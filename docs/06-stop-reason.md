# 06. stop_reason による状態遷移

エージェントループの継続・終了を制御する仕組みです。

## stop_reason とは

LLM レスポンスに含まれる「終了理由」です。これによってエージェントの次のアクションが決まります。

```python
@dataclass
class LLMResponse:
    text: str | None
    tool_calls: list[ToolCall]
    stop_reason: str  # "tool_use" or "end_turn"
    raw_response: Any
```

## 状態遷移図

```
                    ┌─────────────────────────────────────────┐
                    │          Agent Loop Start               │
                    │                                         │
                    │  ユーザー入力を受け取る                   │
                    └─────────────────────────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────────┐
                    │          THINK: LLM 呼び出し             │
                    │                                         │
                    │  messages + tools を送信                 │
                    │  → LLMResponse を取得                    │
                    └─────────────────────────────────────────┘
                                       │
                                       ▼
                         ┌─────────────────────────┐
                         │     stop_reason は？    │
                         └─────────────────────────┘
                          │                       │
              ┌───────────┘                       └───────────┐
              │                                               │
              ▼                                               ▼
┌─────────────────────────────┐             ┌─────────────────────────────┐
│   stop_reason: "tool_use"   │             │   stop_reason: "end_turn"   │
│                             │             │                             │
│ LLM がツールを呼びたい      │             │ LLM がタスク完了と判断      │
│ → ACT フェーズへ           │             │ → ループ終了               │
└─────────────────────────────┘             └─────────────────────────────┘
              │                                               │
              ▼                                               ▼
┌─────────────────────────────┐             ┌─────────────────────────────┐
│   ACT: ツール実行           │             │   最終レスポンスを返す      │
│                             │             │                             │
│ tool_registry.execute()     │             │ return response.text        │
└─────────────────────────────┘             └─────────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│   OBSERVE: 結果を履歴に追加 │
│                             │
│ message_history.add_tool_result()
└─────────────────────────────┘
              │
              │ 次のイテレーションへ
              └──────────────────┐
                                 │
                                 ▼
                    ┌─────────────────────────────────────────┐
                    │          THINK: LLM 呼び出し（次）       │
                    └─────────────────────────────────────────┘
                                       │
                                      ...（繰り返し）
```

## stop_reason の値

### "tool_use"

LLM がツールを呼び出したいことを示します。

```python
# agent.py
if response.stop_reason == "tool_use" or response.tool_calls:
    # ツールを実行
    for tool_call in response.tool_calls:
        result = self.tool_registry.execute(tool_call.name, tool_call.input)
        self.message_history.add_tool_result(...)
    # 次のイテレーションへ
```

### "end_turn"

LLM がタスクを完了し、最終回答を返すことを示します。

```python
# agent.py
if response.stop_reason == "end_turn":
    return response.text or ""
```

## プロバイダーごとの stop_reason 判定

### Gemini

```python
# gemini_client.py
def _parse_response(self, response) -> LLMResponse:
    tool_calls = []

    for part in response.candidates[0].content.parts:
        if part.function_call:
            tool_calls.append(ToolCall(...))

    # tool_calls があれば "tool_use"、なければ "end_turn"
    stop_reason = "tool_use" if tool_calls else "end_turn"

    return LLMResponse(
        stop_reason=stop_reason,
        tool_calls=tool_calls,
        ...
    )
```

### Llama

```python
# llama_client.py
def _parse_response(self, response_text: str) -> LLMResponse:
    data = json.loads(response_text)

    if "tool_call" in data:
        # JSON に tool_call キーがあれば "tool_use"
        return LLMResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCall(...)],
            ...
        )
    else:
        # response キーがあれば "end_turn"
        return LLMResponse(
            stop_reason="end_turn",
            tool_calls=[],
            ...
        )
```

## 実際のコード

```python
# agent.py
def run(self, user_input: str) -> str:
    self.message_history.add_user_message(user_input)

    for iteration in range(1, self.max_iterations + 1):
        # THINK
        response = self.llm_client.chat(
            messages=self.message_history.get_messages(),
            tools=self.tool_registry.get_tool_definitions(),
        )

        # アシスタント応答を履歴に追加
        assistant_msg = self.llm_client.format_assistant_message(response)
        self.message_history.add_raw_message(assistant_msg)

        # 終了判定
        if response.stop_reason == "end_turn":
            return response.text or ""

        # ツールなしの場合も終了
        if not response.tool_calls:
            return response.text or ""

        # ACT & OBSERVE
        for tool_call in response.tool_calls:
            result = self.tool_registry.execute(
                tool_call.name,
                tool_call.input,
            )
            self.message_history.add_tool_result(
                tool_call.id,
                result,
                tool_name=tool_call.name,
            )

    # 最大イテレーション到達
    raise RuntimeError(f"Max iterations ({self.max_iterations}) reached")
```

## 状態遷移表

| 現在の状態 | stop_reason | tool_calls | 次の状態 |
|-----------|-------------|------------|---------|
| THINK | `"tool_use"` | あり | ACT → OBSERVE → THINK |
| THINK | `"end_turn"` | なし | END（ループ終了） |
| THINK | 任意 | なし | END（ループ終了） |
| THINK | N/A | N/A | ERROR（最大イテレーション） |

## 各プロバイダーの元の値

| プロバイダー | ツール呼び出し時 | タスク完了時 | 元の値 |
|-------------|----------------|-------------|--------|
| Gemini | `"tool_use"` | `"end_turn"` | `function_call` の有無 |
| Llama | `"tool_use"` | `"end_turn"` | JSON の `tool_call` / `response` キー |

これらの差異を LLM クライアント内で吸収し、エージェントループからは統一された `stop_reason` として扱えます。

## デバッグ出力

```
[LLM] Response stop_reason: tool_use
[ACT] Executing tool: read_file
[OBSERVE] Result preview: def greet(): ...

[LLM] Response stop_reason: end_turn
[THINK] LLM decided to respond without tools - ending loop
```

## 関連ドキュメント

- [01-agent-loop.md](./01-agent-loop.md) - ループ全体の流れ
- [03-llm-clients.md](./03-llm-clients.md) - プロバイダーごとの実装
