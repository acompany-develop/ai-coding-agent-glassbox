import re
from pathlib import Path

from .base import Tool


class GrepTool(Tool):
    """ファイル内容を正規表現で検索するツール

    指定されたパターンにマッチする行を検索して返す。
    Claude CodeのGrepツールに相当。

    学びのポイント:
    - 大規模コードベースの探索に必須
    - 正規表現による柔軟な検索
    - 結果数の制限で出力を管理
    """

    DEFAULT_MAX_RESULTS = 50

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return (
            "Search for a pattern in files using regular expressions. "
            "Returns matching lines with file paths and line numbers. "
            "Use include parameter to filter by file extension (e.g., '*.py')."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in (default: current directory)",
                    "default": ".",
                },
                "include": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g., '*.py', '*.js')",
                },
                "max_results": {
                    "type": "integer",
                    "description": f"Maximum number of results to return (default: {self.DEFAULT_MAX_RESULTS})",
                    "default": self.DEFAULT_MAX_RESULTS,
                },
            },
            "required": ["pattern"],
        }

    def execute(
        self,
        pattern: str,
        path: str = ".",
        include: str | None = None,
        max_results: int | None = None,
        **kwargs,
    ) -> str:
        """パターンを検索する

        Args:
            pattern: 検索する正規表現パターン
            path: 検索対象のディレクトリまたはファイル
            include: ファイルフィルタのglobパターン
            max_results: 最大結果数

        Returns:
            検索結果、またはエラーメッセージ
        """
        max_results = max_results or self.DEFAULT_MAX_RESULTS

        try:
            # 正規表現をコンパイル
            try:
                regex = re.compile(pattern)
            except re.error as e:
                return f"Error: Invalid regex pattern: {e}"

            search_path = Path(path)

            if not search_path.exists():
                return f"Error: Path not found: {path}"

            results = []

            # 検索対象のファイルを収集
            if search_path.is_file():
                files = [search_path]
            else:
                if include:
                    # includeパターンでフィルタリング
                    files = list(search_path.rglob(include))
                else:
                    # すべてのファイルを対象（ディレクトリは除外）
                    files = [f for f in search_path.rglob("*") if f.is_file()]

            # 各ファイルを検索
            for file_path in sorted(files):
                if len(results) >= max_results:
                    break

                # バイナリファイルをスキップ
                if self._is_binary(file_path):
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, PermissionError):
                    continue

                for line_num, line in enumerate(content.splitlines(), start=1):
                    if regex.search(line):
                        # 相対パスで表示
                        try:
                            relative_path = file_path.relative_to(Path(path))
                        except ValueError:
                            relative_path = file_path

                        results.append(f"{relative_path}:{line_num}: {line.strip()}")

                        if len(results) >= max_results:
                            break

            if not results:
                return f"No matches found for pattern: {pattern}"

            output = "\n".join(results)

            if len(results) == max_results:
                output += f"\n\n[Results truncated at {max_results} matches]"

            return output

        except Exception as e:
            return f"Error searching: {e}"

    def _is_binary(self, file_path: Path) -> bool:
        """ファイルがバイナリかどうかを判定"""
        # 拡張子でバイナリファイルを除外
        binary_extensions = {
            ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
            ".jpg", ".jpeg", ".png", ".gif", ".ico", ".bmp",
            ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
            ".mp3", ".mp4", ".avi", ".mov", ".wav",
            ".woff", ".woff2", ".ttf", ".eot",
        }
        return file_path.suffix.lower() in binary_extensions
