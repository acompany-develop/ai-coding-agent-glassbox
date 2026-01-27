from pathlib import Path

from .base import Tool


class EditFileTool(Tool):
    """ファイルを差分編集するツール

    指定された文字列を検索し、新しい文字列に置換する。
    Claude CodeのEditツールに相当。

    学びのポイント:
    - write_file（全体置換）と比較して、トークン効率が良い
    - 変更箇所のみ指定するため、安全性が高い
    - old_stringの一意性を要求することで、意図しない置換を防止
    """

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Edit a file by replacing a specific string with a new string. "
            "The old_string must appear exactly once in the file for the edit to succeed. "
            "Use an empty new_string to delete the old_string. "
            "This is more efficient than rewriting the entire file with write_file."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact string to find and replace (must appear exactly once)",
                },
                "new_string": {
                    "type": "string",
                    "description": "The string to replace old_string with (empty string to delete)",
                },
            },
            "required": ["path", "old_string", "new_string"],
        }

    def execute(self, path: str, old_string: str, new_string: str, **kwargs) -> str:
        """ファイルを差分編集する

        Args:
            path: 編集するファイルのパス
            old_string: 置換対象の文字列
            new_string: 置換後の文字列（空文字列で削除）

        Returns:
            成功メッセージ、またはエラーメッセージ
        """
        try:
            file_path = Path(path)

            if not file_path.exists():
                return f"Error: File not found: {path}"

            if not file_path.is_file():
                return f"Error: Path is not a file: {path}"

            # ファイル内容を読み込む
            content = file_path.read_text(encoding="utf-8")

            # old_stringの出現回数をカウント
            count = content.count(old_string)

            if count == 0:
                return (
                    f"Error: old_string not found in {path}.\n"
                    f"Searched for:\n{old_string[:200]}{'...' if len(old_string) > 200 else ''}"
                )

            if count > 1:
                return (
                    f"Error: old_string appears {count} times in {path}. "
                    f"It must appear exactly once for safe editing. "
                    f"Provide more context in old_string to make it unique."
                )

            # 置換を実行
            new_content = content.replace(old_string, new_string, 1)

            # ファイルに書き込む
            file_path.write_text(new_content, encoding="utf-8")

            # 変更の種類を判定してメッセージを生成
            if new_string == "":
                return f"Successfully deleted text from {path}"
            elif old_string == "":
                return f"Successfully inserted text at the beginning of {path}"
            else:
                return f"Successfully edited {path}"

        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error editing file: {e}"
