# 00. 全体像

minimal/ をベースに、より実用的なツールを追加した拡張版です。
教育目的で、各ツールの役割と設計思想を理解できる構成になっています。

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

## アーキテクチャ図

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                               │
│                    (エントリーポイント)                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Agent (agent.py)                        │
│                                                             │
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
│                  │  │                                     │
│  ┌────────────┐  │  │  基本ツール (minimal/ と同じ)       │
│  │  Gemini    │  │  │  ┌─────────┐ ┌─────────┐          │
│  ├────────────┤  │  │  │read_file│ │write_file│  ...     │
│  │  Llama     │  │  │  └─────────┘ └─────────┘          │
│  └────────────┘  │  │                                     │
│                  │  │  拡張ツール (standard/ で追加)      │
└──────────────────┘  │  ┌─────────┐ ┌─────────┐ ┌───────┐ │
                      │  │edit_file│ │  grep   │ │ glob  │ │
                      │  ├─────────┤ ├─────────┤ ├───────┤ │
                      │  │web_fetch│ │ask_user │ │       │ │
                      │  └─────────┘ └─────────┘ └───────┘ │
                      └─────────────────────────────────────┘
```

## ファイル構成

```
standard/src/
├── main.py              # エントリーポイント
├── agent.py             # エージェントループ
├── tool_registry.py     # ツール管理
├── message_history.py   # 会話履歴
├── colors.py            # CLI カラー出力
├── llm_clients/         # LLM クライアント
│   ├── base.py
│   ├── gemini_client.py
│   └── llama_client.py
└── tools/
    ├── base.py
    │
    │  # 基本ツール（minimal/ と同じ）
    ├── read_file.py
    ├── write_file.py
    ├── list_files.py
    ├── execute_command.py
    │
    │  # 拡張ツール（standard/ で追加）
    ├── edit_file.py      # 差分編集
    ├── grep.py           # 正規表現検索
    ├── glob_tool.py      # パターンマッチング
    ├── web_fetch.py      # URL 取得
    └── ask_user.py       # ユーザー確認
```

## ドキュメント一覧

| ファイル | 内容 |
|---------|------|
| [01-agent-loop.md](./01-agent-loop.md) | エージェントループの仕組み |
| [02-tool-use.md](./02-tool-use.md) | Tool Use（Function Calling）の詳細 |
| [03-llm-clients.md](./03-llm-clients.md) | LLM クライアントの抽象化 |
| [04-tools-basic.md](./04-tools-basic.md) | 基本ツールの実装 |
| [05-tools-extended.md](./05-tools-extended.md) | **拡張ツールの実装** |
| [06-message-history.md](./06-message-history.md) | メッセージ履歴の管理 |
| [07-stop-reason.md](./07-stop-reason.md) | stop_reason による状態遷移 |

**付録**

| ファイル | 内容 |
|---------|------|
| [A1-agent-patterns.md](./A1-agent-patterns.md) | エージェントループの実装パターン |
| [A2-tool-use-implementations.md](./A2-tool-use-implementations.md) | Tool Use の実装方式 |
| [A3-existing-agents.md](./A3-existing-agents.md) | 既存の AI Coding Agent の実装比較 |

## 読む順序

1. **01-agent-loop.md** でエージェントの基本動作を理解
2. **02-tool-use.md** で LLM とツールの連携を理解
3. **05-tools-extended.md** で standard/ 固有のツールを理解
4. 残りは興味に応じて
