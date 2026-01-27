# 05. メッセージ履歴の管理

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
    {role: "user", content: [{type: "tool_result", ...}]},  # ツール結果
  ]

リクエスト 3:
  messages: [
    {role: "user", content: "hello.py を読んで"},
    {role: "assistant", content: ..., tool_calls: [...]},
    {role: "user", content: [{type: "tool_result", ...}]},
    {role: "assistant", content: "このファイルは..."},
  ]
```

## MessageHistory クラス

```python
# message_history.py
class MessageHistory:
    """会話履歴を管理するクラス"""

    def __init__(self):
        self.messages: list[dict] = []

    def add_user_message(self, content: str) -> None:
        """ユーザーメッセージを追加"""
        self.messages.append({
            "role": "user",
            "content": content,
        })

    def add_raw_message(self, message: dict) -> None:
        """生のメッセージを追加（アシスタント応答用）"""
        self.messages.append(message)

    def add_tool_result(
        self,
        tool_use_id: str,
        result: str,
        tool_name: str = "unknown",
    ) -> None:
        """ツール実行結果を追加"""
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
        """メッセージ履歴のコピーを取得"""
        return self.messages.copy()

    def clear(self) -> None:
        """履歴をクリア"""
        self.messages = []
```

## メッセージの種類

### 1. ユーザーメッセージ

```python
{
    "role": "user",
    "content": "hello.py を読んで"
}
```

### 2. アシスタントメッセージ（テキストのみ）

```python
{
    "role": "assistant",
    "content": [
        TextBlock(type="text", text="ファイルの内容を確認します。")
    ]
}
```

### 3. アシスタントメッセージ（ツール呼び出し）

```python
{
    "role": "assistant",
    "content": [
        TextBlock(type="text", text="ファイルを読みます。"),
        ToolUseBlock(
            type="tool_use",
            id="call_abc123",
            name="read_file",
            input={"path": "hello.py"},
        ),
    ]
}
```

### 4. ツール結果メッセージ

```python
{
    "role": "user",  # ツール結果は user ロールで送る
    "content": [{
        "type": "tool_result",
        "tool_use_id": "call_abc123",
        "tool_name": "read_file",
        "content": "def greet():\n    return 'Hello, World!'",
    }]
}
```

## 典型的な会話フロー

```
User: "hello.py を読んで説明して"
     │
     ▼
┌────────────────────────────────────────────────────────────┐
│ messages = [                                               │
│   {role: "user", content: "hello.py を読んで説明して"}     │
│ ]                                                          │
└────────────────────────────────────────────────────────────┘
     │
     ▼ LLM 呼び出し
     │
     ▼ LLM: "read_file を呼びます"
┌────────────────────────────────────────────────────────────┐
│ messages = [                                               │
│   {role: "user", content: "hello.py を読んで説明して"},    │
│   {role: "assistant", content: [                           │
│     TextBlock("ファイルを読みます"),                        │
│     ToolUseBlock(name="read_file", input={path: "..."})    │
│   ]}                                                        │
│ ]                                                          │
└────────────────────────────────────────────────────────────┘
     │
     ▼ ツール実行
     │
     ▼ 結果を追加
┌────────────────────────────────────────────────────────────┐
│ messages = [                                               │
│   {role: "user", content: "hello.py を読んで説明して"},    │
│   {role: "assistant", content: [...]},                     │
│   {role: "user", content: [{                               │
│     type: "tool_result",                                   │
│     content: "def greet(): ..."                            │
│   }]}                                                       │
│ ]                                                          │
└────────────────────────────────────────────────────────────┘
     │
     ▼ LLM 呼び出し（2回目）
     │
     ▼ LLM: "このファイルは..."
┌────────────────────────────────────────────────────────────┐
│ messages = [                                               │
│   ... (previous messages),                                 │
│   {role: "assistant", content: [                           │
│     TextBlock("このファイルは greet 関数を定義...")        │
│   ]}                                                        │
│ ]                                                          │
└────────────────────────────────────────────────────────────┘
```

## プロバイダーごとの形式変換

メッセージ履歴は共通形式で保持し、LLM クライアントがプロバイダー固有形式に変換します。

### Gemini の場合

```python
# gemini_client.py
def _convert_messages_to_gemini_format(self, messages):
    gemini_contents = []

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            if isinstance(content, list) and content[0].get("type") == "tool_result":
                # ツール結果 → function_response
                parts = [
                    types.Part.from_function_response(
                        name=item["tool_name"],
                        response={"result": item["content"]},
                    )
                    for item in content
                ]
            else:
                # 通常のユーザーメッセージ
                parts = [types.Part.from_text(text=content)]

            gemini_contents.append(types.Content(role="user", parts=parts))

        elif role == "assistant":
            # アシスタントメッセージ → model ロール
            ...

    return gemini_contents
```

### Llama の場合

```python
# llama_client.py
def _convert_messages_to_llama_format(self, messages):
    llama_messages = []

    for msg in messages:
        if msg["role"] == "user":
            content = msg["content"]
            if isinstance(content, list) and content[0].get("type") == "tool_result":
                # ツール結果 → JSON 文字列
                tool_result = {
                    "tool_result": {
                        "name": content[0]["tool_name"],
                        "result": content[0]["content"],
                    }
                }
                llama_messages.append({
                    "role": "user",
                    "content": json.dumps(tool_result),
                })
            else:
                llama_messages.append(msg)
        ...

    return llama_messages
```

## 履歴のリセット

```python
# main.py
if user_input.lower() == "reset":
    agent.reset()
    print("Agent state has been reset.")
    continue

# agent.py
def reset(self) -> None:
    self.message_history.clear()
```

新しいタスクを始める際や、エラーが発生した際に履歴をクリアします。

## コンテキスト長の考慮

履歴が長くなると、LLM のコンテキスト長制限に達する可能性があります。

対策（本実装では未実装）：
- 古いメッセージの要約
- 重要なメッセージのみ保持
- スライディングウィンドウ

## 関連ドキュメント

- [01-agent-loop.md](./01-agent-loop.md) - 履歴が使われる流れ
- [03-llm-clients.md](./03-llm-clients.md) - プロバイダーごとの形式変換
