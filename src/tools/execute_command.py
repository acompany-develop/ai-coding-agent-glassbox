import subprocess

from .base import Tool


class ExecuteCommandTool(Tool):
    """シェルコマンドを実行するツール

    指定されたコマンドをシェルで実行し、結果を返す。
    Claude CodeのBashツールに相当。

    セキュリティ注意: 本番環境では適切なサンドボックス化が必要。
    """

    DEFAULT_TIMEOUT = 30  # seconds

    @property
    def name(self) -> str:
        return "execute_command"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command and return its output. "
            "Use this for running scripts, checking system state, etc. "
            "Note: Commands are executed in the current working directory."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Timeout in seconds (default: {self.DEFAULT_TIMEOUT})",
                    "default": self.DEFAULT_TIMEOUT,
                },
            },
            "required": ["command"],
        }

    def execute(self, command: str, timeout: int | None = None, **kwargs) -> str:
        """コマンドを実行

        Args:
            command: 実行するシェルコマンド
            timeout: タイムアウト秒数

        Returns:
            コマンドの出力（stdout + stderr）、またはエラーメッセージ
        """
        timeout = timeout or self.DEFAULT_TIMEOUT

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output_parts = []

            if result.stdout:
                output_parts.append(f"[stdout]\n{result.stdout}")

            if result.stderr:
                output_parts.append(f"[stderr]\n{result.stderr}")

            if result.returncode != 0:
                output_parts.append(f"[exit code: {result.returncode}]")

            if not output_parts:
                return "[Command completed with no output]"

            return "\n".join(output_parts)

        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds"
        except Exception as e:
            return f"Error executing command: {e}"
