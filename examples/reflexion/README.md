# Self-Reflection（Reflexion）パターン

エージェントが自身の出力を批評し、失敗から学習して改善するパターンです。

## 概要

研究によると、Self-Reflection を使用するエージェントは、
使用しないエージェントよりも統計的に有意に高いパフォーマンスを示します（p < 0.001）。

特に、より多くの情報を含む反省（Explanation, Instructions, Solution）が効果的です。

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                    Reflexion Architecture                        │
│                                                                  │
│  ┌──────────┐     ┌──────────┐     ┌──────────────────────┐    │
│  │  Actor   │────▶│ Evaluator│────▶│   Self-Reflection    │    │
│  │  (実行)  │     │  (評価)  │     │   (反省・改善案)     │    │
│  └──────────┘     └──────────┘     └──────────────────────┘    │
│       ▲                                        │                │
│       │                                        ▼                │
│       │              ┌────────────────────────────────────┐    │
│       └──────────────│        Episodic Memory            │    │
│                      │  (過去の試行と反省を蓄積)          │    │
│                      └────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## 反省の種類と効果

| 反省タイプ | 情報量 | 効果 |
|-----------|-------|------|
| Retry（再試行のみ） | 低 | △ |
| Keywords（キーワード） | 低 | △ |
| Advice（アドバイス） | 中 | ○ |
| Explanation（説明） | 高 | ◎ |
| Instructions（具体的指示） | 高 | ◎ |
| Solution（解決策付き） | 最高 | ◎◎ |

## 使用方法

```python
from reflexion import ReflexionAgent, SimpleActor, SimpleEvaluator, SimpleReflectionGenerator

# コンポーネントを作成
actor = SimpleActor()
evaluator = SimpleEvaluator()
reflection_gen = SimpleReflectionGenerator()

# エージェントを作成
agent = ReflexionAgent(
    actor=actor,
    evaluator=evaluator,
    reflection_generator=reflection_gen,
    max_trials=3,
    success_threshold=0.9,
)

# タスクを実行（自動的に反省と再試行）
result, trials = agent.run("複雑な計算タスクを実行")

# 学習内容を確認
print(agent.get_learning_summary())
```

## 主要コンポーネント

### Actor

タスクを実行し、アクションと結果を返します。

```python
class Actor(ABC):
    @abstractmethod
    def execute(self, task: str, past_reflections: list[Reflection]) -> tuple[str, str]:
        """タスクを実行し、(action, result)を返す"""
        pass
```

### Evaluator

結果を評価し、成功/部分成功/失敗を判定します。

```python
class Evaluator(ABC):
    @abstractmethod
    def evaluate(self, task: str, action: str, result: str) -> Evaluation:
        """結果を評価"""
        pass
```

### ReflectionGenerator

失敗時に反省を生成します。

```python
class ReflectionGenerator(ABC):
    @abstractmethod
    def generate(self, task: str, trial: Trial, past_reflections: list) -> Reflection:
        """反省を生成"""
        pass
```

## Multi-Agent Reflexion (MAR)

単一エージェントの Self-Reflection の限界（認知的硬直、思考の退化）を
克服するため、複数の批評エージェントが異なる視点から分析します。

```
Actor ──▶ 失敗 ──▶ 複数のCritic（異なるペルソナ）
                         │
                         ▼
                    構造化された議論
                         │
                         ▼
                    統合された改善案
```

## 参考文献

- [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366)
- [Self-Reflection in LLM Agents: Effects on Problem-Solving Performance](https://arxiv.org/abs/2405.06682)
- [Multi-Agent Reflexion (MAR)](https://arxiv.org/html/2512.20845)
- [Self-reflection enhances large language models](https://www.nature.com/articles/s44387-025-00045-3)

## ファイル

- [reflexion.py](./reflexion.py) - 実装コード
