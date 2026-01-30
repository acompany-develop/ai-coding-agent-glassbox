# 01. エージェントループ

AI エージェントの核心は **Think → Act → Observe** のサイクルです。

## 基本概念

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent Loop                               │
│                                                             │
│   ユーザー入力: "hello.py を読んで内容を説明して"            │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Iteration 1                                         │   │
│   │                                                     │   │
│   │  THINK   → LLM: "read_file を呼ぶ必要がある"         │   │
│   │  ACT     → read_file(path="hello.py") 実行          │   │
│   │  OBSERVE → ファイル内容を取得                        │   │
│   └─────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Iteration 2                                         │   │
│   │                                                     │   │
│   │  THINK   → LLM: "内容を理解した、説明を返す"         │   │
│   │  (ツール不要 → ループ終了)                          │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   最終レスポンス: "このファイルは..."                       │
└─────────────────────────────────────────────────────────────┘
```

## 実装の流れ

### 1. ユーザー入力を受け取る

```python
# main.py
user_input = input("\n> ").strip()
response = agent.run(user_input)
```

### 2. エージェントループを開始

```python
# agent.py - run() メソッド
def run(self, user_input: str) -> str:
    # ユーザーメッセージを履歴に追加
    self.message_history.add_user_message(user_input)

    # 最大イテレーション数までループ
    for iteration in range(1, self.max_iterations + 1):
        # THINK → ACT → OBSERVE
        ...
```

### 3. THINK フェーズ

LLM を呼び出して、次のアクションを決定させます。

```python
# agent.py
response: LLMResponse = self.llm_client.chat(
    messages=self.message_history.get_messages(),  # これまでの会話履歴
    tools=self.tool_registry.get_tool_definitions(),  # 使えるツール一覧
)
```

LLM は以下のいずれかを返します：
- **ツール呼び出し** → ACT フェーズへ
- **テキストのみ** → ループ終了

### 4. ACT フェーズ

LLM が選んだツールを実際に実行します。

```python
# agent.py
for tool_call in response.tool_calls:
    result = self.tool_registry.execute(
        tool_call.name,   # "read_file"
        tool_call.input,  # {"path": "hello.py"}
    )
```

**重要**: LLM は「read_file を呼びたい」と言うだけで、実際にファイルを読むのはホスト側（Python）です。

### 5. OBSERVE フェーズ

ツールの実行結果を収集し、次のイテレーションに渡します。

```python
# agent.py
self.message_history.add_tool_result(
    tool_call.id,
    result,
    tool_name=tool_call.name,
)
```

### 6. ループ終了条件

```python
# agent.py
if response.stop_reason == "end_turn":
    # LLM がツールを使わずにテキストで回答 → 完了
    return response.text or ""
```

## なぜループが必要か？

単発の LLM 呼び出しでは複雑なタスクを完了できません。

**例**: "src/ 以下の Python ファイルを全て読んで、バグを探して修正して"

1. Iteration 1: `list_files(path="src/")` でファイル一覧を取得
2. Iteration 2: `read_file(path="src/main.py")` で最初のファイルを読む
3. Iteration 3: `read_file(path="src/utils.py")` で次のファイルを読む
4. Iteration 4: バグを発見、`edit_file(...)` で修正
5. Iteration 5: 修正完了、テキストで報告

このように、複数のステップを経て初めてタスクが完了します。

## 無限ループ防止

```python
# agent.py
DEFAULT_MAX_ITERATIONS = 10

for iteration in range(1, self.max_iterations + 1):
    ...

# 最大イテレーション数に達したらエラー
raise RuntimeError(f"Max iterations ({self.max_iterations}) reached")
```

## コード全体の流れ

```
main.py                          agent.py
────────                         ────────

user_input = input(">")
      │
      ▼
agent.run(user_input) ────────▶  run(user_input):
                                     │
                                     ▼
                                 message_history.add_user_message()
                                     │
                                     ▼
                                 for iteration in range(max):
                                     │
                                     ├─▶ THINK: llm_client.chat()
                                     │       │
                                     │       ▼
                                     │   response.tool_calls あり?
                                     │       │
                                     │   Yes ├─▶ ACT: tool_registry.execute()
                                     │       │       │
                                     │       │       ▼
                                     │       │   OBSERVE: message_history.add_tool_result()
                                     │       │       │
                                     │       │       └─▶ 次のイテレーションへ
                                     │       │
                                     │   No  └─▶ return response.text (ループ終了)
                                     │
      ◀─────────────────────────  return final_response
```

## 関連ドキュメント

- [02-tool-use.md](./02-tool-use.md) - LLM がツールを呼び出す仕組み
- [06-stop-reason.md](./06-stop-reason.md) - ループ終了条件の詳細
