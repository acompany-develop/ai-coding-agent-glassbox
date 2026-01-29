# AI Coding Agent パターン集

AI Coding Agent を構築するための主要なパターンと実装例です。

## パターン一覧

| パターン | 説明 | 用途 |
|---------|------|------|
| [plan-and-execute](./plan-and-execute/) | 計画→実行の2フェーズ | 複雑な複数ステップのタスク |
| [memory](./memory/) | 階層的メモリ管理 | 長期タスク、学習 |
| [reflexion](./reflexion/) | 自己反省・自己改善 | 精度向上、エラー修正 |
| [multi-agent](./multi-agent/) | マルチエージェント協調 | タスク分割、議論 |
| [code-rag](./code-rag/) | コードベース検索 | 大規模リポジトリ対応 |
| [error-recovery](./error-recovery/) | エラーリカバリー | 信頼性向上 |
| [sandbox](./sandbox/) | サンドボックス実行 | セキュリティ |

## エージェントループパターン比較

### ReAct（minimal/, standard/ で実装）

```
Think → Act → Observe → Think → Act → Observe → ...
```

- **特徴**: 1ステップずつ判断、即応性が高い
- **用途**: シンプルなタスク、対話型

### Plan-and-Execute

```
Plan（全体計画）→ Execute（順次実行）→ Replan（必要に応じて修正）
```

- **特徴**: 事前に全体を計画、精度が高い
- **用途**: 複雑なタスク、高精度が必要な場面

## パターン選択ガイド

| 要件 | 推奨パターン |
|------|------------|
| シンプルなタスク | ReAct（minimal/） |
| 複雑な複数ステップ | Plan-and-Execute |
| 長時間のタスク | Memory + Checkpoint |
| 高精度が必要 | Reflexion + Multi-Agent Debate |
| 大規模コードベース | Code RAG |
| 本番環境の信頼性 | Error Recovery |
| ユーザーコード実行 | Sandbox（MicroVM推奨） |

## ディレクトリ構成

```
examples/
├── README.md               # この文書
├── plan-and-execute/       # Plan-and-Execute パターン
│   ├── README.md
│   ├── plan_execute_agent.py
│   └── dag_executor.py
├── memory/                 # メモリ管理パターン
│   ├── README.md
│   └── memory.py
├── reflexion/              # Self-Reflection パターン
│   ├── README.md
│   └── reflexion.py
├── multi-agent/            # マルチエージェントパターン
│   ├── README.md
│   └── multi_agent.py
├── code-rag/               # コードベース用RAG
│   ├── README.md
│   └── code_rag.py
├── error-recovery/         # エラーリカバリーパターン
│   ├── README.md
│   └── error_recovery.py
└── sandbox/                # サンドボックスパターン
    ├── README.md
    └── sandbox.py
```

## minimal/ / standard/ との関係

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI Coding Agent 実装                          │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  minimal/   │  │  standard/  │  │     examples/           │ │
│  │             │  │             │  │                         │ │
│  │  基本的な   │  │  実用的な   │  │  高度なパターンの       │ │
│  │  ReAct      │  │  ReAct +    │  │  参考実装               │ │
│  │  エージェント │  │  拡張ツール │  │                         │ │
│  │             │  │             │  │  • Plan-and-Execute    │ │
│  │  4 tools    │  │  9 tools    │  │  • Memory              │ │
│  │             │  │             │  │  • Reflexion           │ │
│  │             │  │             │  │  • Multi-Agent         │ │
│  │             │  │             │  │  • Code RAG            │ │
│  │             │  │             │  │  • Error Recovery      │ │
│  │             │  │             │  │  • Sandbox             │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
│                                                                  │
│       学習用                 実用                  発展            │
└─────────────────────────────────────────────────────────────────┘
```

## 参考文献

### エージェントパターン
- [LangGraph Plan-and-Execute](https://langchain-ai.github.io/langgraph/tutorials/plan-and-execute/plan-and-execute/)
- [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366)
- [Google ADK Multi-Agent Framework](https://developers.googleblog.com/architecting-efficient-context-aware-multi-agent-framework-for-production/)

### メモリ・RAG
- [Memory in the Age of AI Agents Survey](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)
- [RAG for a Codebase with 10k Repos](https://www.qodo.ai/blog/rag-for-large-scale-code-repos/)

### 信頼性・セキュリティ
- [Why Most AI Agents Fail & How to Fix Them](https://galileo.ai/blog/why-most-ai-agents-fail-and-how-to-fix-them)
- [Code Sandboxes for LLMs and AI Agents](https://amirmalik.net/2025/03/07/code-sandboxes-for-llm-ai-agents)
