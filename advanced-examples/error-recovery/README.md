# エラーリカバリーパターン

エージェントの信頼性を高めるための多層防御アプローチです。

## 概要

AI エージェントは複雑なシステムであり、様々な要因で失敗します。
- ネットワークの一時的な障害
- LLM の出力パースエラー
- 外部 API のレート制限
- 予期しない入力

多層的なエラー処理により、自動回復と graceful degradation を実現します。

## エラーの分類

| カテゴリ | 例 | 対処 |
|---------|---|------|
| **Transient（一時的）** | ネットワーク断、タイムアウト、レート制限 | Retry |
| **Recoverable（回復可能）** | 無効なJSON、パース失敗 | Retry + プロンプト修正 |
| **Permanent（永続的）** | 認証失敗、無効な入力 | Fallback or Human |
| **Catastrophic（致命的）** | セキュリティ違反 | 即座に停止 |

## 階層的アプローチ

```
┌─────────────────────────────────────────────────────────────────┐
│                    Error Recovery Layers                         │
│                                                                  │
│  Layer 1: Retry with Backoff                                    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  一時的エラー（ネットワーク、レート制限）→ 再試行       │    │
│  │  Exponential Backoff: 1s → 2s → 4s → 8s                 │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              ↓ 失敗                              │
│  Layer 2: Fallback                                              │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  代替手段に切り替え                                      │    │
│  │  • 別のLLMモデル                                        │    │
│  │  • 別のツール                                           │    │
│  │  • 縮退モード（機能制限版）                             │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              ↓ 失敗                              │
│  Layer 3: Circuit Breaker                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  連続失敗時はサービスを一時停止                          │    │
│  │  • カスケード障害の防止                                  │    │
│  │  • 一定時間後に再開試行                                  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              ↓ 失敗                              │
│  Layer 4: Human Escalation                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  自動回復不可能な場合は人間に委譲                        │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## 使用方法

```python
from error_recovery import ResilientExecutor, ResilienceConfig, TransientError

config = ResilienceConfig(
    max_retries=3,
    base_delay=1.0,
    failure_threshold=5,  # Circuit Breaker
)
executor = ResilientExecutor(config)

# Retry + Fallback 付きで実行
async def primary_operation():
    # メインの処理
    raise TransientError("Network error")

async def fallback_operation():
    return "Fallback result"

result = await executor.execute(
    primary_operation,
    circuit_name="api_call",
    fallbacks=[fallback_operation],
)
```

## 主要コンポーネント

### RetryStrategy

指数バックオフ + ジッターで再試行します。

```python
def calculate_delay(self, attempt: int) -> float:
    """指数バックオフ + ジッター"""
    delay = min(
        base_delay * (2 ** attempt),
        max_delay,
    )
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter
```

### FallbackChain

プライマリ操作が失敗した場合、順番にフォールバックを試行します。

```python
chain = FallbackChain(config)
chain.add_fallback(fallback_1)
chain.add_fallback(fallback_2)

result = await chain.execute(primary_operation)
```

### CircuitBreaker

連続した失敗を検出し、サービスを一時的に遮断します。

```
状態遷移:
CLOSED (正常) ──[失敗が閾値に達する]──▶ OPEN (遮断)
                                            │
                                     [回復タイムアウト]
                                            ▼
                                      HALF-OPEN (試行)
                                       │       │
                              [成功]   │       │  [失敗]
                                ▼      │       │     ▼
                             CLOSED    │       │   OPEN
                                       ◀───────┘
```

## 設定例

```python
ResilienceConfig(
    # Retry
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0,
    exponential_base=2.0,
    jitter_factor=0.1,

    # Fallback
    max_fallback_depth=4,
    fallback_timeout=60.0,

    # Circuit Breaker
    failure_threshold=5,
    recovery_timeout=30.0,
    half_open_max_calls=3,
)
```

## デコレーター

```python
from error_recovery import with_retry, with_fallback

@with_retry(max_retries=3, base_delay=1.0)
async def api_call():
    ...

@with_fallback(fallback_fn1, fallback_fn2)
async def complex_operation():
    ...
```

## ベストプラクティス

1. **エラーを分類する**: 一時的 vs 永続的
2. **適切な待機時間**: 指数バックオフ + ジッター
3. **フォールバック層を設計**: Tier 1（完全機能）→ Tier 2（基本機能）→ Tier 3（最小機能）
4. **Circuit Breaker でカスケード障害を防止**
5. **包括的なログとアラート**
6. **人間の介入は最後の手段**

## 参考文献

- [Error Recovery and Fallback Strategies](https://www.gocodeo.com/post/error-recovery-and-fallback-strategies-in-ai-agent-development)
- [Retries, Fallbacks, and Circuit Breakers](https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps/)
- [Why Most AI Agents Fail & How to Fix Them](https://galileo.ai/blog/why-most-ai-agents-fail-and-how-to-fix-them)
- [LangChain Agent Error Handling Best Practices](https://benny.ghost.io/blog/langchain-agent-error-handling-best-practices/)

## ファイル

- [error_recovery.py](./error_recovery.py) - 実装コード
