# 03. LLM クライアントの抽象化

異なる LLM プロバイダー（Gemini, Llama）を統一インターフェースで扱うための設計です。

## なぜ抽象化が必要か

各プロバイダーは独自の API 形式を持っています：

| 項目 | Gemini | Llama (Ollama) |
|------|--------|----------------|
| SDK | `google-genai` | `httpx` (HTTP直接) |
| ツール形式 | `types.FunctionDeclaration` | JSON in prompt |
| レスポンス | `response.candidates[0].content.parts` | HTTP JSON |
| ツール結果 | `Part.from_function_response()` | JSON string |

これらの差異を吸収し、エージェントループからは統一された方法で呼び出せるようにします。

## クラス階層

```
BaseLLMClient (抽象クラス)
    │
    ├── GeminiClient
    │     └── Native Function Calling
    │
    └── LlamaClient
          └── JSON モード（プロンプト指示）
```

## 抽象基底クラス

```python
# llm_clients/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ToolCall:
    """ツール呼び出し情報"""
    id: str      # ユニークID
    name: str    # ツール名
    input: dict  # 引数

@dataclass
class LLMResponse:
    """LLMレスポンスの統一形式"""
    text: str | None           # テキスト出力
    tool_calls: list[ToolCall] # ツール呼び出しリスト
    stop_reason: str           # "tool_use" or "end_turn"
    raw_response: Any          # プロバイダー固有のレスポンス

class BaseLLMClient(ABC):
    """LLMクライアントの抽象基底クラス"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """プロバイダー名を返す"""
        pass

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
    ) -> LLMResponse:
        """LLMにメッセージを送信し、レスポンスを取得"""
        pass

    @abstractmethod
    def format_tool_result(
        self,
        tool_call_id: str,
        result: str,
        tool_name: str = "unknown",
    ) -> dict:
        """ツール結果をプロバイダー固有形式にフォーマット"""
        pass

    @abstractmethod
    def format_assistant_message(self, response: LLMResponse) -> dict:
        """アシスタントメッセージをフォーマット"""
        pass
```

## Gemini クライアント実装

```python
# llm_clients/gemini_client.py
class GeminiClient(BaseLLMClient):
    """Google Gemini APIクライアント"""

    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key)
        self.model = model or self.DEFAULT_MODEL

    def chat(self, messages, tools, system=None) -> LLMResponse:
        # 1. メッセージを Gemini 形式に変換
        gemini_contents = self._convert_messages_to_gemini_format(messages)

        # 2. ツールを Gemini 形式に変換
        gemini_tools = self._convert_tools_to_gemini_format(tools)

        # 3. API 呼び出し
        response = self.client.models.generate_content(
            model=self.model,
            contents=gemini_contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                tools=gemini_tools,
            ),
        )

        # 4. レスポンスを統一形式に変換
        return self._parse_response(response)
```

### Gemini のツール変換

```python
def _convert_tools_to_gemini_format(self, tools: list[dict]) -> list[types.Tool]:
    function_declarations = []

    for tool in tools:
        func_decl = types.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters_json_schema=tool["input_schema"],
        )
        function_declarations.append(func_decl)

    return [types.Tool(function_declarations=function_declarations)]
```

### Gemini のレスポンス解析

```python
def _parse_response(self, response) -> LLMResponse:
    text = None
    tool_calls = []

    for part in response.candidates[0].content.parts:
        if part.text:
            text = part.text
        elif part.function_call:
            tool_calls.append(ToolCall(
                id=f"call_{uuid.uuid4().hex[:8]}",  # Gemini は ID を返さない
                name=part.function_call.name,
                input=dict(part.function_call.args),
            ))

    stop_reason = "tool_use" if tool_calls else "end_turn"

    return LLMResponse(
        text=text,
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        raw_response=response,
    )
```

## Llama クライアント実装

Llama 3.1 8B は Function Calling 非対応のため、JSON モードでシミュレートします。

```python
# llm_clients/llama_client.py
class LlamaClient(BaseLLMClient):
    """Llama APIクライアント（Ollama経由）"""

    DEFAULT_MODEL = "llama3.1:8b"
    DEFAULT_BASE_URL = "http://localhost:11434"

    # システムプロンプトでツール使用方法を指示
    SYSTEM_PROMPT_TEMPLATE = '''You are a helpful coding assistant.
Available tools:
{tools_description}

When you need to use a tool, respond with JSON:
{{
  "thought": "your reasoning",
  "tool_call": {{"name": "tool_name", "input": {{...}}}}
}}

When you have the final answer:
{{
  "thought": "your reasoning",
  "response": "your final response"
}}

ALWAYS respond with valid JSON only.'''
```

### Llama のツール定義埋め込み

```python
def _build_system_prompt(self, tools: list[dict]) -> str:
    tools_desc = []
    for tool in tools:
        params = tool["input_schema"].get("properties", {})
        param_str = ", ".join(
            f"{k}: {v.get('type', 'any')}"
            for k, v in params.items()
        )
        tools_desc.append(
            f"- {tool['name']}({param_str}): {tool['description']}"
        )

    return self.SYSTEM_PROMPT_TEMPLATE.format(
        tools_description="\n".join(tools_desc)
    )
```

### Llama のレスポンス解析

```python
def _parse_response(self, response_text: str) -> LLMResponse:
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        # JSON パースエラー → テキストとして扱う
        return LLMResponse(
            text=response_text,
            tool_calls=[],
            stop_reason="end_turn",
            raw_response=response_text,
        )

    if "tool_call" in data:
        # ツール呼び出し
        tc = data["tool_call"]
        return LLMResponse(
            text=data.get("thought"),
            tool_calls=[ToolCall(
                id=f"call_{uuid.uuid4().hex[:8]}",
                name=tc["name"],
                input=tc.get("input", {}),
            )],
            stop_reason="tool_use",
            raw_response=data,
        )
    else:
        # 最終レスポンス
        return LLMResponse(
            text=data.get("response", data.get("thought", "")),
            tool_calls=[],
            stop_reason="end_turn",
            raw_response=data,
        )
```

## ファクトリ関数

```python
# llm_clients/__init__.py
def create_llm_client(
    provider: str,
    api_key: str | None = None,
    model: str | None = None,
) -> BaseLLMClient:
    """プロバイダー名からLLMクライアントを作成"""
    provider = provider.lower()

    if provider == "gemini":
        return GeminiClient(api_key=api_key, model=model)
    elif provider == "llama":
        return LlamaClient(api_key=api_key, model=model)
    else:
        raise ValueError(f"Unknown provider: {provider}")
```

## 使用例

```python
# main.py
llm_client = create_llm_client(provider="gemini")

# agent.py - プロバイダーを意識せずに呼び出せる
response = self.llm_client.chat(
    messages=self.message_history.get_messages(),
    tools=self.tool_registry.get_tool_definitions(),
)
```

## Native Function Calling vs JSON モード

| 項目 | Native (Gemini) | JSON モード (Llama) |
|------|-----------------|---------------------|
| 信頼性 | 高（API が保証） | 中（パースエラーの可能性） |
| 設定 | ツール定義を送信 | プロンプトで指示 |
| 型安全 | あり | なし（文字列として扱う） |
| 複数ツール | 一度に複数可 | 一度に1つが安全 |

## 関連ドキュメント

- [02-tool-use.md](./02-tool-use.md) - Tool Use の全体像
- [05-message-history.md](./05-message-history.md) - メッセージ形式の詳細
