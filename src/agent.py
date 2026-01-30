from .colors import (
    cyan, yellow, magenta, blue, gray, bold,
    print_agent, print_think, print_act, print_observe,
    print_separator, print_header,
)
from .llm_clients import BaseLLMClient, LLMResponse
from .message_history import MessageHistory
from .tool_registry import ToolRegistry


class Agent:
    """エージェントループを実行するコアクラス

    Think → Act → Observe のサイクルを繰り返し、
    ユーザーのリクエストを達成する。

    - THINK: LLMを呼び出し、次のアクションを決定
    - ACT: ツールを実行
    - OBSERVE: 結果を収集し、次のイテレーションに渡す
    """

    DEFAULT_MAX_ITERATIONS = 10

    def __init__(
        self,
        llm_client: BaseLLMClient,
        tool_registry: ToolRegistry,
        max_iterations: int | None = None,
    ):
        """エージェントを初期化

        Args:
            llm_client: LLM APIクライアント
            tool_registry: 利用可能なツールのレジストリ
            max_iterations: 最大イテレーション数（無限ループ防止）
        """
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations or self.DEFAULT_MAX_ITERATIONS
        self.message_history = MessageHistory()

    def run(self, user_input: str) -> str:
        """エージェントループを実行

        Args:
            user_input: ユーザーからの入力

        Returns:
            最終的なレスポンステキスト

        Raises:
            RuntimeError: 最大イテレーション数に達した場合
        """
        print()
        print_header("Starting agent loop")
        print_agent(f"Provider: {cyan(self.llm_client.provider_name)}")
        print_agent(f"User input: {user_input}")

        self.message_history.add_user_message(user_input)

        for iteration in range(1, self.max_iterations + 1):
            print()
            print_separator()
            print_agent(f"Iteration {bold(str(iteration))}/{self.max_iterations}")
            print_separator()

            # ========== THINK ==========
            print_think("Calling LLM for next action...")

            response: LLMResponse = self.llm_client.chat(
                messages=self.message_history.get_messages(),
                tools=self.tool_registry.get_tool_definitions(),
            )

            # アシスタントのレスポンスを履歴に追加
            assistant_msg = self.llm_client.format_assistant_message(response)
            self.message_history.add_raw_message(assistant_msg)

            # レスポンス内容を表示
            self._print_response_content(response)

            # 終了条件: ツール呼び出しなし（end_turn）
            if response.stop_reason == "end_turn":
                print_think("LLM decided to respond without tools - ending loop")
                return response.text or ""

            # ========== ACT & OBSERVE ==========
            if not response.tool_calls:
                print_think("No tool calls found - ending loop")
                return response.text or ""

            for tool_call in response.tool_calls:
                # ========== ACT ==========
                print()
                print_act(f"Executing tool: {magenta(tool_call.name)}")
                print_act(f"Tool ID: {gray(tool_call.id)}")
                print_act(f"Input: {tool_call.input}")

                result = self.tool_registry.execute(
                    tool_call.name,
                    tool_call.input,
                )

                # ========== OBSERVE ==========
                result_preview = result[:200] + "..." if len(result) > 200 else result
                print()
                print_observe("Result preview:")
                print(gray(result_preview))

                # ツール結果を履歴に追加
                self.message_history.add_tool_result(
                    tool_call.id,
                    result,
                    tool_name=tool_call.name,
                )

        # 最大イテレーション数に達した場合
        raise RuntimeError(
            f"Max iterations ({self.max_iterations}) reached without completion"
        )

    def _print_response_content(self, response: LLMResponse) -> None:
        """レスポンス内容をデバッグ出力"""
        if response.text:
            text_preview = response.text[:100] + "..." if len(response.text) > 100 else response.text
            print_think(f"Text: {text_preview}")

        for tool_call in response.tool_calls:
            print_think(f"Tool call: {magenta(tool_call.name)}")

    def reset(self) -> None:
        """エージェントの状態をリセット"""
        self.message_history.clear()
        print_agent("Agent state reset")
