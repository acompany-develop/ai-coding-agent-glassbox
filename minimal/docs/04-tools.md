# 04. ツールの実装

エージェントが使用できるツール（機能）の実装方法です。

## ツールの基本構造

```python
# tools/base.py
from abc import ABC, abstractmethod

class Tool(ABC):
    """ツールの抽象基底クラス"""

    # ツールのメタ情報（サブクラスで定義）
    name: str = ""
    description: str = ""
    input_schema: dict = {}

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """ツールを実行し、結果を文字列で返す"""
        pass

    def to_dict(self) -> dict:
        """LLM に送信するためのツール定義を返す"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
```

## 実装例: read_file

```python
# tools/read_file.py
from .base import Tool

class ReadFileTool(Tool):
    """ファイル読み込みツール"""

    name = "read_file"
    description = "Read the contents of a file at the specified path."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path to the file to read",
            },
        },
        "required": ["path"],
    }

    def execute(self, path: str) -> str:
        """ファイルを読み込んで内容を返す"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return content
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
```

## 実装例: write_file

```python
# tools/write_file.py
from pathlib import Path
from .base import Tool

class WriteFileTool(Tool):
    """ファイル書き込みツール"""

    name = "write_file"
    description = "Write content to a file at the specified path."
    input_schema = {
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

    def execute(self, path: str, content: str) -> str:
        """ファイルに内容を書き込む"""
        try:
            # 親ディレクトリを作成
            Path(path).parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            return f"Successfully wrote to {path}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
```

## 実装例: execute_command

```python
# tools/execute_command.py
import subprocess
from .base import Tool

class ExecuteCommandTool(Tool):
    """シェルコマンド実行ツール"""

    name = "execute_command"
    description = "Execute a shell command and return the output."
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
        },
        "required": ["command"],
    }

    # セキュリティのためブロックするパターン
    BLOCKED_PATTERNS = [
        "rm -rf /",
        "rm -rf ~",
        "sudo rm",
        "> /dev/sda",
    ]

    def execute(self, command: str) -> str:
        """コマンドを実行して出力を返す"""
        # ブロックパターンのチェック
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in command:
                return f"Error: Blocked command pattern: {pattern}"

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,  # 30秒でタイムアウト
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"

            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"

            return output or "(no output)"

        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 30 seconds"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
```

## ツールレジストリ

```python
# tool_registry.py
class ToolRegistry:
    """ツールを登録・管理するクラス"""

    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """ツールを登録"""
        self.tools[tool.name] = tool

    def register_all(self, tools: list[Tool]) -> None:
        """複数のツールを一括登録"""
        for tool in tools:
            self.register(tool)

    def get_tool_definitions(self) -> list[dict]:
        """LLM に送信するためのツール定義リストを返す"""
        return [tool.to_dict() for tool in self.tools.values()]

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """ツールを実行"""
        if tool_name not in self.tools:
            return f"Error: Unknown tool '{tool_name}'"

        tool = self.tools[tool_name]
        return tool.execute(**tool_input)

    def list_tools(self) -> list[str]:
        """登録されているツール名のリストを返す"""
        return list(self.tools.keys())
```

## ツールの登録

```python
# main.py
tool_registry = ToolRegistry()

tools = [
    ReadFileTool(),
    WriteFileTool(),
    ListFilesTool(),
    ExecuteCommandTool(),
]
tool_registry.register_all(tools)
```

## input_schema の書き方

JSON Schema 形式でパラメータを定義します。

```python
input_schema = {
    "type": "object",
    "properties": {
        # 必須パラメータ
        "path": {
            "type": "string",
            "description": "The path to the file",
        },
        # オプションパラメータ（デフォルト値付き）
        "encoding": {
            "type": "string",
            "description": "File encoding (default: utf-8)",
            "default": "utf-8",
        },
        # 列挙型
        "mode": {
            "type": "string",
            "enum": ["read", "write", "append"],
            "description": "File open mode",
        },
        # 配列
        "paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of file paths",
        },
    },
    "required": ["path"],  # 必須パラメータのリスト
}
```

## 新しいツールの追加方法

1. `tools/` に新しいファイルを作成
2. `Tool` クラスを継承
3. `name`, `description`, `input_schema` を定義
4. `execute()` メソッドを実装
5. `tools/__init__.py` でエクスポート
6. `main.py` で登録

```python
# tools/my_tool.py
from .base import Tool

class MyTool(Tool):
    name = "my_tool"
    description = "Does something useful."
    input_schema = {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."},
        },
        "required": ["param1"],
    }

    def execute(self, param1: str) -> str:
        # 実装
        return f"Result: {param1}"
```

```python
# tools/__init__.py
from .my_tool import MyTool
__all__ = [..., "MyTool"]
```

```python
# main.py
from .tools import MyTool
tools = [..., MyTool()]
```

## エラーハンドリングのベストプラクティス

```python
def execute(self, **kwargs) -> str:
    try:
        # メイン処理
        result = do_something(**kwargs)
        return result
    except SpecificError as e:
        # 特定のエラー
        return f"Error: {e}"
    except Exception as e:
        # 予期しないエラー
        return f"Error: {type(e).__name__}: {e}"
```

常に文字列を返すことで、エージェントループが壊れないようにします。

## 関連ドキュメント

- [02-tool-use.md](./02-tool-use.md) - ツールが呼び出される仕組み
