# 02. Tool Use（Function Calling）

LLM は直接ファイルを読み書きできません。代わりに「どのツールをどう呼ぶか」を返し、ホスト側が実際の処理を行います。

## 基本的な流れ

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│    User     │         │     LLM     │         │    Host     │
│             │         │             │         │  (Python)   │
└──────┬──────┘         └──────┬──────┘         └──────┬──────┘
       │                       │                       │
       │  "hello.py を読んで"  │                       │
       │──────────────────────▶│                       │
       │                       │                       │
       │                       │ ツール定義を確認       │
       │                       │ read_file が使えそう  │
       │                       │                       │
       │                       │  tool_call:           │
       │                       │  name: read_file      │
       │                       │  input: {path: ...}   │
       │                       │──────────────────────▶│
       │                       │                       │
       │                       │                       │ ファイルを実際に読む
       │                       │                       │
       │                       │  tool_result:         │
       │                       │  "def greet(): ..."   │
       │                       │◀──────────────────────│
       │                       │                       │
       │  "このファイルは..."   │                       │
       │◀──────────────────────│                       │
       │                       │                       │
```

## Step 1: ツール定義の送信

エージェント起動時に、利用可能なツールの定義を LLM に送信します。

```python
# tool_registry.py
def get_tool_definitions(self) -> list[dict]:
    return [tool.to_dict() for tool in self.tools.values()]
```

送信されるツール定義の例：

```json
{
  "name": "read_file",
  "description": "Read the contents of a file at the specified path.",
  "input_schema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "The path to the file to read"
      }
    },
    "required": ["path"]
  }
}
```

この定義は LLM への「説明書」です。LLM はこれを読んで：
- どんなツールが使えるか
- 各ツールに何を渡せばいいか

を理解します。

## Step 2: LLM がツール呼び出しを決定

ユーザーが「hello.py を読んで」と入力すると、LLM は以下のようなレスポンスを返します：

```python
# LLMResponse (gemini_client.py より)
@dataclass
class LLMResponse:
    text: str | None           # テキストレスポンス（あれば）
    tool_calls: list[ToolCall] # ツール呼び出しのリスト
    stop_reason: str           # "tool_use" or "end_turn"
    raw_response: Any          # プロバイダー固有のレスポンス

@dataclass
class ToolCall:
    id: str      # "call_abc123"
    name: str    # "read_file"
    input: dict  # {"path": "hello.py"}
```

**重要ポイント**:
- LLM は「read_file を呼びたい」という **意図** を返すだけ
- 実際にファイルを読むわけではない
- ホスト側が安全に実行するかどうかを判断できる

## Step 3: ホスト側でツール実行

```python
# agent.py
for tool_call in response.tool_calls:
    result = self.tool_registry.execute(
        tool_call.name,     # "read_file"
        tool_call.input,    # {"path": "hello.py"}
    )
```

```python
# tool_registry.py
def execute(self, tool_name: str, tool_input: dict) -> str:
    if tool_name not in self.tools:
        return f"Error: Unknown tool '{tool_name}'"

    tool = self.tools[tool_name]
    return tool.execute(**tool_input)
```

```python
# tools/read_file.py
class ReadFileTool(Tool):
    def execute(self, path: str) -> str:
        try:
            with open(path, "r") as f:
                return f.read()
        except FileNotFoundError:
            return f"Error: File not found: {path}"
```

## Step 4: 結果を LLM に返送

ツールの実行結果をメッセージ履歴に追加し、次の LLM 呼び出しで送信します。

```python
# agent.py
self.message_history.add_tool_result(
    tool_call.id,
    result,
    tool_name=tool_call.name,
)
```

## プロバイダーごとの形式の違い

### Gemini

```python
# Gemini はネイティブの Function Calling をサポート
# function_call / function_response として処理

# ツール呼び出しの受け取り
part.function_call.name  # "read_file"
part.function_call.args  # {"path": "hello.py"}

# 結果の送信
types.Part.from_function_response(
    name="read_file",
    response={"result": "def greet(): ..."},
)
```

### Llama（JSON モード）

Llama 3.1 8B は Function Calling に非対応のため、JSON 形式でシミュレートします。

```python
# システムプロンプトで形式を指定
SYSTEM_PROMPT = '''
When you need to use a tool, respond with JSON:
{
  "thought": "your reasoning",
  "tool_call": {"name": "tool_name", "input": {...}}
}
'''

# LLM のレスポンスを JSON としてパース
data = json.loads(response_text)
if "tool_call" in data:
    tool_name = data["tool_call"]["name"]
    tool_input = data["tool_call"]["input"]
```

## ツール定義の書き方

良いツール定義は LLM が正しくツールを選択するために重要です。

```python
# tools/read_file.py
class ReadFileTool(Tool):
    name = "read_file"
    description = "Read the contents of a file at the specified path."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path to the file to read"
            }
        },
        "required": ["path"],
    }
```

**ポイント**:
- `description`: ツールの用途を明確に
- `properties.*.description`: 各パラメータの意味を説明
- `required`: 必須パラメータを明示

## セキュリティ上の考慮

LLM は任意のツールを任意の引数で呼び出そうとする可能性があります。

```python
# 悪意のある呼び出しの例
tool_call.name = "execute_command"
tool_call.input = {"command": "rm -rf /"}
```

対策：
1. **ツール側でバリデーション**
2. **危険なコマンドのブロック**
3. **サンドボックス環境での実行**

```python
# tools/execute_command.py
BLOCKED_COMMANDS = ["rm -rf", "sudo", "chmod 777"]

def execute(self, command: str) -> str:
    for blocked in BLOCKED_COMMANDS:
        if blocked in command:
            return f"Error: Command contains blocked pattern: {blocked}"
    ...
```

## 関連ドキュメント

- [03-llm-clients.md](./03-llm-clients.md) - プロバイダーごとの実装詳細
- [04-tools.md](./04-tools.md) - ツールの実装方法
