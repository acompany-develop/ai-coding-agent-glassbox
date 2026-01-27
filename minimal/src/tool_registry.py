from typing import Any

from .tools.base import Tool


class ToolRegistry:
    """ツールの登録・検索・実行を管理するレジストリ

    エージェントが利用可能なツールを一元管理し、
    LLMからのツール呼び出しを適切なツール実装にディスパッチする。
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """ツールを登録

        Args:
            tool: 登録するツールインスタンス
        """
        if tool.name in self._tools:
            print(f"[REGISTRY] Warning: Overwriting existing tool: {tool.name}")

        self._tools[tool.name] = tool
        print(f"[REGISTRY] Registered tool: {tool.name}")

    def register_all(self, tools: list[Tool]) -> None:
        """複数のツールを一括登録

        Args:
            tools: 登録するツールのリスト
        """
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Tool | None:
        """名前でツールを取得

        Args:
            name: ツール名

        Returns:
            ツールインスタンス、または見つからない場合はNone
        """
        return self._tools.get(name)

    def get_tool_definitions(self) -> list[dict]:
        """Anthropic API用のツール定義リストを取得

        Returns:
            すべての登録済みツールのAnthropic形式定義リスト
        """
        return [tool.to_anthropic_tool() for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """ツールを名前で検索して実行

        Args:
            name: 実行するツールの名前
            arguments: ツールに渡す引数

        Returns:
            ツールの実行結果
        """
        tool = self.get(name)

        if tool is None:
            return f"Error: Unknown tool: {name}"

        try:
            return tool.execute(**arguments)
        except TypeError as e:
            return f"Error: Invalid arguments for {name}: {e}"
        except Exception as e:
            return f"Error executing {name}: {e}"

    def list_tools(self) -> list[str]:
        """登録済みツール名のリストを取得

        Returns:
            ツール名のリスト
        """
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
