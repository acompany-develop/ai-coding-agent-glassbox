from .colors import print_history


class MessageHistory:
    """会話履歴を管理するクラス

    各プロバイダー共通のメッセージ形式で履歴を管理する。
    LLMクライアント側で適切な形式に変換される。
    """

    def __init__(self):
        self.messages: list[dict] = []

    def add_user_message(self, content: str) -> None:
        """ユーザーメッセージを追加

        Args:
            content: ユーザーの入力テキスト
        """
        self.messages.append({"role": "user", "content": content})
        print_history(f"Added user message: {content[:50]}...")

    def add_raw_message(self, message: dict) -> None:
        """生のメッセージを追加（プロバイダー固有形式）

        Args:
            message: メッセージ辞書
        """
        self.messages.append(message)
        print_history(f"Added {message.get('role', 'unknown')} message")

    def add_tool_result(
        self,
        tool_use_id: str,
        result: str,
        tool_name: str = "unknown",
    ) -> None:
        """ツール実行結果を追加

        プロバイダーによって形式が異なるため、共通形式で保存し、
        LLMクライアント側で変換する。

        Args:
            tool_use_id: ツール呼び出しのID
            result: ツール実行結果の文字列
            tool_name: ツール名（Gemini用）
        """
        self.messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "content": result,
            }],
        })
        print_history(f"Added tool result for {tool_use_id} ({tool_name})")

    def get_messages(self) -> list[dict]:
        """メッセージ履歴のコピーを取得

        Returns:
            メッセージリストのコピー
        """
        return self.messages.copy()

    def clear(self) -> None:
        """履歴をクリア"""
        self.messages = []
        print_history("Cleared message history")
