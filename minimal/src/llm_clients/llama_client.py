import json
import os
import uuid

import httpx

from .base import BaseLLMClient, LLMResponse, ToolCall


class LlamaClient(BaseLLMClient):
    """Llama APIクライアント（Ollama経由）

    Llama 3.1 8B は Tool Use（Function Calling）に対応していないため、
    JSON 形式でツール呼び出しを出力させる方式を採用。

    学びのポイント:
    - Tool Use 非対応モデルでもエージェント構築は可能
    - システムプロンプトで JSON フォーマットを強制
    - レスポンスのパースでツール呼び出しを抽出
    """

    DEFAULT_MODEL = "llama3.1:8b"
    DEFAULT_BASE_URL = "http://localhost:11434"

    SYSTEM_PROMPT_TEMPLATE = '''You are a helpful coding assistant. You have access to the following tools:

{tool_definitions}

When you need to use a tool, respond with a JSON object in this exact format:
{{
  "thought": "your reasoning about what to do",
  "tool_call": {{
    "name": "tool_name",
    "input": {{ "param1": "value1" }}
  }}
}}

When you have completed the task and want to respond to the user (no more tool calls needed), respond with:
{{
  "thought": "your reasoning",
  "response": "your final response to the user"
}}

IMPORTANT:
- Always respond with valid JSON only, no other text
- Use "tool_call" when you need to use a tool
- Use "response" when you're done and want to reply to the user
- Never include both "tool_call" and "response" in the same message'''

    def __init__(
        self,
        api_key: str | None = None,  # 互換性のため（Ollamaは不要）
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.model = model or self.DEFAULT_MODEL
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL", self.DEFAULT_BASE_URL)
        self.client = httpx.Client(timeout=120.0)

    @property
    def provider_name(self) -> str:
        return "Llama (Ollama)"

    def _format_tools_for_prompt(self, tools: list[dict]) -> str:
        """ツール定義をシステムプロンプト用にフォーマット"""
        tool_descriptions = []
        for tool in tools:
            desc = f"- {tool['name']}: {tool['description']}\n"
            desc += f"  Parameters: {json.dumps(tool['input_schema'], indent=2)}"
            tool_descriptions.append(desc)
        return "\n\n".join(tool_descriptions)

    def _convert_messages_to_ollama_format(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> list[dict]:
        """メッセージを Ollama 形式に変換"""
        ollama_messages = []

        # システムプロンプトを先頭に追加
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
            tool_definitions=self._format_tools_for_prompt(tools)
        )
        ollama_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                # tool_result の場合
                if isinstance(content, list) and content and content[0].get("type") == "tool_result":
                    for item in content:
                        # ツール結果を JSON で伝える
                        result_json = json.dumps({
                            "tool_result": {
                                "name": item.get("tool_name", "unknown"),
                                "result": item["content"]
                            }
                        }, ensure_ascii=False)
                        ollama_messages.append({"role": "user", "content": result_json})
                else:
                    ollama_messages.append({"role": "user", "content": content})

            elif role == "assistant":
                # アシスタントメッセージ
                if isinstance(content, str):
                    ollama_messages.append({"role": "assistant", "content": content})
                elif isinstance(content, dict):
                    # 保存された JSON 形式
                    ollama_messages.append({
                        "role": "assistant",
                        "content": json.dumps(content, ensure_ascii=False)
                    })

        return ollama_messages

    def _parse_llm_response(self, response_text: str) -> tuple[str | None, list[ToolCall], str]:
        """LLM のレスポンスをパース

        Returns:
            tuple: (text, tool_calls, stop_reason)
        """
        try:
            # JSON をパース
            response_text = response_text.strip()

            # コードブロックで囲まれている場合は除去
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                # 最初と最後の ``` を除去
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                response_text = "\n".join(lines)

            data = json.loads(response_text)

            thought = data.get("thought", "")

            # tool_call がある場合
            if "tool_call" in data and data["tool_call"]:
                tool_call_data = data["tool_call"]
                tool_calls = [
                    ToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        name=tool_call_data["name"],
                        input=tool_call_data.get("input", {}),
                    )
                ]
                return thought, tool_calls, "tool_use"

            # response がある場合（タスク完了）
            if "response" in data:
                return data["response"], [], "end_turn"

            # どちらもない場合はテキストとして返す
            return response_text, [], "end_turn"

        except json.JSONDecodeError as e:
            # JSON パースに失敗した場合はそのままテキストとして返す
            print(f"[LLM] Warning: Failed to parse JSON response: {e}")
            return response_text, [], "end_turn"

    def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
    ) -> LLMResponse:
        print(f"\n[LLM] Sending request to {self.provider_name}...")
        print(f"[LLM] Model: {self.model}")
        print(f"[LLM] Messages count: {len(messages)}")
        print(f"[LLM] Tools count: {len(tools)}")

        ollama_messages = self._convert_messages_to_ollama_format(messages, tools)

        # Ollama API を呼び出し
        try:
            response = self.client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": ollama_messages,
                    "stream": False,
                    "format": "json",  # JSON モードを強制
                },
            )
            response.raise_for_status()
            result = response.json()
        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to call Ollama API: {e}")

        response_text = result.get("message", {}).get("content", "")
        print(f"[LLM] Raw response: {response_text[:200]}...")

        # レスポンスをパース
        text, tool_calls, stop_reason = self._parse_llm_response(response_text)

        print(f"[LLM] Response stop_reason: {stop_reason}")

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw_response=result,
        )

    def format_tool_result(self, tool_call_id: str, result: str, tool_name: str = "unknown") -> dict:
        """ツール結果をフォーマット"""
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
        """アシスタントメッセージをフォーマット"""
        # Llama の場合、JSON レスポンスをそのまま保存
        if response.tool_calls:
            content = {
                "thought": response.text or "",
                "tool_call": {
                    "name": response.tool_calls[0].name,
                    "input": response.tool_calls[0].input,
                }
            }
        else:
            content = {
                "thought": "",
                "response": response.text or "",
            }

        return {
            "role": "assistant",
            "content": content,
        }
