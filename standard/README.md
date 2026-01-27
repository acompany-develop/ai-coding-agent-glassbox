# AI Coding Agent - Glass Box Implementation (Standard Edition)

minimal/ をベースに、より実用的なツールを追加した拡張版です。
教育目的で、各ツールの役割と設計思想を理解できる構成になっています。

## ドキュメント

詳細な解説は [docs/](./docs/) を参照してください。

| ドキュメント | 内容 |
|-------------|------|
| [00-overview.md](./docs/00-overview.md) | 全体像とファイル構成 |
| [01-agent-loop.md](./docs/01-agent-loop.md) | Think→Act→Observe のサイクル |
| [02-tool-use.md](./docs/02-tool-use.md) | Tool Use（Function Calling）の仕組み |
| [03-llm-clients.md](./docs/03-llm-clients.md) | LLM クライアントの抽象化 |
| [04-tools-basic.md](./docs/04-tools-basic.md) | 基本ツールの実装 |
| [05-tools-extended.md](./docs/05-tools-extended.md) | **拡張ツールの実装（edit_file, grep, glob, web_fetch, ask_user）** |
| [06-message-history.md](./docs/06-message-history.md) | メッセージ履歴の管理 |
| [07-stop-reason.md](./docs/07-stop-reason.md) | stop_reason による状態遷移 |

**付録（一般的な AI Coding Agent の実装手法）**

| ドキュメント | 内容 |
|-------------|------|
| [A1-agent-patterns.md](./docs/A1-agent-patterns.md) | エージェントループの実装パターン（ReAct, Plan-and-Execute 等） |
| [A2-tool-use-implementations.md](./docs/A2-tool-use-implementations.md) | Tool Use の実装方式（Native, JSON, XML 等） |
| [A3-existing-agents.md](./docs/A3-existing-agents.md) | 既存の AI Coding Agent の実装比較 |

## 対応プロバイダー

| プロバイダー | デフォルトモデル | 環境変数 | Tool Use 方式 |
|-------------|-----------------|---------|--------------|
| Google Gemini | gemini-2.5-flash | `GEMINI_API_KEY` | Native Function Calling |
| Llama (Ollama) | llama3.1:8b | `OLLAMA_BASE_URL` | JSON モード（プロンプト指示） |

## アーキテクチャ

### 全体像

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                               │
│                    (エントリーポイント)                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Agent Loop (agent.py)                   │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐            │
│  │  THINK   │ ──▶ │   ACT    │ ──▶ │ OBSERVE  │ ─┐         │
│  │ LLM呼出  │     │ ツール実行│     │ 結果収集  │  │         │
│  └──────────┘     └──────────┘     └──────────┘  │         │
│       ▲                                           │         │
│       └───────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────┘
        │                       │
        ▼                       ▼
┌──────────────────┐  ┌─────────────────────────────────────┐
│  LLM Clients     │  │          Tool Registry              │
│  (llm_clients/)  │  │  ┌─────────┐ ┌─────────┐ ┌───────┐ │
│  ┌────────────┐  │  │  │read_file│ │edit_file│ │ grep │ │
│  │  Gemini    │  │  │  ├─────────┤ ├─────────┤ ├───────┤ │
│  ├────────────┤  │  │  │web_fetch│ │ask_user │ │ ... │ │
│  │  Llama     │  │  │  └─────────┘ └─────────┘ └───────┘ │
│  └────────────┘  │  └─────────────────────────────────────┘
└──────────────────┘
```

### Tool Use（Function Calling）の仕組み

AI コーディングエージェントの核心は **Tool Use（Function Calling）** です。
LLM は直接ファイル操作を行わず、「どのツールをどう呼ぶか」を返し、ホスト側が実際の処理を行います。

#### 1. ツール定義の送信

エージェント起動時に、利用可能なツールの定義を LLM に送信します：

```json
{
  "name": "edit_file",
  "description": "Edit a file by replacing a specific string with a new string.",
  "input_schema": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "The path to the file to edit"},
      "old_string": {"type": "string", "description": "The exact string to find and replace"},
      "new_string": {"type": "string", "description": "The string to replace old_string with"}
    },
    "required": ["path", "old_string", "new_string"]
  }
}
```

この定義は LLM への「説明書」であり、LLM はこれを読んで適切なツールを選択します。

#### 2. LLM がツール呼び出しを決定

ユーザーが「hello.py の World を Universe に変えて」と入力すると、LLM は以下のようなレスポンスを返します：

```json
{
  "content": "ファイルを編集します。",
  "tool_calls": [
    {
      "id": "call_abc123",
      "name": "edit_file",
      "input": {
        "path": "hello.py",
        "old_string": "World",
        "new_string": "Universe"
      }
    }
  ],
  "stop_reason": "tool_use"
}
```

**重要**: LLM は「edit_file を呼びたい」という **意図** を返すだけで、実際にファイルを編集するわけではありません。

#### 3. ホスト側でツール実行

エージェントは LLM のレスポンスを解析し、指定されたツールを実際に実行します：

```python
# agent.py での処理
for tool_call in response.tool_calls:
    result = self.tool_registry.execute(
        tool_call.name,     # "edit_file"
        tool_call.input,    # {"path": "hello.py", "old_string": "World", ...}
    )
```

#### 4. 結果を LLM に返送

ツールの実行結果を LLM に送り返します。プロバイダーによって形式が異なります：

**Gemini の場合:**
```json
{
  "role": "user",
  "content": [{
    "type": "tool_result",
    "tool_use_id": "call_abc123",
    "tool_name": "edit_file",
    "content": "Successfully edited hello.py"
  }]
}
```

**Llama（JSON モード）の場合:**
```json
{
  "role": "user",
  "content": "{\"tool_result\": {\"name\": \"edit_file\", \"result\": \"Successfully edited hello.py\"}}"
}
```

#### 5. ループの継続または終了

LLM は結果を受け取り、次のアクションを決定します：

- **さらにツールが必要な場合**: `stop_reason: "tool_use"` で新たなツール呼び出しを返す
- **タスク完了の場合**: `stop_reason: "end_turn"` でテキストのみを返す

### stop_reason の状態遷移

エージェントループは `stop_reason` によって制御されます。

```
                    ┌─────────────────────────────────────────┐
                    │          Agent Loop Start               │
                    └─────────────────────────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────────┐
                    │          THINK: LLM 呼び出し             │
                    └─────────────────────────────────────────┘
                                       │
                                       ▼
                         ┌─────────────────────────┐
                         │     stop_reason は？    │
                         └─────────────────────────┘
                          │                       │
              ┌───────────┘                       └───────────┐
              │                                               │
              ▼                                               ▼
┌─────────────────────────┐                 ┌─────────────────────────┐
│   stop_reason:          │                 │   stop_reason:          │
│   "tool_use"            │                 │   "end_turn"            │
│                         │                 │                         │
│ ツール呼び出しが必要     │                 │ タスク完了              │
│ → ACT フェーズへ        │                 │ → ループ終了            │
└─────────────────────────┘                 └─────────────────────────┘
              │                                               │
              ▼                                               ▼
┌─────────────────────────┐                 ┌─────────────────────────┐
│   ACT: ツール実行        │                 │   最終レスポンスを返す   │
│   OBSERVE: 結果収集      │                 │                         │
└─────────────────────────┘                 └─────────────────────────┘
              │
              │ ツール結果を履歴に追加
              │
              └──────────────────┐
                                 │
                                 ▼
                    ┌─────────────────────────────────────────┐
                    │          THINK: LLM 呼び出し（次）       │
                    └─────────────────────────────────────────┘
                                       │
                                      ...（繰り返し）
```

**状態遷移表:**

| 現在の状態 | stop_reason | 次の状態 | 説明 |
|-----------|-------------|---------|------|
| THINK | `"tool_use"` | ACT → OBSERVE → THINK | ツールを実行し、結果を収集して次の判断へ |
| THINK | `"end_turn"` | END | タスク完了、ループ終了 |
| THINK | その他/空 | END | ツール呼び出しなし、テキストのみ返却 |

**各プロバイダーの stop_reason 値:**

| プロバイダー | ツール呼び出し時 | タスク完了時 | 元の値 |
|-------------|----------------|-------------|--------|
| Gemini | `"tool_use"` | `"end_turn"` | `function_call` の有無で判定 |
| Llama | `"tool_use"` | `"end_turn"` | JSON の `tool_call` / `response` キーで判定 |

### Human-in-the-loop（ask_user ツール）

Standard 版では `ask_user` ツールにより、エージェントがユーザーに確認を求めることができます：

```
User: "不要なファイルを削除して"
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ Iteration 1: THINK                                        │
│   LLM: "削除前に確認します"                                │
│   tool_calls: [{name: "ask_user", input: {                │
│     "question": "以下のファイルを削除してよいですか？",      │
│     "options": ["はい", "いいえ", "選択して削除"]           │
│   }}]                                                     │
│   stop_reason: "tool_use"                                 │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ Iteration 1: ACT (ユーザー入力待ち)                        │
│   [ASK USER] 以下のファイルを削除してよいですか？           │
│     1. はい                                               │
│     2. いいえ                                             │
│     3. 選択して削除                                       │
│   選択してください (番号を入力): _                         │
└───────────────────────────────────────────────────────────┘
```

これにより、危険な操作の前にユーザー確認を挟むことができます。

### Llama（Tool Use 非対応モデル）への対応

Llama 3.1 8B は Native Function Calling（Tool Use）に対応していません。
そのため、**JSON モード** を使用してツール呼び出しをシミュレートします。

#### Llama 用の JSON フォーマット

**ツール呼び出し時:**
```json
{
  "thought": "ファイルの内容を変更する必要があります",
  "tool_call": {
    "name": "edit_file",
    "input": { "path": "hello.py", "old_string": "World", "new_string": "Universe" }
  }
}
```

**タスク完了時:**
```json
{
  "thought": "ファイルを正常に編集しました",
  "response": "hello.py の World を Universe に変更しました"
}
```

## セットアップ

### uv を使用（推奨）

```bash
cd standard

# 依存関係のインストールと実行
uv run ai-agent-standard

# または直接 Python モジュールとして実行
uv run python -m src.main
```

### Ollama のセットアップ（Llama を使う場合）

```bash
# Ollama をインストール（macOS）
brew install ollama

# Ollama サーバーを起動
ollama serve

# Llama 3.1 8B をダウンロード
ollama pull llama3.1:8b
```

### 環境変数の設定

`.env` ファイルを使用するか、環境変数を直接設定してください。

```bash
# .env ファイルを作成（推奨）
cp .env.example .env
# .env を編集して API キーを設定
```

または、シェルで直接設定：

```bash
export GEMINI_API_KEY="your-gemini-key"
export OLLAMA_BASE_URL="http://localhost:11434"  # デフォルト値
```

## 使用方法

### CLI として実行

```bash
# Gemini を使用（デフォルト）
uv run ai-agent-standard

# プロバイダーを指定
uv run ai-agent-standard --provider gemini
uv run ai-agent-standard --provider llama

# モデルも指定
uv run ai-agent-standard --provider gemini --model gemini-2.0-flash
uv run ai-agent-standard --provider llama --model llama3.1:70b
```

### 対話例

```
> src/ 以下の全ての .py ファイルを一覧表示して
> "def " を含むPythonファイルを検索して
> hello.py の "World" を "Universe" に変更して
> https://example.com の内容を取得して要約して
> このファイルを削除していい？
```

## ツール一覧

### 基本ツール（minimal/ と同じ）

| ツール | 説明 | Claude Code 相当 |
|--------|------|-----------------|
| `read_file` | ファイル内容を読み込む | Read |
| `write_file` | ファイルに書き込む（全体置換） | Write |
| `list_files` | ディレクトリ内容を一覧表示 | Glob |
| `execute_command` | シェルコマンドを実行 | Bash |

### 拡張ツール（Standard 版で追加）

| ツール | 説明 | Claude Code 相当 | 学びのポイント |
|--------|------|-----------------|---------------|
| `edit_file` | 差分編集 | Edit | write_file との違い、トークン効率 |
| `grep` | 正規表現検索 | Grep | コードベース探索 |
| `glob` | パターンマッチング | Glob | ファイル検索の効率化 |
| `web_fetch` | URL 取得 | WebFetch | 外部情報への拡張 |
| `ask_user` | ユーザー確認 | (暗黙的) | Human-in-the-loop |

## ディレクトリ構成

```
standard/
├── pyproject.toml            # 依存関係（uv/pip 対応）
├── README.md
├── src/
│   ├── __init__.py
│   ├── main.py               # エントリーポイント
│   ├── agent.py              # エージェントループ (Think→Act→Observe)
│   ├── tool_registry.py      # ツール登録・実行管理
│   ├── message_history.py    # メッセージ履歴管理
│   ├── llm_clients/          # LLMクライアント
│   │   ├── __init__.py       # ファクトリ関数
│   │   ├── base.py           # 抽象基底クラス (BaseLLMClient)
│   │   ├── gemini_client.py  # Gemini 実装 (Native Function Calling)
│   │   └── llama_client.py   # Llama 実装 (JSON モード)
│   └── tools/
│       ├── __init__.py
│       ├── base.py           # ツール基底クラス (Tool)
│       ├── read_file.py      # 基本: ファイル読み込み
│       ├── write_file.py     # 基本: ファイル書き込み
│       ├── list_files.py     # 基本: ディレクトリ一覧
│       ├── execute_command.py # 基本: シェルコマンド実行
│       ├── edit_file.py      # 拡張: 差分編集
│       ├── grep.py           # 拡張: 正規表現検索
│       ├── glob_tool.py      # 拡張: パターンマッチング
│       ├── web_fetch.py      # 拡張: URL取得
│       └── ask_user.py       # 拡張: ユーザー確認
└── examples/
    └── sample_project/
        └── hello.py
```

## 学びのポイント

### 1. edit_file vs write_file

**write_file**（全体置換）:
- ファイル全体を送信 → トークン消費大
- 意図しない変更のリスク

**edit_file**（差分編集）:
- 変更箇所のみ指定 → トークン効率◎
- old_string の一意性チェックで安全性確保

```python
# write_file: ファイル全体を書き込み
write_file(path="hello.py", content="def greet():\n    return 'Hello'")

# edit_file: 変更箇所のみ指定
edit_file(path="hello.py", old_string="World", new_string="Universe")
```

### 2. grep + glob

大規模コードベースでは、ファイル探索の効率が重要：

```python
# glob: ファイル名パターンで検索
glob(pattern="**/*.py")  # すべての Python ファイル

# grep: 内容で検索
grep(pattern="def main", include="*.py")  # main 関数を探す
```

### 3. web_fetch

エージェントの情報源を外部に拡張：

```python
# ドキュメント取得
web_fetch(url="https://docs.python.org/3/library/json.html")

# API リファレンス取得
web_fetch(url="https://api.example.com/docs")
```

### 4. ask_user（Human-in-the-loop）

危険な操作の前にユーザー確認：

```python
# 確認を求める
ask_user(
    question="このファイルを削除してよいですか？",
    options=["はい", "いいえ", "キャンセル"]
)

# 自由回答を求める
ask_user(question="どのような形式で出力しますか？")
```

### 5. Tool Use 非対応モデル（Llama）への対応

Llama のような Tool Use 非対応モデルでも、JSON モードとプロンプトエンジニアリングで
エージェント構築が可能。ただし：

- **パース処理** が必要（JSON の構文エラー対応）
- **プロンプト設計** が重要（明確なフォーマット指示）
- **信頼性** は Native Function Calling より低い

## minimal/ との違い

| 項目 | minimal/ | standard/ |
|------|----------|-----------|
| ツール数 | 4 | 9 |
| 依存関係 | google-genai, httpx | + requests, beautifulsoup4 |
| 用途 | 学習・理解 | 実用的な開発 |
| Human-in-the-loop | なし | あり (ask_user) |
| 外部情報取得 | なし | あり (web_fetch) |
| 差分編集 | なし | あり (edit_file) |
| コード検索 | なし | あり (grep, glob) |

## 次のステップ

- **advanced/**: サブエージェント、メモリ、より高度なツール
- **MCP サポート**: 外部ツールサーバーとの連携
- **セキュリティ強化**: サンドボックス、認可システム
