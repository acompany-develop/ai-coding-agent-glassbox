# 06. メッセージ履歴の管理

LLM との会話履歴を管理し、コンテキストを維持するための仕組みです。

## なぜ履歴が必要か

LLM は **ステートレス** です。各リクエストは独立しており、前の会話を覚えていません。
そのため、毎回のリクエストで「これまでの会話全体」を送信する必要があります。

```
リクエスト 1:
  messages: [
    {role: "user", content: "hello.py を読んで"}
  ]

リクエスト 2:
  messages: [
    {role: "user", content: "hello.py を読んで"},
    {role: "assistant", content: ..., tool_calls: [...]},
    {role: "user", content: [{type: "tool_result", ...}]},
  ]
```

## MessageHistory クラス

```python
# message_history.py
class MessageHistory:
    def __init__(self):
        self.messages: list[dict] = []

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_raw_message(self, message: dict) -> None:
        self.messages.append(message)

    def add_tool_result(
        self,
        tool_use_id: str,
        result: str,
        tool_name: str = "unknown",
    ) -> None:
        self.messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "content": result,
            }],
        })

    def get_messages(self) -> list[dict]:
        return self.messages.copy()

    def clear(self) -> None:
        self.messages = []
```

## メッセージの種類

### 1. ユーザーメッセージ

```python
{"role": "user", "content": "hello.py を読んで"}
```

### 2. アシスタントメッセージ（ツール呼び出し）

```python
{
    "role": "assistant",
    "content": [
        TextBlock(type="text", text="ファイルを読みます。"),
        ToolUseBlock(type="tool_use", id="call_abc", name="read_file", input={...}),
    ]
}
```

### 3. ツール結果メッセージ

```python
{
    "role": "user",
    "content": [{
        "type": "tool_result",
        "tool_use_id": "call_abc",
        "tool_name": "read_file",
        "content": "def greet():\n    return 'Hello'",
    }]
}
```

## ask_user ツールとの連携

`ask_user` ツールの結果も他のツールと同様に履歴に追加されます。

```
Iteration 1:
  THINK → LLM: ask_user ツールを呼び出す
  ACT   → ask_user(question="削除してよいですか？")
          → ユーザー入力待ち
          → ユーザー: "はい"
  OBSERVE → "はい" を履歴に追加

履歴:
  [user]: "ファイルを削除して"
  [assistant]: [ask_user ツール呼び出し]
  [user]: [tool_result: "はい"]

Iteration 2:
  THINK → LLM: ユーザーが承認したことを認識
  ...
```

## 関連ドキュメント

- [01-agent-loop.md](./01-agent-loop.md) - 履歴が使われる流れ
- [03-llm-clients.md](./03-llm-clients.md) - プロバイダーごとの形式変換
