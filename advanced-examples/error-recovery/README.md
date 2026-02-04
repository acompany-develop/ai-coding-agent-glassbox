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

### 基本: エージェントループに組み込む

Error Recovery はエージェントループの内部に組み込んで使います。
LLM 呼び出しやツール実行を `executor.execute()` で包むことで、リトライやフォールバックが自動的に適用されます。

```python
class Agent:
    def __init__(self, llm_client, tool_registry):
        self.llm_client = llm_client
        self.tool_registry = tool_registry

        # Error Recovery の設定
        config = ResilienceConfig(
            max_retries=3,       # 最大3回リトライ
            base_delay=1.0,      # 初回待機1秒（以降 2s, 4s と倍増）
            failure_threshold=5, # 5回連続失敗で Circuit Breaker が遮断
        )
        self.executor = ResilientExecutor(config)

    async def run(self, user_input: str) -> str:
        for iteration in range(self.max_iterations):
            # THINK: LLM呼び出しを executor 経由にする
            response = await self.executor.execute(
                lambda: self.llm_client.chat(messages, tools),
                circuit_name="llm",                  # "llm" 回路で管理
                fallbacks=[self.fallback_llm_call],   # 失敗時の代替手段
            )

            if response.stop_reason == "end_turn":
                return response.text

            # ACT: ツール実行も executor 経由にできる
            for tool_call in response.tool_calls:
                result = await self.executor.execute(
                    lambda: self.tool_registry.execute(tool_call.name, tool_call.input),
                    circuit_name=f"tool_{tool_call.name}",  # ツールごとに別回路
                )
```

### executor.execute() の引数

```python
result = await executor.execute(
    primary_operation,              # ① まず実行する関数
    circuit_name="llm",             # ② Circuit Breaker の回路名
    fallbacks=[fallback_operation], # ③ 失敗時の代替関数リスト
)
```

| 引数 | 説明 |
|------|------|
| `primary_operation` | 本来実行したい関数。リトライ対象 |
| `circuit_name` | Circuit Breaker の回路名。同じ名前は同じブレーカーで管理される |
| `fallbacks` | 代替関数のリスト。リトライが全て失敗した場合に順番に試行 |

### circuit_name（回路名）とは

電気のブレーカーと同じ概念です。操作の種類ごとに**独立した回路**を持ち、1箇所の障害が他に波及するのを防ぎます。

```
"llm" 回路       ──[ブレーカー]── LLM API 呼び出し
"tool_read" 回路  ──[ブレーカー]── read_file ツール
"tool_exec" 回路  ──[ブレーカー]── execute_command ツール
```

`"llm"` の回路が5回連続失敗して遮断（OPEN）されても、`"tool_read"` は影響を受けません。

### 実行フロー

`executor.execute()` を呼ぶと、内部で以下が順番に起きます:

```
① Circuit Breaker チェック
   → 回路が OPEN（遮断中）なら即座に ③ へ
   → CLOSED（正常）なら ② へ

② Retry with Backoff
   1回目: primary_operation() 実行 → 失敗 → 1秒待機
   2回目: primary_operation() 実行 → 失敗 → 2秒待機
   3回目: primary_operation() 実行 → 失敗 → 4秒待機
   4回目: primary_operation() 実行 → 失敗 → リトライ上限超過

③ Fallback
   fallbacks[0]() を実行 → 失敗なら fallbacks[1]() → ...
   → 成功した結果を返す
   → 全て失敗なら例外を投げる
```

### 具体例: LLM API のフォールバック

```python
async def call_primary_llm():
    return await gpt4_client.chat(messages, tools)

async def call_fallback_llm():
    return await gpt35_client.chat(messages, tools)

async def return_cached_response():
    return cached_responses.get(user_input, "申し訳ありません、現在応答できません。")

result = await executor.execute(
    call_primary_llm,
    circuit_name="llm",
    fallbacks=[call_fallback_llm, return_cached_response],
)
# GPT-4 → (失敗) → GPT-3.5 → (失敗) → キャッシュ応答
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

## 補足: フレームワーク（LangGraph）を使う場合との違い

本実装では `ResilientExecutor` や `CircuitBreaker` を自前で実装していますが、LangGraph のようなフレームワークを使うと、これらの機能が組み込みで提供されます。

### リトライ

本実装では `RetryStrategy` クラスを自前で書いていますが、LangGraph では `RetryPolicy` をノードに渡すだけで済みます。

```python
# 本実装（自前）
config = ResilienceConfig(max_retries=3, base_delay=1.0)
executor = ResilientExecutor(config)
result = await executor.execute(operation, circuit_name="llm")
```

```python
# LangGraph
from langgraph.graph import StateGraph
from langgraph.types import RetryPolicy

builder = StateGraph(MessagesState)
builder.add_node(
    "call_model",
    call_model,
    retry_policy=RetryPolicy(max_attempts=5),  # これだけでリトライが有効に
)
```

### エラーハンドリング

本実装ではエラー分類（`TransientError` / `PermanentError` 等）を自前で定義していますが、LangGraph では `ToolNode` がエラーハンドリングを内蔵しています。

```python
# 本実装（自前）
class TransientError(Exception): ...
class PermanentError(Exception): ...

# エラー種別に応じて分岐するロジックを自分で書く
```

```python
# LangGraph
from langgraph.prebuilt import ToolNode, create_react_agent

# ToolNode がエラーを自動で ToolMessage に変換し、LLM にフィードバック
custom_tool_node = ToolNode(
    [my_tool],
    handle_tool_errors="ツール実行に失敗しました。別の方法を試してください。",
)
agent = create_react_agent(model="anthropic:claude-3-7-sonnet-latest", tools=custom_tool_node)
```

### ノードごとのリトライポリシー

LangGraph ではノード（処理単位）ごとに異なるリトライポリシーを宣言的に設定できます。本実装の `circuit_name` で回路を分けるのと同じ発想ですが、より簡潔です。

```python
# LangGraph: ノードごとに異なるポリシーを設定
builder.add_node(
    "query_database",
    query_database,
    retry_policy=RetryPolicy(retry_on=sqlite3.OperationalError),  # DB エラーのみリトライ
)
builder.add_node(
    "call_model",
    call_model,
    retry_policy=RetryPolicy(max_attempts=5),  # 最大5回
)
```

### まとめ: 自前実装 vs フレームワーク

| 観点 | 本実装（自前） | LangGraph |
|------|--------------|-----------|
| リトライ | `RetryStrategy` を実装 | `RetryPolicy` を渡すだけ |
| エラーハンドリング | エラー分類・分岐を自前実装 | `ToolNode` が内蔵 |
| Circuit Breaker | `CircuitBreaker` を実装 | フレームワーク外で対応 |
| Fallback | `FallbackChain` を実装 | グラフの条件分岐で表現 |
| 学びやすさ | 内部動作が全て見える | 抽象化されて見えにくい |

本実装は「中で何が起きているか」を理解するためのものです。フレームワークが提供する `RetryPolicy` や `ToolNode` の裏側では、本実装と同様の仕組みが動いています。

## 参考文献

- [Error Recovery and Fallback Strategies](https://www.gocodeo.com/post/error-recovery-and-fallback-strategies-in-ai-agent-development)
- [Retries, Fallbacks, and Circuit Breakers](https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps/)
- [Why Most AI Agents Fail & How to Fix Them](https://galileo.ai/blog/why-most-ai-agents-fail-and-how-to-fix-them)
- [LangChain Agent Error Handling Best Practices](https://benny.ghost.io/blog/langchain-agent-error-handling-best-practices/)

## ファイル

- [error_recovery.py](./error_recovery.py) - 実装コード
