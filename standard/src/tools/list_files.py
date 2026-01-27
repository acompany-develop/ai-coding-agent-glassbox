from pathlib import Path

from .base import Tool


class ListFilesTool(Tool):
    """ディレクトリ内のファイル一覧を取得するツール

    指定されたディレクトリ内のファイルとサブディレクトリを一覧表示する。
    Claude CodeのGlobツールに相当。
    """

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "List files and directories in the specified directory. "
            "Returns a tree-like structure showing the contents."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to list contents of",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether to list files recursively (default: False)",
                    "default": False,
                },
            },
            "required": ["path"],
        }

    def execute(self, path: str, recursive: bool = False, **kwargs) -> str:
        """ディレクトリ内のファイル一覧を取得

        Args:
            path: 一覧を取得するディレクトリのパス
            recursive: 再帰的に取得するかどうか

        Returns:
            ファイル一覧、またはエラーメッセージ
        """
        try:
            dir_path = Path(path)

            if not dir_path.exists():
                return f"Error: Directory not found: {path}"

            if not dir_path.is_dir():
                return f"Error: Path is not a directory: {path}"

            if recursive:
                items = self._list_recursive(dir_path, prefix="")
            else:
                items = self._list_flat(dir_path)

            if not items:
                return f"Directory is empty: {path}"

            return "\n".join(items)

        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error listing directory: {e}"

    def _list_flat(self, dir_path: Path) -> list[str]:
        """フラットなファイル一覧を取得"""
        items = []
        for item in sorted(dir_path.iterdir()):
            if item.is_dir():
                items.append(f"{item.name}/")
            else:
                items.append(item.name)
        return items

    def _list_recursive(self, dir_path: Path, prefix: str) -> list[str]:
        """再帰的なファイル一覧を取得（ツリー表示）"""
        items = []
        children = sorted(dir_path.iterdir())

        for i, item in enumerate(children):
            is_last = i == len(children) - 1
            connector = "└── " if is_last else "├── "
            extension = "    " if is_last else "│   "

            if item.is_dir():
                items.append(f"{prefix}{connector}{item.name}/")
                items.extend(
                    self._list_recursive(item, prefix + extension)
                )
            else:
                items.append(f"{prefix}{connector}{item.name}")

        return items
