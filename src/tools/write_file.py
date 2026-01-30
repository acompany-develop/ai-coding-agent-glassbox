from pathlib import Path

from .base import Tool


class WriteFileTool(Tool):
    """ファイルに書き込むツール

    指定されたパスにファイルを作成または上書きする。
    Claude CodeのWriteツールに相当。
    """

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write content to a file at the specified path. "
            "Creates the file if it doesn't exist, or overwrites it if it does. "
            "Parent directories will be created if they don't exist."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file",
                },
            },
            "required": ["path", "content"],
        }

    def execute(self, path: str, content: str, **kwargs) -> str:
        """ファイルに書き込む

        Args:
            path: 書き込むファイルのパス
            content: 書き込む内容

        Returns:
            成功メッセージ、またはエラーメッセージ
        """
        try:
            file_path = Path(path)

            # 親ディレクトリが存在しない場合は作成
            file_path.parent.mkdir(parents=True, exist_ok=True)

            file_path.write_text(content, encoding="utf-8")
            return f"Successfully wrote to {path}"

        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error writing file: {e}"
