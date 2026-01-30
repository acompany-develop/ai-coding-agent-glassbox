# AI Coding Agent - Glass Box Implementation (Minimal Edition)

AI コーディングエージェント（Claude Code や Cursor のようなもの）の内部構造を理解するための最小セット実装。
「ガラスボックス」として、各コンポーネントの動作が見える設計になっています。

## ドキュメント

詳細な解説は [docs/](./docs/) を参照してください。

| ドキュメント | 内容 |
|-------------|------|
| [00-overview.md](./docs/00-overview.md) | 全体像とファイル構成 |
| [01-agent-loop.md](./docs/01-agent-loop.md) | Think→Act→Observe のサイクル |
| [02-tool-use.md](./docs/02-tool-use.md) | Tool Use（Function Calling）の仕組み |
| [03-llm-clients.md](./docs/03-llm-clients.md) | LLM クライアントの抽象化 |
| [04-tools.md](./docs/04-tools.md) | ツールの実装方法 |
| [05-message-history.md](./docs/05-message-history.md) | メッセージ履歴の管理 |
| [06-stop-reason.md](./docs/06-stop-reason.md) | stop_reason による状態遷移 |

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
│  ┌────────────┐  │  │  │read_file│ │write_file│ │ ... │ │
│  │  Gemini    │  │  │  └─────────┘ └─────────┘ └───────┘ │
│  ├────────────┤  │  └─────────────────────────────────────┘
│  │  Llama     │  │
│  └────────────┘  │
└──────────────────┘
```

### Tool Use（Function Calling）の仕組み

AI コーディングエージェントの核心は **Tool Use（Function Calling）** です。
LLM は直接ファイル操作を行わず、「どのツールをどう呼ぶか」を返し、ホスト側が実際の処理を行います。

#### 1. ツール定義の送信

エージェント起動時に、利用可能なツールの定義を LLM に送信します：

```json
{
  "name": "read_file",
  "description": "Read the contents of a file at the specified path.",
  "input_schema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "The path to the file to read"
      }
    },
    "required": ["path"]
  }
}
```

この定義は LLM への「説明書」であり、LLM はこれを読んで適切なツールを選択します。

#### 2. LLM がツール呼び出しを決定

ユーザーが「hello.py を読んで」と入力すると、LLM は以下のようなレスポンスを返します：

```json
{
  "content": "ファイルの内容を確認します。",
  "tool_calls": [
    {
      "id": "call_abc123",
      "name": "read_file",
      "input": { "path": "hello.py" }
    }
  ],
  "stop_reason": "tool_use"
}
```

**重要**: LLM は「read_file を呼びたい」という **意図** を返すだけで、実際にファイルを読むわけではありません。

#### 3. ホスト側でツール実行

エージェントは LLM のレスポンスを解析し、指定されたツールを実際に実行します：

```python
# agent.py での処理
for tool_call in response.tool_calls:
    result = self.tool_registry.execute(
        tool_call.name,     # "read_file"
        tool_call.input,    # {"path": "hello.py"}
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
    "tool_name": "read_file",
    "content": "def greet():\n    return 'Hello, World!'"
  }]
}
```

**Llama（JSON モード）の場合:**
```json
{
  "role": "user",
  "content": "{\"tool_result\": {\"name\": \"read_file\", \"result\": \"def greet():\\n    return 'Hello, World!'\"}}"
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

### Llama（Tool Use 非対応モデル）への対応

Llama 3.1 8B は Native Function Calling（Tool Use）に対応していません。
そのため、**JSON モード** を使用してツール呼び出しをシミュレートします。

#### 方式の違い

```
┌─────────────────────────────────────────────────────────────┐
│ Gemini: Native Function Calling                             │
│                                                             │
│   LLM                          API                          │
│   ├── ツール定義を理解           ├── tool_calls を返す      │
│   ├── 構造化された呼び出し       └── 型安全なパラメータ      │
│   └── 専用のレスポンス形式                                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Llama: JSON モード（プロンプト指示）                         │
│                                                             │
│   システムプロンプト              LLM レスポンス              │
│   ├── ツール定義を記述            ├── JSON 形式で出力       │
│   ├── JSON フォーマット指定       ├── パース処理が必要      │
│   └── 出力形式のルール            └── エラーハンドリング    │
└─────────────────────────────────────────────────────────────┘
```

#### Llama 用の JSON フォーマット

**ツール呼び出し時:**
```json
{
  "thought": "ファイルの内容を確認する必要があります",
  "tool_call": {
    "name": "read_file",
    "input": { "path": "hello.py" }
  }
}
```

**タスク完了時:**
```json
{
  "thought": "ファイルの内容を説明しました",
  "response": "hello.py は greet 関数を定義しています..."
}
```

## セットアップ

### uv を使用（推奨）

```bash
# 依存関係のインストールと実行
uv run ai-agent

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
uv run ai-agent

# プロバイダーを指定
uv run ai-agent --provider gemini
uv run ai-agent --provider llama

# モデルも指定
uv run ai-agent --provider gemini --model gemini-2.0-flash
uv run ai-agent --provider llama --model llama3.1:70b
```

### 対話例

```
> examples/sample_project のファイル一覧を見せて
> hello.py の中身を読んで説明して
> goodbye.py を作成して "print('Goodbye!')" と書いて
```

## ファイル構成

```
├── pyproject.toml            # 依存関係（uv/pip 対応）
├── README.md
├── STUDY_SESSION.md          # 勉強会資料
├── advanced-examples/        # 応用パターン集
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
│       ├── read_file.py      # ファイル読み込み
│       ├── write_file.py     # ファイル書き込み
│       ├── list_files.py     # ディレクトリ一覧
│       └── execute_command.py # シェルコマンド実行
├── examples/
│   └── sample_project/       # テスト用サンプル
│       └── hello.py
└── docs/                     # 詳細解説
```

## ツール一覧

| ツール | 説明 | Claude Code 相当 |
|--------|------|-----------------|
| `read_file` | ファイル内容を読み込む | Read |
| `write_file` | ファイルに書き込む（全体置換） | Write |
| `list_files` | ディレクトリ内容を一覧表示 | Glob |
| `execute_command` | シェルコマンドを実行 | Bash |

## 学びのポイント

### 1. LLM は「判断」のみ、実行はホスト

```
LLM の役割:
  ├── ユーザーの意図を理解
  ├── 適切なツールを選択
  ├── ツールの引数を決定
  └── 結果を解釈して応答

ホスト（Python）の役割:
  ├── ツールの実装と実行
  ├── ファイルシステムへのアクセス
  ├── シェルコマンドの実行
  └── セキュリティ管理
```

### 2. エージェントループと stop_reason

Think → Act → Observe の繰り返しが AI エージェントの本質：

- **Think**: LLM に次のアクションを問い合わせる
- **Act**: LLM が選んだツールを実行する
- **Observe**: 結果を収集し、次のイテレーションへ

`stop_reason` が `"end_turn"` になるまでループを継続（最大イテレーション数で無限ループ防止）。

### 3. tool_result の扱いはプロバイダーごとに異なる

- **Gemini**: `function_response` として追加
- **Llama**: JSON 形式でユーザーメッセージとして追加

この差異は `llm_clients/` 内で吸収され、エージェントループからは統一されたインターフェースで扱える。

### 4. Tool Use 非対応モデルへの対応

Llama のような Tool Use 非対応モデルでも、JSON モードとプロンプトエンジニアリングで
エージェント構築が可能。ただし：

- **パース処理** が必要（JSON の構文エラー対応）
- **プロンプト設計** が重要（明確なフォーマット指示）
- **信頼性** は Native Function Calling より低い

### 5. マルチプロバイダー対応の設計

```
BaseLLMClient (抽象クラス)
    │
    ├── GeminiClient
    │     └── Native Function Calling
    │
    └── LlamaClient
          └── JSON モード（プロンプト指示）
```

共通インターフェース（`chat()`, `format_assistant_message()` など）を定義し、
各プロバイダーの差異は個別クライアントで吸収します。
