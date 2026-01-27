# 05. 拡張ツールの実装

standard/ で追加された5つのツールの実装と設計思想を解説します。

## 拡張ツール一覧

| ツール | 説明 | Claude Code 相当 | 学びのポイント |
|--------|------|-----------------|---------------|
| `edit_file` | 差分編集 | Edit | write_file との違い、トークン効率 |
| `grep` | 正規表現検索 | Grep | コードベース探索 |
| `glob` | パターンマッチング | Glob | ファイル検索の効率化 |
| `web_fetch` | URL 取得 | WebFetch | 外部情報への拡張 |
| `ask_user` | ユーザー確認 | (暗黙的) | Human-in-the-loop |

---

## 1. edit_file（差分編集）

### なぜ必要か

`write_file` はファイル全体を書き込むため、大きなファイルでは非効率です。

```
write_file の問題点:
┌─────────────────────────────────────────────────────┐
│ 1000行のファイルで1行を変更する場合               │
│                                                   │
│ LLM → "1000行全体をレスポンスに含める"             │
│     → トークン消費大                              │
│     → 意図しない変更のリスク                       │
└─────────────────────────────────────────────────────┘

edit_file の解決策:
┌─────────────────────────────────────────────────────┐
│ 変更箇所のみ指定                                   │
│                                                   │
│ LLM → old_string: "Hello"                         │
│     → new_string: "Hello, World"                  │
│     → トークン消費最小                             │
│     → 安全（一意性チェック）                        │
└─────────────────────────────────────────────────────┘
```

### 実装

```python
# tools/edit_file.py
class EditFileTool(Tool):
    name = "edit_file"
    description = "Edit a file by replacing a specific string with a new string."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path to the file to edit",
            },
            "old_string": {
                "type": "string",
                "description": "The exact string to find and replace",
            },
            "new_string": {
                "type": "string",
                "description": "The string to replace old_string with",
            },
        },
        "required": ["path", "old_string", "new_string"],
    }

    def execute(self, path: str, old_string: str, new_string: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            # old_string が見つからない場合
            if old_string not in content:
                return f"Error: Could not find the string to replace in {path}"

            # 複数マッチの場合（一意性チェック）
            count = content.count(old_string)
            if count > 1:
                return (
                    f"Error: Found {count} occurrences of the string. "
                    f"Please provide a more specific string to ensure unique match."
                )

            # 置換して書き込み
            new_content = content.replace(old_string, new_string, 1)

            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return f"Successfully edited {path}"

        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
```

### 使用例

```python
# "Hello" を "Hello, World" に変更
edit_file(
    path="greeting.py",
    old_string='return "Hello"',
    new_string='return "Hello, World"',
)
```

### 一意性チェックの重要性

```python
# 悪い例: 曖昧な old_string
edit_file(path="app.py", old_string="def", new_string="async def")
# → "def" が複数あるとエラー

# 良い例: 十分なコンテキストを含む
edit_file(
    path="app.py",
    old_string="def greet():",
    new_string="async def greet():",
)
```

---

## 2. grep（正規表現検索）

### なぜ必要か

大規模コードベースで特定のパターンを探すのに必須です。

### 実装

```python
# tools/grep.py
import re
from pathlib import Path
from .base import Tool

class GrepTool(Tool):
    name = "grep"
    description = "Search for a pattern in files using regular expressions."
    input_schema = {
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
                "description": "File pattern to include (e.g., '*.py')",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 50,
            },
        },
        "required": ["pattern"],
    }

    def execute(
        self,
        pattern: str,
        path: str = ".",
        include: str | None = None,
        max_results: int = 50,
    ) -> str:
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Error: Invalid regex pattern: {e}"

        results = []
        search_path = Path(path)

        # ファイルを収集
        if search_path.is_file():
            files = [search_path]
        else:
            glob_pattern = include or "**/*"
            files = [f for f in search_path.glob(glob_pattern) if f.is_file()]

        # 各ファイルを検索
        for file_path in files:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if regex.search(line):
                            results.append(f"{file_path}:{line_num}: {line.rstrip()}")

                            if len(results) >= max_results:
                                results.append(f"... (truncated at {max_results} results)")
                                return "\n".join(results)
            except Exception:
                continue  # バイナリファイル等はスキップ

        if not results:
            return f"No matches found for pattern: {pattern}"

        return "\n".join(results)
```

### 使用例

```python
# 全ての Python ファイルで "def main" を検索
grep(pattern="def main", path="src/", include="*.py")

# 正規表現: "TODO" または "FIXME" を検索
grep(pattern="TODO|FIXME", path=".")
```

---

## 3. glob（パターンマッチング）

### なぜ必要か

ファイル構造を把握したり、特定パターンのファイルを見つけるのに使います。

### 実装

```python
# tools/glob_tool.py
from pathlib import Path
from .base import Tool

class GlobTool(Tool):
    name = "glob"
    description = "Find files matching a glob pattern."
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern (e.g., '**/*.py' for all Python files)",
            },
            "path": {
                "type": "string",
                "description": "Base directory to search from (default: current directory)",
                "default": ".",
            },
        },
        "required": ["pattern"],
    }

    def execute(self, pattern: str, path: str = ".") -> str:
        try:
            base_path = Path(path)

            if not base_path.exists():
                return f"Error: Path does not exist: {path}"

            # glob でファイルを検索
            matches = sorted(base_path.glob(pattern))

            if not matches:
                return f"No files found matching pattern: {pattern}"

            # 結果を整形
            results = [str(m) for m in matches[:100]]  # 最大100件

            if len(matches) > 100:
                results.append(f"... and {len(matches) - 100} more files")

            return "\n".join(results)

        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
```

### 使用例

```python
# 全ての Python ファイル
glob(pattern="**/*.py")

# src/ 直下のファイルのみ
glob(pattern="src/*")

# テストファイル
glob(pattern="**/test_*.py")
```

---

## 4. web_fetch（URL 取得）

### なぜ必要か

ドキュメント参照、API 仕様の確認など、外部情報が必要な場面で使用します。

### 実装

```python
# tools/web_fetch.py
import requests
from bs4 import BeautifulSoup
from .base import Tool

class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch content from a URL and extract text."
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch content from",
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds (default: 30)",
                "default": 30,
            },
        },
        "required": ["url"],
    }

    def execute(self, url: str, timeout: int = 30) -> str:
        try:
            # HTTP リクエスト
            response = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": "AI-Coding-Agent/1.0"},
            )
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")

            # HTML の場合はテキスト抽出
            if "text/html" in content_type:
                soup = BeautifulSoup(response.text, "html.parser")

                # スクリプト、スタイルを除去
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()

                text = soup.get_text(separator="\n", strip=True)

                # 長すぎる場合は切り詰め
                if len(text) > 10000:
                    text = text[:10000] + "\n... (truncated)"

                return text

            # それ以外はそのまま返す
            return response.text[:10000]

        except requests.Timeout:
            return f"Error: Request timed out after {timeout} seconds"
        except requests.RequestException as e:
            return f"Error: {type(e).__name__}: {e}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
```

### 使用例

```python
# ドキュメント取得
web_fetch(url="https://docs.python.org/3/library/json.html")

# API リファレンス
web_fetch(url="https://api.example.com/docs")
```

---

## 5. ask_user（Human-in-the-loop）

### なぜ必要か

危険な操作の前にユーザー確認を挟むことで、安全性を確保します。

```
┌─────────────────────────────────────────────────────────────┐
│ Human-in-the-loop パターン                                  │
│                                                             │
│  User: "不要なファイルを削除して"                           │
│         │                                                   │
│         ▼                                                   │
│  Agent: "以下のファイルを削除してよいですか？"              │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  [ASK USER]                                         │   │
│  │  以下のファイルを削除してよいですか？               │   │
│  │    1. はい                                          │   │
│  │    2. いいえ                                        │   │
│  │    3. 選択して削除                                  │   │
│  │  選択 (番号): _                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│         │                                                   │
│         ▼                                                   │
│  Agent: ユーザーの回答に基づいて処理を継続                  │
└─────────────────────────────────────────────────────────────┘
```

### 実装

```python
# tools/ask_user.py
from .base import Tool

class AskUserTool(Tool):
    name = "ask_user"
    description = "Ask the user a question and wait for their response."
    input_schema = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to ask the user",
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of choices for the user",
            },
        },
        "required": ["question"],
    }

    def execute(self, question: str, options: list[str] | None = None) -> str:
        print(f"\n[ASK USER] {question}")

        if options:
            # 選択肢がある場合
            for i, opt in enumerate(options, 1):
                print(f"  {i}. {opt}")

            while True:
                try:
                    choice = input("選択 (番号): ").strip()
                    idx = int(choice) - 1

                    if 0 <= idx < len(options):
                        return options[idx]
                    else:
                        print(f"1〜{len(options)} の番号を入力してください")
                except ValueError:
                    # 番号以外の入力はそのまま返す
                    return choice
        else:
            # 自由回答
            response = input("回答: ").strip()
            return response
```

### 使用例

```python
# 確認を求める（選択肢あり）
ask_user(
    question="このファイルを削除してよいですか？",
    options=["はい", "いいえ", "キャンセル"],
)

# 自由回答を求める
ask_user(question="どのような形式で出力しますか？")
```

### エージェントループでの動作

```
Iteration 1:
  THINK → LLM: "削除前に確認します"
  ACT   → ask_user(question="削除してよいですか？", options=["はい", "いいえ"])
          ↓
          ユーザー入力待ち
          ↓
          ユーザー: "1" (はい)
  OBSERVE → "はい"

Iteration 2:
  THINK → LLM: "ユーザーが承認したので削除を実行"
  ACT   → execute_command("rm temp.txt")
  ...
```

---

## ツール設計のベストプラクティス

### 1. 明確な description

LLM がツールを正しく選択できるように、用途を明確に記述します。

```python
# 悪い例
description = "Edit file"

# 良い例
description = "Edit a file by replacing a specific string with a new string. Use this for targeted edits instead of rewriting the entire file."
```

### 2. 適切な input_schema

パラメータの意味と制約を明確にします。

```python
input_schema = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "Regular expression pattern to search for",
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of results (default: 50)",
            "default": 50,
            "minimum": 1,
            "maximum": 1000,
        },
    },
    "required": ["pattern"],
}
```

### 3. 安全なエラーハンドリング

常に文字列を返し、例外でエージェントループが壊れないようにします。

```python
def execute(self, **kwargs) -> str:
    try:
        result = do_something(**kwargs)
        return result
    except SpecificError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
```

---

## Claude Code との対応

| 本実装 | Claude Code | 違い |
|--------|-------------|------|
| edit_file | Edit | ほぼ同じ（一意性チェック） |
| grep | Grep | 基本機能は同じ |
| glob | Glob | 基本機能は同じ |
| web_fetch | WebFetch | HTML→テキスト変換 |
| ask_user | (暗黙的) | Claude Code は CLI で確認を出す |

## 関連ドキュメント

- [04-tools-basic.md](./04-tools-basic.md) - 基本ツール
- [02-tool-use.md](./02-tool-use.md) - ツールが呼び出される仕組み
