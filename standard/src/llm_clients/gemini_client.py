import os
import uuid
from dataclasses import dataclass, field

from google import genai
from google.genai import types

from ..colors import print_llm
from .base import BaseLLMClient, LLMResponse, ToolCall


@dataclass
class TextBlock:
    """テキストブロック（共通形式）"""
    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    """ツール使用ブロック（共通形式）"""
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


class GeminiClient(BaseLLMClient):
    """Google Gemini APIクライアント"""

    DEFAULT_MODEL = "gemini-2.5-flash"
    DEFAULT_SYSTEM_PROMPT = (
        "You are a helpful coding assistant. "
        "Use tools when needed to accomplish the user's request."
    )

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is required. "
                "Set it as an environment variable or pass it to the constructor."
            )

        self.client = genai.Client(api_key=self.api_key)
        self.model = model or self.DEFAULT_MODEL

    @property
    def provider_name(self) -> str:
        return "Gemini"

    def _convert_tools_to_gemini_format(self, tools: list[dict]) -> list[types.Tool]:
        """共通形式のツール定義をGemini形式に変換"""
        function_declarations = []

        for tool in tools:
            func_decl = types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters_json_schema=tool["input_schema"],
            )
            function_declarations.append(func_decl)

        return [types.Tool(function_declarations=function_declarations)]

    def _convert_messages_to_gemini_format(
        self,
        messages: list[dict],
    ) -> list[types.Content]:
        """共通形式のメッセージをGemini形式に変換"""
        gemini_contents = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                # tool_result の場合
                if isinstance(content, list) and content and content[0].get("type") == "tool_result":
                    parts = []
                    for item in content:
                        parts.append(types.Part.from_function_response(
                            name=item.get("tool_name", "unknown"),
                            response={"result": item["content"]},
                        ))
                    gemini_contents.append(types.Content(role="user", parts=parts))
                else:
                    gemini_contents.append(types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=content)],
                    ))

            elif role == "assistant":
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if hasattr(block, "type"):
                            if block.type == "text":
                                parts.append(types.Part.from_text(text=block.text))
                            elif block.type == "tool_use":
                                parts.append(types.Part.from_function_call(
                                    name=block.name,
                                    args=block.input,
                                ))
                    if parts:
                        gemini_contents.append(types.Content(role="model", parts=parts))
                else:
                    gemini_contents.append(types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=content)],
                    ))

        return gemini_contents

    def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
    ) -> LLMResponse:
        print()
        print_llm(f"Sending request to {self.provider_name}...")
        print_llm(f"Model: {self.model}")
        print_llm(f"Messages count: {len(messages)}")
        print_llm(f"Tools count: {len(tools)}")

        gemini_contents = self._convert_messages_to_gemini_format(messages)
        gemini_tools = self._convert_tools_to_gemini_format(tools) if tools else None

        config = types.GenerateContentConfig(
            system_instruction=system or self.DEFAULT_SYSTEM_PROMPT,
            tools=gemini_tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True  # 手動でfunction callを処理する
            ),
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=gemini_contents,
            config=config,
        )

        # 統一形式に変換
        text = None
        tool_calls = []

        # レスポンスからテキストとfunction callを抽出
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.text:
                    text = part.text
                elif part.function_call:
                    # Gemini はツールIDを返さないので生成
                    tool_calls.append(ToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        name=part.function_call.name,
                        input=dict(part.function_call.args) if part.function_call.args else {},
                    ))

        stop_reason = "tool_use" if tool_calls else "end_turn"
        print_llm(f"Response stop_reason: {stop_reason}")

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw_response=response,
        )

    def format_tool_result(self, tool_call_id: str, result: str, tool_name: str = "unknown") -> dict:
        """Gemini形式: function_response として追加"""
        return {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "tool_name": tool_name,
                "content": result,
            }],
        }

    def format_assistant_message(self, response: LLMResponse) -> dict:
        """アシスタントメッセージをフォーマット（共通形式で保存）"""
        content = []

        if response.text:
            content.append(TextBlock(type="text", text=response.text))

        for tc in response.tool_calls:
            content.append(ToolUseBlock(
                type="tool_use",
                id=tc.id,
                name=tc.name,
                input=tc.input,
            ))

        return {
            "role": "assistant",
            "content": content,
        }
