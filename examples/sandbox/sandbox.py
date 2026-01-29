"""
サンドボックス実行

LLMが生成したコードを安全に実行するための隔離環境を提供します。

レベル:
1. Process Isolation: subprocess + 制限された権限
2. Container Isolation: Docker/LXC
3. MicroVM Isolation: Firecracker（本番推奨）

このファイルでは教育目的でLevel 1の簡易実装を提供します。
本番環境ではE2B、Microsandbox等の利用を推奨します。
"""

from __future__ import annotations

import ast
import io
import signal
import sys
import threading
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# データ構造
# =============================================================================


@dataclass
class ExecutionResult:
    """コード実行の結果"""

    success: bool
    output: str
    error: str | None = None
    execution_time: float = 0.0
    memory_used: int = 0  # bytes


@dataclass
class SecurityPolicy:
    """セキュリティポリシー"""

    # 許可されないモジュール
    blocked_modules: set[str] = field(
        default_factory=lambda: {
            "os",
            "subprocess",
            "sys",
            "shutil",
            "socket",
            "requests",
            "urllib",
            "http",
            "ftplib",
            "smtplib",
            "telnetlib",
            "pickle",
            "marshal",
            "shelve",
            "ctypes",
            "multiprocessing",
            "threading",
            "_thread",
        }
    )

    # 許可されないビルトイン
    blocked_builtins: set[str] = field(
        default_factory=lambda: {
            "open",
            "exec",
            "eval",
            "compile",
            "__import__",
            "input",
            "breakpoint",
            "memoryview",
            "globals",
            "locals",
            "vars",
            "dir",
            "getattr",
            "setattr",
            "delattr",
            "hasattr",
        }
    )

    # 実行制限
    max_execution_time: float = 5.0  # seconds
    max_memory: int = 50 * 1024 * 1024  # 50 MB
    max_output_length: int = 10000  # characters


# =============================================================================
# 静的解析
# =============================================================================


class CodeAnalyzer:
    """コードの静的解析"""

    def __init__(self, policy: SecurityPolicy):
        self.policy = policy

    def analyze(self, code: str) -> list[str]:
        """
        コードを解析し、セキュリティ違反を検出

        Returns:
            violations: 検出された違反のリスト
        """
        violations = []

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [f"Syntax error: {e}"]

        for node in ast.walk(tree):
            # Import文のチェック
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module in self.policy.blocked_modules:
                        violations.append(f"Blocked module import: {module}")

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module = node.module.split(".")[0]
                    if module in self.policy.blocked_modules:
                        violations.append(f"Blocked module import: {module}")

            # eval/exec のチェック
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in {"eval", "exec", "compile"}:
                        violations.append(f"Blocked function call: {node.func.id}")

            # ファイル操作のチェック
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id == "open":
                        violations.append("File operations are not allowed")

            # __のアクセス（dunder）のチェック
            elif isinstance(node, ast.Attribute):
                if node.attr.startswith("__") and node.attr.endswith("__"):
                    violations.append(f"Dunder attribute access: {node.attr}")

        return violations


# =============================================================================
# タイムアウト
# =============================================================================


class TimeoutError(Exception):
    """実行タイムアウト"""

    pass


@contextmanager
def timeout_context(seconds: float):
    """タイムアウト付きコンテキスト（Unix系のみ）"""

    def handler(signum, frame):
        raise TimeoutError(f"Execution timed out after {seconds} seconds")

    # シグナルハンドラを設定（Unix系のみ）
    try:
        old_handler = signal.signal(signal.SIGALRM, handler)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


@contextmanager
def timeout_context_thread(seconds: float):
    """スレッドベースのタイムアウト（クロスプラットフォーム）"""
    result = {"timed_out": False}

    def check_timeout():
        result["timed_out"] = True

    timer = threading.Timer(seconds, check_timeout)
    timer.start()
    try:
        yield result
    finally:
        timer.cancel()


# =============================================================================
# サンドボックス
# =============================================================================


class SimpleSandbox:
    """
    シンプルなサンドボックス（教育用）

    警告: この実装は教育目的です。本番環境では使用しないでください。
    本番環境ではMicroVM (E2B, Firecracker) やコンテナを使用してください。
    """

    def __init__(self, policy: SecurityPolicy | None = None):
        self.policy = policy or SecurityPolicy()
        self.analyzer = CodeAnalyzer(self.policy)

    def execute(self, code: str, inputs: dict | None = None) -> ExecutionResult:
        """
        コードを安全に実行

        Args:
            code: 実行するPythonコード
            inputs: コードに渡す入力変数

        Returns:
            ExecutionResult: 実行結果
        """
        import time

        start_time = time.time()

        # 1. 静的解析
        violations = self.analyzer.analyze(code)
        if violations:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Security violations:\n" + "\n".join(f"- {v}" for v in violations),
            )

        # 2. 安全なグローバル環境を作成
        safe_globals = self._create_safe_globals()
        if inputs:
            safe_globals.update(inputs)

        # 3. 出力をキャプチャ
        output_buffer = io.StringIO()
        old_stdout = sys.stdout

        try:
            sys.stdout = output_buffer

            # 4. タイムアウト付きで実行
            with timeout_context_thread(self.policy.max_execution_time) as timeout_state:
                exec(code, safe_globals)

                if timeout_state["timed_out"]:
                    return ExecutionResult(
                        success=False,
                        output=output_buffer.getvalue()[: self.policy.max_output_length],
                        error=f"Execution timed out after {self.policy.max_execution_time}s",
                        execution_time=time.time() - start_time,
                    )

            output = output_buffer.getvalue()
            if len(output) > self.policy.max_output_length:
                output = output[: self.policy.max_output_length] + "\n... (truncated)"

            return ExecutionResult(
                success=True,
                output=output,
                execution_time=time.time() - start_time,
            )

        except TimeoutError as e:
            return ExecutionResult(
                success=False,
                output=output_buffer.getvalue()[: self.policy.max_output_length],
                error=str(e),
                execution_time=time.time() - start_time,
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output=output_buffer.getvalue()[: self.policy.max_output_length],
                error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                execution_time=time.time() - start_time,
            )

        finally:
            sys.stdout = old_stdout

    def _create_safe_globals(self) -> dict[str, Any]:
        """安全なグローバル環境を作成"""
        # 安全なビルトインのみを含める
        safe_builtins = {}
        for name, obj in __builtins__.__dict__.items() if hasattr(__builtins__, '__dict__') else __builtins__.items():
            if name not in self.policy.blocked_builtins:
                safe_builtins[name] = obj

        # 安全な標準ライブラリを追加
        import math
        import json
        import datetime
        import collections
        import itertools
        import functools
        import re

        return {
            "__builtins__": safe_builtins,
            "math": math,
            "json": json,
            "datetime": datetime,
            "collections": collections,
            "itertools": itertools,
            "functools": functools,
            "re": re,
        }


# =============================================================================
# Docker サンドボックス（概念実装）
# =============================================================================


class DockerSandbox:
    """
    Dockerベースのサンドボックス（概念実装）

    実際の実装には docker-py パッケージが必要です。
    """

    def __init__(
        self,
        image: str = "python:3.11-slim",
        memory_limit: str = "100m",
        cpu_limit: float = 1.0,
        network_disabled: bool = True,
    ):
        self.image = image
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.network_disabled = network_disabled

    def execute(self, code: str) -> ExecutionResult:
        """
        Dockerコンテナ内でコードを実行

        注: この実装は概念的なものです。
        実際の実装には docker-py が必要です。
        """
        # 概念的なコード
        """
        import docker
        client = docker.from_env()

        container = client.containers.run(
            image=self.image,
            command=["python", "-c", code],
            mem_limit=self.memory_limit,
            cpu_quota=int(self.cpu_limit * 100000),
            network_disabled=self.network_disabled,
            read_only=True,
            remove=True,
            detach=True,
        )

        try:
            result = container.wait(timeout=30)
            logs = container.logs().decode()
            return ExecutionResult(
                success=result['StatusCode'] == 0,
                output=logs,
            )
        finally:
            container.remove(force=True)
        """
        return ExecutionResult(
            success=False,
            output="",
            error="Docker sandbox is a conceptual implementation",
        )


# =============================================================================
# MicroVM サンドボックス（概念実装）
# =============================================================================


class MicroVMSandbox:
    """
    MicroVMベースのサンドボックス（概念実装）

    本番環境で最も安全な選択肢です。
    E2B、Microsandbox、Firecracker 等を使用してください。
    """

    def __init__(
        self,
        memory_mb: int = 512,
        vcpus: int = 1,
        timeout: float = 30.0,
    ):
        self.memory_mb = memory_mb
        self.vcpus = vcpus
        self.timeout = timeout

    def execute(self, code: str) -> ExecutionResult:
        """
        MicroVM内でコードを実行

        注: 本番環境では E2B (https://e2b.dev) 等を使用してください。
        """
        # 概念的なコード
        """
        from e2b import Sandbox

        sandbox = Sandbox(
            template="python",
            timeout=self.timeout,
        )

        try:
            result = sandbox.run_code(code)
            return ExecutionResult(
                success=not result.error,
                output=result.stdout,
                error=result.stderr if result.error else None,
            )
        finally:
            sandbox.close()
        """
        return ExecutionResult(
            success=False,
            output="",
            error="MicroVM sandbox requires external service (e.g., E2B)",
        )


# =============================================================================
# デモ
# =============================================================================


def main():
    """デモ実行"""
    print("=" * 60)
    print("Sandbox Demo")
    print("=" * 60)

    sandbox = SimpleSandbox()

    # テスト1: 安全なコード
    print("\n--- Test 1: Safe code ---")
    code1 = """
result = sum([1, 2, 3, 4, 5])
print(f"Sum: {result}")
"""
    result = sandbox.execute(code1)
    print(f"Success: {result.success}")
    print(f"Output: {result.output}")

    # テスト2: 数学計算
    print("\n--- Test 2: Math calculation ---")
    code2 = """
import math
result = math.factorial(10)
print(f"10! = {result}")
"""
    result = sandbox.execute(code2)
    print(f"Success: {result.success}")
    print(f"Output: {result.output}")

    # テスト3: ブロックされたモジュール
    print("\n--- Test 3: Blocked module (os) ---")
    code3 = """
import os
os.system("ls")
"""
    result = sandbox.execute(code3)
    print(f"Success: {result.success}")
    print(f"Error: {result.error}")

    # テスト4: ブロックされた関数
    print("\n--- Test 4: Blocked function (open) ---")
    code4 = """
with open("/etc/passwd") as f:
    print(f.read())
"""
    result = sandbox.execute(code4)
    print(f"Success: {result.success}")
    print(f"Error: {result.error}")

    # テスト5: eval/exec
    print("\n--- Test 5: Blocked (eval) ---")
    code5 = """
eval("__import__('os').system('ls')")
"""
    result = sandbox.execute(code5)
    print(f"Success: {result.success}")
    print(f"Error: {result.error}")

    # テスト6: 入力変数
    print("\n--- Test 6: With input variables ---")
    code6 = """
result = x + y
print(f"{x} + {y} = {result}")
"""
    result = sandbox.execute(code6, inputs={"x": 10, "y": 20})
    print(f"Success: {result.success}")
    print(f"Output: {result.output}")

    # テスト7: 実行時間
    print("\n--- Test 7: Execution time ---")
    code7 = """
import math
for i in range(100000):
    math.sqrt(i)
print("Done")
"""
    result = sandbox.execute(code7)
    print(f"Success: {result.success}")
    print(f"Execution time: {result.execution_time:.3f}s")


if __name__ == "__main__":
    main()
