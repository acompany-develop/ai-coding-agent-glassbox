from pathlib import Path

from .base import Tool


class ReadFileTool(Tool):
    """ファイルを読み込むツール

    指定されたパスのファイル内容を読み込んで返す。
    Claude CodeのReadツールに相当。
    """

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file at the specified path. "
            "Use this tool when you need to examine file contents."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file to read",
                },
            },
            "required": ["path"],
        }

    def execute(self, path: str, **kwargs) -> str:
        """ファイルを読み込む

        Args:
            path: 読み込むファイルのパス

        Returns:
            ファイルの内容、またはエラーメッセージ
        """
        try:
            file_path = Path(path)

            if not file_path.exists():
                return f"Error: File not found: {path}"

            if not file_path.is_file():
                return f"Error: Path is not a file: {path}"

            content = file_path.read_text(encoding="utf-8")
            return content

        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error reading file: {e}"
