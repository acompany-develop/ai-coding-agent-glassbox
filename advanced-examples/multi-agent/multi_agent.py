"""
マルチエージェントシステム

複数のエージェントが協調して問題を解決するパターンを実装します。

パターン:
1. Agents as Tools: 親エージェントが子エージェントを関数として呼び出し
2. Hierarchical: 階層構造で大規模タスクを分割
3. Debate: 複数の視点から議論して意思決定
4. Swarm: 自律分散で並列探索
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


# =============================================================================
# データ構造
# =============================================================================


@dataclass
class Message:
    """エージェント間のメッセージ"""

    sender: str
    receiver: str
    content: str
    message_type: str = "task"  # task, result, feedback, question
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentCapability:
    """エージェントの能力定義"""

    name: str
    description: str
    required_context: list[str] = field(default_factory=list)


@dataclass
class DebateOpinion:
    """議論での意見"""

    agent_name: str
    perspective: str  # セキュリティ、パフォーマンス、可読性など
    opinion: str
    confidence: float  # 0.0 - 1.0
    evidence: list[str] = field(default_factory=list)


# =============================================================================
# 基底クラス
# =============================================================================


class Agent(ABC):
    """エージェントの抽象基底クラス"""

    def __init__(self, name: str, capabilities: list[AgentCapability] = None):
        self.name = name
        self.capabilities = capabilities or []
        self.message_bus: MessageBus | None = None

    def set_message_bus(self, bus: "MessageBus") -> None:
        self.message_bus = bus

    @abstractmethod
    def execute(self, task: str, context: dict) -> str:
        """タスクを実行"""
        pass

    def send_message(self, receiver: str, content: str, **kwargs) -> None:
        """他のエージェントにメッセージを送信"""
        if self.message_bus:
            msg = Message(sender=self.name, receiver=receiver, content=content, **kwargs)
            self.message_bus.send(msg)

    def receive_messages(self) -> list[Message]:
        """自分宛のメッセージを受信"""
        if self.message_bus:
            return self.message_bus.receive(self.name)
        return []


class MessageBus:
    """エージェント間のメッセージバス"""

    def __init__(self):
        self.messages: dict[str, list[Message]] = {}

    def send(self, message: Message) -> None:
        """メッセージを送信"""
        if message.receiver not in self.messages:
            self.messages[message.receiver] = []
        self.messages[message.receiver].append(message)

    def receive(self, agent_name: str) -> list[Message]:
        """メッセージを受信"""
        messages = self.messages.get(agent_name, [])
        self.messages[agent_name] = []
        return messages


# =============================================================================
# パターン1: Agents as Tools
# =============================================================================


class AgentsAsToolsOrchestrator:
    """
    Agents as Tools パターン

    親エージェント（Orchestrator）が子エージェントを
    ツール/関数として呼び出すパターン。

    特徴:
    - コンテキストは明示的にスコープ
    - 親が全体の制御フローを管理
    - 子は特化されたタスクのみ実行
    """

    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.context_scopes: dict[str, list[str]] = {}

    def register_agent(
        self,
        name: str,
        agent: Agent,
        required_context: list[str] = None,
    ) -> None:
        """エージェントを登録"""
        self.agents[name] = agent
        self.context_scopes[name] = required_context or []

    def call_agent(
        self,
        agent_name: str,
        task: str,
        full_context: dict,
    ) -> str:
        """エージェントをツールとして呼び出し"""
        if agent_name not in self.agents:
            raise ValueError(f"Unknown agent: {agent_name}")

        agent = self.agents[agent_name]

        # コンテキストをスコープ（必要な情報のみ渡す）
        scoped_context = self._scope_context(agent_name, full_context)

        print(f"  [CALL] {agent_name} with scoped context: {list(scoped_context.keys())}")

        return agent.execute(task, scoped_context)

    def _scope_context(self, agent_name: str, full_context: dict) -> dict:
        """コンテキストを必要な範囲に制限"""
        required = self.context_scopes.get(agent_name, [])
        if not required:
            # 何も指定がなければ最小限のコンテキスト
            return {"task_id": full_context.get("task_id")}

        return {k: v for k, v in full_context.items() if k in required}


# =============================================================================
# パターン2: Hierarchical（階層構造）
# =============================================================================


@dataclass
class HierarchicalTask:
    """階層的タスク"""

    id: str
    description: str
    subtasks: list["HierarchicalTask"] = field(default_factory=list)
    assigned_agent: str | None = None
    result: str | None = None
    status: str = "pending"


class HierarchicalOrchestrator:
    """
    階層的マルチエージェント

    大規模タスクを階層的に分割し、
    適切なエージェントに割り当てます。
    """

    def __init__(self, planner_llm: Any = None):
        self.agents: dict[str, Agent] = {}
        self.planner = planner_llm

    def register_agent(self, agent: Agent) -> None:
        self.agents[agent.name] = agent

    async def execute(self, root_task: HierarchicalTask) -> str:
        """階層的タスクを実行"""
        return await self._execute_task(root_task)

    async def _execute_task(self, task: HierarchicalTask) -> str:
        """タスクを再帰的に実行"""
        print(f"  [TASK] {task.id}: {task.description}")

        # サブタスクがあれば先に実行
        if task.subtasks:
            # 依存関係がなければ並列実行
            subtask_results = await asyncio.gather(
                *[self._execute_task(st) for st in task.subtasks]
            )

            # サブタスクの結果を統合
            context = {"subtask_results": dict(zip(
                [st.id for st in task.subtasks],
                subtask_results
            ))}
        else:
            context = {}

        # 割り当てられたエージェントで実行
        if task.assigned_agent and task.assigned_agent in self.agents:
            agent = self.agents[task.assigned_agent]
            task.result = agent.execute(task.description, context)
            task.status = "completed"
        else:
            task.result = f"Completed: {task.description}"
            task.status = "completed"

        return task.result


# =============================================================================
# パターン3: Multi-Agent Debate
# =============================================================================


class DebateAgent(Agent):
    """議論に参加するエージェント"""

    def __init__(self, name: str, perspective: str, llm: Any = None):
        super().__init__(name)
        self.perspective = perspective
        self.llm = llm

    def execute(self, task: str, context: dict) -> str:
        """タスクを実行（議論では使用しない）"""
        return ""

    def critique(self, topic: str, context: dict = None) -> DebateOpinion:
        """トピックについて意見を述べる"""
        # LLMがあれば使用、なければシンプルな実装
        opinion_text = f"[{self.perspective}視点] {topic}について: "
        opinion_text += f"{self.perspective}の観点から分析すると..."

        return DebateOpinion(
            agent_name=self.name,
            perspective=self.perspective,
            opinion=opinion_text,
            confidence=0.8,
        )


class DebateOrchestrator:
    """
    Multi-Agent Debate パターン

    複数のエージェントが異なる視点から議論し、
    より良い意思決定を行います。

    用途:
    - コードレビュー（セキュリティ、パフォーマンス、可読性）
    - 設計判断
    - Self-Reflection の強化
    """

    def __init__(self, synthesizer_llm: Any = None):
        self.critics: list[DebateAgent] = []
        self.synthesizer = synthesizer_llm
        self.debate_rounds = 2

    def add_critic(self, agent: DebateAgent) -> None:
        """批評エージェントを追加"""
        self.critics.append(agent)

    def debate(self, topic: str, context: dict = None) -> dict:
        """議論を実行"""
        print(f"\n{'=' * 50}")
        print(f"Debate: {topic}")
        print("=" * 50)

        all_opinions: list[DebateOpinion] = []

        for round_num in range(1, self.debate_rounds + 1):
            print(f"\n--- Round {round_num} ---")

            round_context = context or {}
            if all_opinions:
                round_context["previous_opinions"] = [
                    {"agent": o.agent_name, "opinion": o.opinion}
                    for o in all_opinions
                ]

            for critic in self.critics:
                opinion = critic.critique(topic, round_context)
                all_opinions.append(opinion)
                print(f"\n[{critic.name} ({critic.perspective})]")
                print(f"  Opinion: {opinion.opinion[:100]}...")
                print(f"  Confidence: {opinion.confidence:.2f}")

        # 意見を統合
        synthesis = self._synthesize(topic, all_opinions)

        return {
            "topic": topic,
            "opinions": all_opinions,
            "synthesis": synthesis,
        }

    def _synthesize(self, topic: str, opinions: list[DebateOpinion]) -> str:
        """意見を統合"""
        # 信頼度の加重平均などを計算
        perspectives = {}
        for op in opinions:
            if op.perspective not in perspectives:
                perspectives[op.perspective] = []
            perspectives[op.perspective].append(op)

        synthesis = f"議論の結論: {topic}\n\n"
        for perspective, ops in perspectives.items():
            avg_confidence = sum(o.confidence for o in ops) / len(ops)
            synthesis += f"- {perspective}: 平均信頼度 {avg_confidence:.2f}\n"
            synthesis += f"  最終意見: {ops[-1].opinion[:100]}...\n"

        return synthesis


# =============================================================================
# パターン4: Swarm（簡易版）
# =============================================================================


class SwarmAgent(Agent):
    """Swarmエージェント"""

    def __init__(self, name: str, search_strategy: str):
        super().__init__(name)
        self.search_strategy = search_strategy
        self.discovered: list[str] = []

    def execute(self, task: str, context: dict) -> str:
        # シンプルな実装
        return f"[{self.name}] Found using {self.search_strategy}: {task}"

    def explore(self, search_space: list[str]) -> list[str]:
        """探索を実行"""
        # 戦略に基づいて探索
        results = []
        for item in search_space:
            if self._matches_strategy(item):
                results.append(item)
        self.discovered.extend(results)
        return results

    def _matches_strategy(self, item: str) -> bool:
        """戦略に基づくマッチング（シンプル実装）"""
        return self.search_strategy.lower() in item.lower()


class SwarmOrchestrator:
    """
    Swarm パターン

    複数のエージェントが自律的に探索し、
    結果を共有します。
    """

    def __init__(self):
        self.agents: list[SwarmAgent] = []
        self.shared_discoveries: list[str] = []

    def add_agent(self, agent: SwarmAgent) -> None:
        self.agents.append(agent)

    async def search(self, search_space: list[str]) -> list[str]:
        """並列で探索を実行"""
        tasks = []
        for agent in self.agents:
            # 各エージェントに探索を割り当て
            task = asyncio.create_task(
                asyncio.to_thread(agent.explore, search_space)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # 結果を統合（重複除去）
        all_discoveries = set()
        for agent_results in results:
            all_discoveries.update(agent_results)

        self.shared_discoveries = list(all_discoveries)
        return self.shared_discoveries


# =============================================================================
# サンプルエージェント
# =============================================================================


class CodeAgent(Agent):
    """コード生成エージェント"""

    def __init__(self):
        super().__init__(
            name="code_agent",
            capabilities=[
                AgentCapability(
                    name="code_generation",
                    description="コードを生成する",
                    required_context=["language", "requirements"],
                )
            ],
        )

    def execute(self, task: str, context: dict) -> str:
        lang = context.get("language", "Python")
        return f"Generated {lang} code for: {task}"


class TestAgent(Agent):
    """テスト生成エージェント"""

    def __init__(self):
        super().__init__(
            name="test_agent",
            capabilities=[
                AgentCapability(
                    name="test_generation",
                    description="テストを生成する",
                    required_context=["code", "framework"],
                )
            ],
        )

    def execute(self, task: str, context: dict) -> str:
        framework = context.get("framework", "pytest")
        return f"Generated {framework} tests for: {task}"


class ReviewAgent(Agent):
    """コードレビューエージェント"""

    def __init__(self):
        super().__init__(
            name="review_agent",
            capabilities=[
                AgentCapability(
                    name="code_review",
                    description="コードをレビューする",
                    required_context=["code"],
                )
            ],
        )

    def execute(self, task: str, context: dict) -> str:
        return f"Reviewed code: {task}. No issues found."


# =============================================================================
# デモ
# =============================================================================


async def main():
    """デモ実行"""
    print("\n" + "#" * 60)
    print("# Multi-Agent Systems Demo")
    print("#" * 60)

    # パターン1: Agents as Tools
    print("\n" + "=" * 50)
    print("Pattern 1: Agents as Tools")
    print("=" * 50)

    orchestrator = AgentsAsToolsOrchestrator()
    orchestrator.register_agent(
        "code", CodeAgent(), required_context=["language", "requirements"]
    )
    orchestrator.register_agent(
        "test", TestAgent(), required_context=["code", "framework"]
    )
    orchestrator.register_agent("review", ReviewAgent(), required_context=["code"])

    full_context = {
        "task_id": "task-001",
        "language": "Python",
        "requirements": "REST API",
        "framework": "pytest",
        "code": "...",
        "sensitive_data": "should not be passed",
    }

    result = orchestrator.call_agent("code", "Create a user service", full_context)
    print(f"Result: {result}")

    # パターン3: Debate
    print("\n" + "=" * 50)
    print("Pattern 3: Multi-Agent Debate")
    print("=" * 50)

    debate = DebateOrchestrator()
    debate.add_critic(DebateAgent("security_expert", "セキュリティ"))
    debate.add_critic(DebateAgent("performance_expert", "パフォーマンス"))
    debate.add_critic(DebateAgent("readability_expert", "可読性"))

    result = debate.debate("この認証実装は適切か？")
    print("\n" + result["synthesis"])


if __name__ == "__main__":
    asyncio.run(main())
