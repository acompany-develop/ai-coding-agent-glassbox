from pathlib import Path

from .base import Tool


class GlobTool(Tool):
    """パターンマッチングでファイルを検索するツール

    globパターンを使用してファイルを検索する。
    Claude CodeのGlobツールに相当。

    学びのポイント:
    - **を使った再帰検索のサポート
    - ファイル名のパターンマッチング
    - list_filesとの違い（パターン指定 vs ディレクトリ一覧）
    """

    DEFAULT_MAX_RESULTS = 100

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return (
            "Find files matching a glob pattern. "
            "Supports ** for recursive matching (e.g., '**/*.py' for all Python files). "
            "Returns a list of matching file paths."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match files (e.g., '**/*.py', 'src/*.js')",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search from (default: current directory)",
                    "default": ".",
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
        max_results: int | None = None,
        **kwargs,
    ) -> str:
        """パターンにマッチするファイルを検索する

        Args:
            pattern: globパターン
            path: 検索のベースディレクトリ
            max_results: 最大結果数

        Returns:
            マッチしたファイルの一覧、またはエラーメッセージ
        """
        max_results = max_results or self.DEFAULT_MAX_RESULTS

        try:
            base_path = Path(path)

            if not base_path.exists():
                return f"Error: Path not found: {path}"

            if not base_path.is_dir():
                return f"Error: Path is not a directory: {path}"

            # globを実行
            matches = list(base_path.glob(pattern))

            # ファイルのみをフィルタリング（ディレクトリを除外）
            files = [m for m in matches if m.is_file()]

            # ソート
            files = sorted(files)

            # 結果数を制限
            truncated = len(files) > max_results
            files = files[:max_results]

            if not files:
                return f"No files found matching pattern: {pattern}"

            # 相対パスで出力
            results = []
            for file_path in files:
                try:
                    relative_path = file_path.relative_to(base_path)
                except ValueError:
                    relative_path = file_path
                results.append(str(relative_path))

            output = "\n".join(results)

            if truncated:
                output += f"\n\n[Results truncated at {max_results} files]"

            return output

        except Exception as e:
            return f"Error searching for files: {e}"
