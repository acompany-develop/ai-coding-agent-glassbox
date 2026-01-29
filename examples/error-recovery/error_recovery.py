"""
エラーリカバリーパターン

エージェントの信頼性を高めるための多層防御アプローチを実装します。

階層:
1. Retry with Backoff: 一時的エラーに対する再試行
2. Fallback: 代替手段への切り替え
3. Circuit Breaker: 連続失敗時のサービス停止
4. Human Escalation: 自動回復不可能な場合の人間への委譲
"""

from __future__ import annotations

import asyncio
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, TypeVar

T = TypeVar("T")


# =============================================================================
# エラーの分類
# =============================================================================


class ErrorCategory(Enum):
    TRANSIENT = "transient"  # 一時的（ネットワーク、レート制限）
    RECOVERABLE = "recoverable"  # 回復可能（パース失敗、無効なJSON）
    PERMANENT = "permanent"  # 永続的（認証失敗、無効な入力）
    CATASTROPHIC = "catastrophic"  # 致命的（セキュリティ違反）


class TransientError(Exception):
    """一時的なエラー（再試行で回復可能）"""

    pass


class RecoverableError(Exception):
    """回復可能なエラー（修正して再試行可能）"""

    def __init__(self, message: str, suggestion: str = ""):
        super().__init__(message)
        self.suggestion = suggestion


class PermanentError(Exception):
    """永続的なエラー（再試行では回復不可能）"""

    pass


class CatastrophicError(Exception):
    """致命的なエラー（即座に停止が必要）"""

    pass


# =============================================================================
# 設定
# =============================================================================


@dataclass
class ResilienceConfig:
    """回復力の設定"""

    # Retry設定
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter_factor: float = 0.1

    # Fallback設定
    max_fallback_depth: int = 4
    fallback_timeout: float = 60.0

    # Circuit Breaker設定
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3


# =============================================================================
# Retry with Exponential Backoff
# =============================================================================


class RetryStrategy:
    """再試行戦略"""

    def __init__(self, config: ResilienceConfig):
        self.config = config

    def calculate_delay(self, attempt: int) -> float:
        """指数バックオフ + ジッターで待機時間を計算"""
        delay = min(
            self.config.base_delay * (self.config.exponential_base**attempt),
            self.config.max_delay,
        )
        jitter = random.uniform(0, delay * self.config.jitter_factor)
        return delay + jitter

    async def execute_with_retry(
        self,
        operation: Callable[[], T],
        on_retry: Callable[[int, Exception], None] | None = None,
    ) -> T:
        """再試行付きで操作を実行"""
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                return await self._execute(operation)

            except TransientError as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    delay = self.calculate_delay(attempt)
                    if on_retry:
                        on_retry(attempt + 1, e)
                    print(
                        f"  [RETRY] Attempt {attempt + 1}/{self.config.max_retries}, "
                        f"waiting {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)

            except (PermanentError, CatastrophicError):
                raise

        raise last_exception or Exception("All retries exhausted")

    async def _execute(self, operation: Callable[[], T]) -> T:
        """同期/非同期の両方に対応した実行"""
        if asyncio.iscoroutinefunction(operation):
            return await operation()
        else:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, operation)


# =============================================================================
# Fallback
# =============================================================================


@dataclass
class FallbackResult:
    """Fallbackの結果"""

    success: bool
    result: Any = None
    fallback_level: int = 0
    error: Exception | None = None


class FallbackChain:
    """Fallbackチェーン"""

    def __init__(self, config: ResilienceConfig):
        self.config = config
        self.fallbacks: list[Callable] = []

    def add_fallback(self, fallback: Callable) -> "FallbackChain":
        """Fallbackを追加"""
        self.fallbacks.append(fallback)
        return self

    async def execute(self, primary: Callable) -> FallbackResult:
        """プライマリ操作を実行し、失敗時はFallbackを試行"""
        operations = [primary] + self.fallbacks[: self.config.max_fallback_depth - 1]

        for level, operation in enumerate(operations):
            try:
                if asyncio.iscoroutinefunction(operation):
                    result = await asyncio.wait_for(
                        operation(), timeout=self.config.fallback_timeout
                    )
                else:
                    result = operation()

                return FallbackResult(
                    success=True, result=result, fallback_level=level
                )

            except CatastrophicError:
                raise

            except Exception as e:
                print(f"  [FALLBACK] Level {level} failed: {e}")
                if level == len(operations) - 1:
                    return FallbackResult(
                        success=False, fallback_level=level, error=e
                    )

        return FallbackResult(success=False, error=Exception("No operations available"))


# =============================================================================
# Circuit Breaker
# =============================================================================


class CircuitState(Enum):
    CLOSED = "closed"  # 正常動作
    OPEN = "open"  # 遮断中
    HALF_OPEN = "half_open"  # 回復試行中


class CircuitBreaker:
    """
    Circuit Breaker パターン

    連続した失敗を検出し、サービスを一時的に遮断して
    カスケード障害を防止します。
    """

    def __init__(self, name: str, config: ResilienceConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.half_open_calls = 0

    @property
    def is_open(self) -> bool:
        """回路が開いている（遮断中）かどうか"""
        if self.state == CircuitState.OPEN:
            # 回復タイムアウト経過後はHalf-Openに移行
            if self._should_attempt_recovery():
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return False
            return True
        return False

    def _should_attempt_recovery(self) -> bool:
        """回復を試行すべきかどうか"""
        if self.last_failure_time is None:
            return True
        return time.time() - self.last_failure_time >= self.config.recovery_timeout

    def record_success(self) -> None:
        """成功を記録"""
        self.failure_count = 0

        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.half_open_max_calls:
                print(f"  [CIRCUIT] {self.name}: Closed (recovered)")
                self.state = CircuitState.CLOSED
                self.success_count = 0

    def record_failure(self) -> None:
        """失敗を記録"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            print(f"  [CIRCUIT] {self.name}: Open (recovery failed)")
            self.state = CircuitState.OPEN

        elif self.failure_count >= self.config.failure_threshold:
            print(
                f"  [CIRCUIT] {self.name}: Open "
                f"(threshold {self.config.failure_threshold} reached)"
            )
            self.state = CircuitState.OPEN

    async def execute(self, operation: Callable[[], T]) -> T:
        """Circuit Breaker付きで操作を実行"""
        if self.is_open:
            raise TransientError(f"Circuit {self.name} is open")

        try:
            if asyncio.iscoroutinefunction(operation):
                result = await operation()
            else:
                result = operation()
            self.record_success()
            return result

        except Exception as e:
            self.record_failure()
            raise


# =============================================================================
# 統合: ResilientExecutor
# =============================================================================


class ResilientExecutor:
    """
    回復力のある実行器

    Retry, Fallback, Circuit Breakerを統合して提供します。
    """

    def __init__(self, config: ResilienceConfig | None = None):
        self.config = config or ResilienceConfig()
        self.retry_strategy = RetryStrategy(self.config)
        self.circuit_breakers: dict[str, CircuitBreaker] = {}

    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """Circuit Breakerを取得（なければ作成）"""
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(name, self.config)
        return self.circuit_breakers[name]

    async def execute(
        self,
        operation: Callable[[], T],
        circuit_name: str = "default",
        fallbacks: list[Callable] | None = None,
    ) -> T:
        """
        回復力のある実行

        1. Circuit Breakerをチェック
        2. Retry with Backoffで実行
        3. 失敗時はFallbackを試行
        """
        circuit = self.get_circuit_breaker(circuit_name)

        # Circuit Breakerがオープンならすぐにfallbackを試行
        if circuit.is_open:
            print(f"  [CIRCUIT] {circuit_name} is open, trying fallbacks...")
            if fallbacks:
                chain = FallbackChain(self.config)
                for fb in fallbacks:
                    chain.add_fallback(fb)
                result = await chain.execute(lambda: None)
                if result.success:
                    return result.result
            raise TransientError(f"Circuit {circuit_name} is open and no fallbacks")

        # Retry with Backoff
        try:
            return await self.retry_strategy.execute_with_retry(
                lambda: circuit.execute(operation)
            )
        except Exception as e:
            # Fallbackを試行
            if fallbacks:
                print(f"  [FALLBACK] Primary failed, trying fallbacks...")
                chain = FallbackChain(self.config)
                for fb in fallbacks:
                    chain.add_fallback(fb)
                result = await chain.execute(fallbacks[0] if fallbacks else operation)
                if result.success:
                    return result.result
            raise


# =============================================================================
# デコレーター
# =============================================================================


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple = (TransientError,),
):
    """再試行デコレーター"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            config = ResilienceConfig(max_retries=max_retries, base_delay=base_delay)
            strategy = RetryStrategy(config)

            async def operation():
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                return func(*args, **kwargs)

            return await strategy.execute_with_retry(operation)

        return wrapper

    return decorator


def with_fallback(*fallback_funcs: Callable):
    """Fallbackデコレーター"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            config = ResilienceConfig()
            chain = FallbackChain(config)
            for fb in fallback_funcs:
                chain.add_fallback(lambda f=fb: f(*args, **kwargs))

            result = await chain.execute(lambda: func(*args, **kwargs))
            if result.success:
                return result.result
            raise result.error or Exception("All fallbacks failed")

        return wrapper

    return decorator


# =============================================================================
# デモ
# =============================================================================


async def main():
    """デモ実行"""
    print("=" * 60)
    print("Error Recovery Demo")
    print("=" * 60)

    config = ResilienceConfig(
        max_retries=3,
        base_delay=0.5,
        failure_threshold=3,
        recovery_timeout=5.0,
    )
    executor = ResilientExecutor(config)

    # シミュレートされた操作
    attempt_count = 0

    def flaky_operation():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise TransientError(f"Simulated failure #{attempt_count}")
        return f"Success on attempt {attempt_count}"

    def fallback_operation():
        return "Fallback result"

    # テスト1: Retry成功
    print("\n--- Test 1: Retry with eventual success ---")
    attempt_count = 0
    try:
        result = await executor.execute(flaky_operation, circuit_name="test1")
        print(f"Result: {result}")
    except Exception as e:
        print(f"Failed: {e}")

    # テスト2: Fallback
    print("\n--- Test 2: Fallback ---")

    def always_fail():
        raise TransientError("Always fails")

    try:
        result = await executor.execute(
            always_fail, circuit_name="test2", fallbacks=[fallback_operation]
        )
        print(f"Result: {result}")
    except Exception as e:
        print(f"Failed: {e}")

    # テスト3: Circuit Breaker
    print("\n--- Test 3: Circuit Breaker ---")
    circuit = executor.get_circuit_breaker("test3")

    for i in range(6):
        try:
            await circuit.execute(always_fail)
        except TransientError:
            print(f"  Attempt {i + 1}: Failed")
        except Exception as e:
            print(f"  Attempt {i + 1}: {e}")

    print(f"  Circuit state: {circuit.state.value}")


if __name__ == "__main__":
    asyncio.run(main())
