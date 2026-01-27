# A2. Tool Use の実装方式

LLM にツールを使わせる方式は複数あります。各方式の特徴と実装例を解説します。

## 方式の比較

| 方式 | 信頼性 | 対応LLM | 実装難易度 |
|------|--------|---------|-----------|
| Native Function Calling | 高 | GPT-4, Claude, Gemini | 低 |
| JSON モード | 中 | 全LLM | 中 |
| XML/タグベース | 中 | 全LLM | 中 |
| ReAct プロンプト | 低〜中 | 全LLM | 低 |

---

## 1. Native Function Calling

LLM プロバイダーが公式にサポートする方式。API レベルでツール定義を送信し、構造化されたレスポンスを受け取ります。

### 対応プロバイダー

| プロバイダー | API 名称 | リリース時期 |
|-------------|---------|-------------|
| OpenAI | Function Calling | 2023年6月 |
| Anthropic | Tool Use | 2024年4月 |
| Google | Function Calling | 2023年12月 |

### OpenAI の実装

```python
import openai

# ツール定義
tools = [{
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read the contents of a file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"}
            },
            "required": ["path"]
        }
    }
}]

# API 呼び出し
response = openai.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Read hello.py"}],
    tools=tools,
)

# レスポンス解析
if response.choices[0].finish_reason == "tool_calls":
    tool_call = response.choices[0].message.tool_calls[0]
    print(tool_call.function.name)       # "read_file"
    print(tool_call.function.arguments)  # '{"path": "hello.py"}'
```

### Anthropic (Claude) の実装

```python
import anthropic

client = anthropic.Anthropic()

# ツール定義
tools = [{
    "name": "read_file",
    "description": "Read the contents of a file",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"}
        },
        "required": ["path"]
    }
}]

# API 呼び出し
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "Read hello.py"}],
)

# レスポンス解析
for block in response.content:
    if block.type == "tool_use":
        print(block.name)   # "read_file"
        print(block.input)  # {"path": "hello.py"}
```

### Google Gemini の実装

```python
from google import genai
from google.genai import types

client = genai.Client(api_key="...")

# ツール定義
tools = [types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="read_file",
        description="Read the contents of a file",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"}
            },
            "required": ["path"]
        },
    )
])]

# API 呼び出し
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[types.Content(
        role="user",
        parts=[types.Part.from_text("Read hello.py")]
    )],
    config=types.GenerateContentConfig(tools=tools),
)

# レスポンス解析
for part in response.candidates[0].content.parts:
    if part.function_call:
        print(part.function_call.name)  # "read_file"
        print(part.function_call.args)  # {"path": "hello.py"}
```

### 特徴

**メリット:**
- API が構造化レスポンスを保証
- パースエラーが発生しない
- 型安全

**デメリット:**
- 特定プロバイダーに依存
- 対応していない LLM では使えない

---

## 2. JSON モード

LLM に JSON 形式で出力させ、ホスト側でパースする方式。Native Function Calling 非対応の LLM で使用します。

### システムプロンプト

```
You are a helpful assistant with access to tools.

Available tools:
- read_file(path: string): Read the contents of a file
- write_file(path: string, content: string): Write content to a file

When you need to use a tool, respond with JSON:
{
  "thought": "your reasoning",
  "tool_call": {
    "name": "tool_name",
    "input": {"param1": "value1"}
  }
}

When you have the final answer:
{
  "thought": "your reasoning",
  "response": "your answer"
}

ALWAYS respond with valid JSON only.
```

### 実装

```python
import json

def parse_json_response(text: str) -> dict:
    """JSON レスポンスをパース"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # JSON 部分を抽出して再試行
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise

def llama_chat(messages: list, tools: list) -> dict:
    """Llama を JSON モードで使用"""
    # ツール定義をプロンプトに埋め込み
    system_prompt = build_system_prompt(tools)

    response = ollama.chat(
        model="llama3.1:8b",
        messages=[
            {"role": "system", "content": system_prompt},
            *messages,
        ],
    )

    return parse_json_response(response["message"]["content"])
```

### Llama での出力例

```json
{
  "thought": "ユーザーが hello.py の内容を知りたがっている。read_file ツールを使う。",
  "tool_call": {
    "name": "read_file",
    "input": {"path": "hello.py"}
  }
}
```

### 特徴

**メリット:**
- 任意の LLM で使用可能
- ローカル LLM にも対応
- プロバイダー非依存

**デメリット:**
- パースエラーの可能性
- プロンプト設計が重要
- 出力の一貫性が低い

---

## 3. XML/タグベース

XML タグで構造を表現する方式。Claude が以前使用していた方式です。

### プロンプト

```
When you need to use a tool, format your response like this:

<thinking>
Your reasoning here
</thinking>

<tool_call>
<name>read_file</name>
<input>
<path>hello.py</path>
</input>
</tool_call>

When you have the final answer:

<thinking>
Your reasoning here
</thinking>

<response>
Your answer here
</response>
```

### 実装

```python
import re
from dataclasses import dataclass

@dataclass
class ParsedResponse:
    thinking: str | None
    tool_call: dict | None
    response: str | None

def parse_xml_response(text: str) -> ParsedResponse:
    """XML 形式のレスポンスをパース"""
    thinking = extract_tag(text, "thinking")
    response = extract_tag(text, "response")

    tool_call = None
    tool_call_text = extract_tag(text, "tool_call")
    if tool_call_text:
        tool_call = {
            "name": extract_tag(tool_call_text, "name"),
            "input": parse_input_tag(extract_tag(tool_call_text, "input")),
        }

    return ParsedResponse(thinking, tool_call, response)

def extract_tag(text: str, tag: str) -> str | None:
    """タグの内容を抽出"""
    pattern = f"<{tag}>(.*?)</{tag}>"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else None
```

### 出力例

```xml
<thinking>
ユーザーが hello.py の内容を知りたがっている。
ファイルを読み込むために read_file ツールを使用する。
</thinking>

<tool_call>
<name>read_file</name>
<input>
<path>hello.py</path>
</input>
</tool_call>
```

### 特徴

**メリット:**
- 構造が明確
- ネストした構造を表現しやすい
- Claude が得意（学習データに多い）

**デメリット:**
- タグの閉じ忘れエラー
- JSON より冗長

---

## 4. ReAct プロンプト

Thought/Action/Observation を明示的に出力させる方式。

### プロンプト

```
You are a helpful assistant. You can use the following tools:

- read_file(path): Read file contents
- write_file(path, content): Write to file

Use this format:

Thought: I need to think about what to do
Action: tool_name(param1="value1", param2="value2")
Observation: [Result will be provided]
... (repeat Thought/Action/Observation as needed)
Thought: I now have the final answer
Final Answer: Your response to the user
```

### 実装

```python
import re

def parse_react_response(text: str) -> tuple[str, dict | None]:
    """ReAct 形式のレスポンスをパース"""
    # Action を抽出
    action_match = re.search(
        r'Action:\s*(\w+)\((.*?)\)',
        text,
        re.DOTALL
    )

    if action_match:
        name = action_match.group(1)
        args_str = action_match.group(2)
        args = parse_args(args_str)  # "path='hello.py'" → {"path": "hello.py"}
        return text, {"name": name, "input": args}

    # Final Answer を抽出
    final_match = re.search(r'Final Answer:\s*(.*)', text, re.DOTALL)
    if final_match:
        return final_match.group(1).strip(), None

    return text, None
```

### 出力例

```
Thought: ユーザーが hello.py の内容を知りたがっている。
まずファイルを読み込む必要がある。

Action: read_file(path="hello.py")
```

### 特徴

**メリット:**
- 思考過程が明示的
- 古い LLM でも動作
- デバッグしやすい

**デメリット:**
- パースが複雑
- 形式の揺れが大きい

---

## 方式の選び方

```
                    ┌─────────────────────────────────────┐
                    │   使用する LLM は？                  │
                    └─────────────────────────────────────┘
                                   │
                   ┌───────────────┴───────────────┐
                   │                               │
                   ▼                               ▼
        ┌─────────────────┐             ┌─────────────────┐
        │ GPT-4, Claude,  │             │ Llama, Mistral, │
        │ Gemini          │             │ その他ローカル   │
        └─────────────────┘             └─────────────────┘
                   │                               │
                   ▼                               ▼
        ┌─────────────────┐             ┌─────────────────┐
        │ Native Function │             │ JSON モード      │
        │ Calling を使用  │             │ を使用          │
        └─────────────────┘             └─────────────────┘
```

### 推奨

| シチュエーション | 推奨方式 |
|-----------------|---------|
| 本番環境（信頼性重視） | Native Function Calling |
| マルチプロバイダー対応 | JSON モード + Native のハイブリッド |
| ローカル LLM | JSON モード |
| 古い LLM | ReAct プロンプト |

---

## 本実装での採用

### Gemini: Native Function Calling

```python
# gemini_client.py
gemini_tools = [types.Tool(function_declarations=[...])]

response = client.models.generate_content(
    model=self.model,
    contents=gemini_contents,
    config=types.GenerateContentConfig(tools=gemini_tools),
)
```

### Llama: JSON モード

```python
# llama_client.py
SYSTEM_PROMPT = '''
When you need to use a tool, respond with JSON:
{
  "thought": "...",
  "tool_call": {"name": "...", "input": {...}}
}
'''
```

この組み合わせにより、Native Function Calling 対応 LLM では高い信頼性を、非対応 LLM でも動作可能な設計になっています。

---

## 参考リンク

- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)
- [Anthropic Tool Use Documentation](https://docs.anthropic.com/claude/docs/tool-use)
- [Google Gemini Function Calling](https://ai.google.dev/gemini-api/docs/function-calling)
