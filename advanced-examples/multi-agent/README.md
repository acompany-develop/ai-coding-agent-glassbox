# マルチエージェントパターン

複数のエージェントが協調して問題を解決するパターンです。

## 概要

単一エージェントでは対処が難しい複雑なタスクを、
複数の専門化されたエージェントに分割して解決します。

## パターン比較

| パターン | 構造 | 使用場面 |
|---------|------|---------|
| Agents as Tools | 親→子（関数呼び出し） | 専門化されたサブタスク |
| Hierarchical | 階層構造 | 大規模タスクの分割 |
| Debate | 対等な議論 | 意思決定の質向上 |
| Swarm | 自律分散 | 並列探索 |

## パターン1: Agents as Tools

親エージェント（Orchestrator）が子エージェントをツール/関数として呼び出します。

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agents as Tools Pattern                       │
│                                                                  │
│                    ┌────────────────┐                           │
│                    │  Root Agent    │                           │
│                    │  (Orchestrator)│                           │
│                    └───────┬────────┘                           │
│                            │                                     │
│              ┌─────────────┼─────────────┐                      │
│              ▼             ▼             ▼                      │
│     ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│     │ Code Agent │ │ Test Agent │ │ Doc Agent  │               │
│     │ (as Tool)  │ │ (as Tool)  │ │ (as Tool)  │               │
│     └────────────┘ └────────────┘ └────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

**特徴:**
- コンテキストは明示的にスコープ（履歴全体は渡さない）
- Root が全体の制御フローを管理
- トークン効率が良い

### 使用方法

```python
from multi_agent import AgentsAsToolsOrchestrator, CodeAgent, TestAgent

orchestrator = AgentsAsToolsOrchestrator()
orchestrator.register_agent("code", CodeAgent(), required_context=["language"])
orchestrator.register_agent("test", TestAgent(), required_context=["code"])

# コンテキストをスコープして子エージェントを呼び出し
result = orchestrator.call_agent(
    "code",
    "Create a user service",
    full_context={"language": "Python", "sensitive_data": "..."}
)
```

## パターン2: Multi-Agent Debate

複数のエージェントが異なる視点から議論し、より良い意思決定を行います。

```
┌─────────────────────────────────────────────────────────────────┐
│                   Multi-Agent Debate Pattern                     │
│                                                                  │
│     ┌──────────┐   ┌──────────┐   ┌──────────┐                 │
│     │ Critic A │   │ Critic B │   │ Critic C │                 │
│     │(セキュリティ)│ │(パフォーマンス)│ │(可読性) │                 │
│     └────┬─────┘   └────┬─────┘   └────┬─────┘                 │
│          │              │              │                        │
│          └──────────────┼──────────────┘                        │
│                         ▼                                        │
│              ┌────────────────────┐                             │
│              │     Synthesizer    │                             │
│              │  (意見を統合)       │                             │
│              └────────────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

**用途:**
- コードレビュー（複数の観点から評価）
- 難しい設計判断
- Self-Reflection の強化版

### 使用方法

```python
from multi_agent import DebateOrchestrator, DebateAgent

debate = DebateOrchestrator()
debate.add_critic(DebateAgent("security_expert", "セキュリティ"))
debate.add_critic(DebateAgent("performance_expert", "パフォーマンス"))
debate.add_critic(DebateAgent("readability_expert", "可読性"))

result = debate.debate("この認証実装は適切か？")
print(result["synthesis"])
```

## パターン3: Hierarchical（階層構造）

大規模タスクを階層的に分割し、適切なエージェントに割り当てます。

```
Root Task
├── Subtask A (assigned to Agent A)
│   ├── Sub-subtask A1
│   └── Sub-subtask A2
├── Subtask B (assigned to Agent B)
└── Subtask C (assigned to Agent C)
```

## パターン4: Swarm（自律分散）

複数のエージェントが自律的に探索し、結果を共有します。

```python
from multi_agent import SwarmOrchestrator, SwarmAgent

swarm = SwarmOrchestrator()
swarm.add_agent(SwarmAgent("explorer1", "security"))
swarm.add_agent(SwarmAgent("explorer2", "performance"))

results = await swarm.search(codebase_files)
```

## コンテキスト管理の重要性

マルチエージェントシステムでは、コンテキスト肥大化が問題になります。

**問題:**
- 親エージェントの全履歴を子に渡すとトークン数が爆発
- 無関係なコンテキストがノイズになる

**解決策:**
- 必要なコンテキストのみを明示的にスコープ
- 最新のクエリと必要な成果物のみを渡す

```python
def scope_context(full_context: dict, required_keys: list) -> dict:
    """必要なキーのみを抽出"""
    return {k: v for k, v in full_context.items() if k in required_keys}
```

## 参考文献

- [Google ADK Multi-Agent Framework](https://developers.googleblog.com/architecting-efficient-context-aware-multi-agent-framework-for-production/)
- [The Ultimate Guide to AI Agent Architectures in 2025](https://dev.to/sohail-akbar/the-ultimate-guide-to-ai-agent-architectures-in-2025-2j1c)
- [Agentic AI Design Patterns](https://medium.com/@balarampanda.ai/agentic-ai-design-patterns-choosing-the-right-multimodal-multi-agent-architecture-2022-2025-046a37eb6dbe)

## ファイル

- [multi_agent.py](./multi_agent.py) - 実装コード
