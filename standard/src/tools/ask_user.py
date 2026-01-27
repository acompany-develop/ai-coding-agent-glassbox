from .base import Tool


class AskUserTool(Tool):
    """ユーザーに質問するツール

    エージェントがユーザーに質問し、回答を待つ。
    Human-in-the-loopパターンの実装。

    学びのポイント:
    - Human-in-the-loopで安全性を確保
    - 危険な操作の前にユーザー確認
    - 曖昧な指示の明確化
    """

    @property
    def name(self) -> str:
        return "ask_user"

    @property
    def description(self) -> str:
        return (
            "Ask the user a question and wait for their response. "
            "Use this when you need clarification, confirmation for dangerous operations, "
            "or when the user's intent is unclear. "
            "You can optionally provide choices for the user to select from."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of choices for the user to select from",
                },
            },
            "required": ["question"],
        }

    def execute(self, question: str, options: list[str] | None = None, **kwargs) -> str:
        """ユーザーに質問する

        Args:
            question: 質問内容
            options: 選択肢のリスト（オプション）

        Returns:
            ユーザーの回答
        """
        print(f"\n{'='*50}")
        print(f"[ASK USER] {question}")
        print(f"{'='*50}")

        if options:
            # 選択肢がある場合
            for i, option in enumerate(options, 1):
                print(f"  {i}. {option}")
            print()

            while True:
                try:
                    response = input("選択してください (番号を入力): ").strip()

                    # 番号で選択
                    if response.isdigit():
                        index = int(response) - 1
                        if 0 <= index < len(options):
                            selected = options[index]
                            print(f"[ASK USER] User selected: {selected}")
                            return selected

                    # テキストで直接入力も許可
                    if response in options:
                        print(f"[ASK USER] User selected: {response}")
                        return response

                    print(f"1から{len(options)}の番号を入力してください。")

                except (KeyboardInterrupt, EOFError):
                    return "[User cancelled the question]"
        else:
            # 自由回答
            try:
                response = input("回答: ").strip()
                print(f"[ASK USER] User responded: {response}")
                return response
            except (KeyboardInterrupt, EOFError):
                return "[User cancelled the question]"
