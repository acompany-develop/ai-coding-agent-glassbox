# 04. 基本ツールの実装

minimal/ と共通の4つの基本ツールの実装方法です。
拡張ツールについては [05-tools-extended.md](./05-tools-extended.md) を参照してください。

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

## 基本ツール一覧

| ツール | 説明 | Claude Code 相当 |
|--------|------|-----------------|
| `read_file` | ファイル内容を読み込む | Read |
| `write_file` | ファイルに書き込む（全体置換） | Write |
| `list_files` | ディレクトリ内容を一覧表示 | Glob |
| `execute_command` | シェルコマンドを実行 | Bash |

---

## 1. read_file

```python
# tools/read_file.py
class ReadFileTool(Tool):
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
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
```

---

## 2. write_file

```python
# tools/write_file.py
from pathlib import Path

class WriteFileTool(Tool):
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
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote to {path}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
```

**注意**: `write_file` はファイル全体を置き換えます。部分的な編集には `edit_file` を使用してください。

---

## 3. list_files

```python
# tools/list_files.py
from pathlib import Path

class ListFilesTool(Tool):
    name = "list_files"
    description = "List files and directories in the specified path."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The directory path to list",
                "default": ".",
            },
        },
        "required": [],
    }

    def execute(self, path: str = ".") -> str:
        try:
            p = Path(path)
            if not p.exists():
                return f"Error: Path does not exist: {path}"
            if not p.is_dir():
                return f"Error: Path is not a directory: {path}"

            items = sorted(p.iterdir())
            result = []
            for item in items:
                prefix = "[DIR]" if item.is_dir() else "[FILE]"
                result.append(f"{prefix} {item.name}")

            return "\n".join(result) or "(empty directory)"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
```

---

## 4. execute_command

```python
# tools/execute_command.py
import subprocess

class ExecuteCommandTool(Tool):
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

    BLOCKED_PATTERNS = ["rm -rf /", "rm -rf ~", "sudo rm"]

    def execute(self, command: str) -> str:
        # セキュリティチェック
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in command:
                return f"Error: Blocked command pattern: {pattern}"

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
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

---

## ツールレジストリ

```python
# tool_registry.py
class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def register_all(self, tools: list[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def get_tool_definitions(self) -> list[dict]:
        return [tool.to_dict() for tool in self.tools.values()]

    def execute(self, tool_name: str, tool_input: dict) -> str:
        if tool_name not in self.tools:
            return f"Error: Unknown tool '{tool_name}'"
        return self.tools[tool_name].execute(**tool_input)

    def list_tools(self) -> list[str]:
        return list(self.tools.keys())
```

---

## ツールの登録（standard/）

```python
# main.py
from .tools import (
    # 基本ツール
    ReadFileTool,
    WriteFileTool,
    ListFilesTool,
    ExecuteCommandTool,
    # 拡張ツール
    EditFileTool,
    GrepTool,
    GlobTool,
    WebFetchTool,
    AskUserTool,
)

tools = [
    # 基本ツール
    ReadFileTool(),
    WriteFileTool(),
    ListFilesTool(),
    ExecuteCommandTool(),
    # 拡張ツール
    EditFileTool(),
    GrepTool(),
    GlobTool(),
    WebFetchTool(),
    AskUserTool(),
]
tool_registry.register_all(tools)
```

---

## 関連ドキュメント

- [05-tools-extended.md](./05-tools-extended.md) - 拡張ツール（edit_file, grep, glob, web_fetch, ask_user）
- [02-tool-use.md](./02-tool-use.md) - ツールが呼び出される仕組み
