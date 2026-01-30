"""
Self-Reflection（Reflexion）エージェント

エージェントが自身の出力を批評し、失敗から学習して改善するパターンです。

アーキテクチャ:
1. Actor: タスクを実行
2. Evaluator: 結果を評価
3. Self-Reflection: 失敗を分析し改善案を生成
4. Episodic Memory: 過去の試行と反省を蓄積

参考: Reflexion: Language Agents with Verbal Reinforcement Learning
https://arxiv.org/abs/2303.11366
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# =============================================================================
# データ構造
# =============================================================================


class EvaluationResult(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


@dataclass
class Evaluation:
    """評価結果"""

    result: EvaluationResult
    score: float  # 0.0 - 1.0
    feedback: str
    details: dict = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.result == EvaluationResult.SUCCESS


@dataclass
class Reflection:
    """反省内容"""

    trial_number: int
    task: str
    action_taken: str
    evaluation: Evaluation
    what_went_wrong: str
    why_it_happened: str
    how_to_improve: str
    timestamp: float = field(default_factory=lambda: __import__("time").time())

    def to_prompt(self) -> str:
        """プロンプトに含める形式に変換"""
        return f"""
Trial {self.trial_number}:
- Action: {self.action_taken}
- Result: {self.evaluation.result.value} (score: {self.evaluation.score:.2f})
- What went wrong: {self.what_went_wrong}
- Why: {self.why_it_happened}
- Improvement: {self.how_to_improve}
"""


@dataclass
class Trial:
    """1回の試行"""

    number: int
    action: str
    result: str
    evaluation: Evaluation
    reflection: Reflection | None = None


# =============================================================================
# コンポーネント
# =============================================================================


class Actor(ABC):
    """タスクを実行するコンポーネント"""

    @abstractmethod
    def execute(
        self, task: str, past_reflections: list[Reflection]
    ) -> tuple[str, str]:
        """
        タスクを実行

        Args:
            task: 実行するタスク
            past_reflections: 過去の反省リスト

        Returns:
            (action, result): 取ったアクションと結果
        """
        pass


class Evaluator(ABC):
    """結果を評価するコンポーネント"""

    @abstractmethod
    def evaluate(self, task: str, action: str, result: str) -> Evaluation:
        """
        結果を評価

        Args:
            task: 元のタスク
            action: 取ったアクション
            result: 実行結果

        Returns:
            Evaluation: 評価結果
        """
        pass


class ReflectionGenerator(ABC):
    """反省を生成するコンポーネント"""

    @abstractmethod
    def generate(
        self,
        task: str,
        trial: Trial,
        past_reflections: list[Reflection],
    ) -> Reflection:
        """
        反省を生成

        Args:
            task: 元のタスク
            trial: 今回の試行
            past_reflections: 過去の反省

        Returns:
            Reflection: 生成された反省
        """
        pass


# =============================================================================
# LLMベースの実装
# =============================================================================


class LLMActor(Actor):
    """LLMを使用したActor"""

    def __init__(self, llm_client: Any):
        self.llm = llm_client

    def execute(
        self, task: str, past_reflections: list[Reflection]
    ) -> tuple[str, str]:
        # 過去の反省を含むプロンプトを構築
        reflection_context = ""
        if past_reflections:
            reflection_context = """
過去の試行からの学び:
""" + "\n".join(r.to_prompt() for r in past_reflections[-3:])  # 直近3件

        prompt = f"""あなたはタスクを実行するエージェントです。

タスク: {task}

{reflection_context}

過去の失敗から学び、より良いアプローチを取ってください。

実行するアクションを説明し、その結果を返してください。

出力形式:
{{
    "action": "取るアクションの説明",
    "result": "アクションの結果"
}}
"""

        response = self.llm.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        try:
            data = json.loads(
                re.search(r"\{[\s\S]*\}", response.text).group()
            )
            return data.get("action", ""), data.get("result", "")
        except (json.JSONDecodeError, AttributeError):
            return response.text, "結果を解析できませんでした"


class LLMEvaluator(Evaluator):
    """LLMを使用したEvaluator"""

    def __init__(self, llm_client: Any, success_criteria: str = ""):
        self.llm = llm_client
        self.success_criteria = success_criteria

    def evaluate(self, task: str, action: str, result: str) -> Evaluation:
        prompt = f"""あなたはタスク実行の評価者です。

タスク: {task}
成功基準: {self.success_criteria or "タスクが正しく完了すること"}

実行されたアクション:
{action}

結果:
{result}

この結果を評価してください。

出力形式:
{{
    "result": "success" | "partial" | "failure",
    "score": 0.0-1.0,
    "feedback": "評価の詳細"
}}
"""

        response = self.llm.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        try:
            data = json.loads(
                re.search(r"\{[\s\S]*\}", response.text).group()
            )
            result_str = data.get("result", "failure")
            return Evaluation(
                result=EvaluationResult(result_str),
                score=float(data.get("score", 0.0)),
                feedback=data.get("feedback", ""),
            )
        except (json.JSONDecodeError, AttributeError, ValueError):
            return Evaluation(
                result=EvaluationResult.FAILURE,
                score=0.0,
                feedback="評価を解析できませんでした",
            )


class LLMReflectionGenerator(ReflectionGenerator):
    """LLMを使用した反省生成"""

    def __init__(self, llm_client: Any):
        self.llm = llm_client

    def generate(
        self,
        task: str,
        trial: Trial,
        past_reflections: list[Reflection],
    ) -> Reflection:
        past_context = ""
        if past_reflections:
            past_context = """
過去の反省:
""" + "\n".join(r.to_prompt() for r in past_reflections[-3:])

        prompt = f"""あなたはタスク実行の反省を行うエージェントです。

タスク: {task}

今回の試行:
- アクション: {trial.action}
- 結果: {trial.result}
- 評価: {trial.evaluation.result.value} (score: {trial.evaluation.score:.2f})
- フィードバック: {trial.evaluation.feedback}

{past_context}

この試行を深く分析し、次回の改善につなげる反省を生成してください。

重要: 具体的で実行可能な改善案を含めてください。

出力形式:
{{
    "what_went_wrong": "何が問題だったか",
    "why_it_happened": "なぜその問題が発生したか",
    "how_to_improve": "次回どう改善すべきか（具体的な手順）"
}}
"""

        response = self.llm.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        try:
            data = json.loads(
                re.search(r"\{[\s\S]*\}", response.text).group()
            )
            return Reflection(
                trial_number=trial.number,
                task=task,
                action_taken=trial.action,
                evaluation=trial.evaluation,
                what_went_wrong=data.get("what_went_wrong", ""),
                why_it_happened=data.get("why_it_happened", ""),
                how_to_improve=data.get("how_to_improve", ""),
            )
        except (json.JSONDecodeError, AttributeError):
            return Reflection(
                trial_number=trial.number,
                task=task,
                action_taken=trial.action,
                evaluation=trial.evaluation,
                what_went_wrong="分析できませんでした",
                why_it_happened="不明",
                how_to_improve="再試行してください",
            )


# =============================================================================
# Reflexion エージェント
# =============================================================================


class ReflexionAgent:
    """
    Reflexion エージェント

    自己反省を通じて学習し、タスクの成功率を向上させます。

    使用方法:
        agent = ReflexionAgent(actor, evaluator, reflection_generator)
        result = agent.run(task, max_trials=3)
    """

    def __init__(
        self,
        actor: Actor,
        evaluator: Evaluator,
        reflection_generator: ReflectionGenerator,
        max_trials: int = 3,
        success_threshold: float = 0.8,
    ):
        self.actor = actor
        self.evaluator = evaluator
        self.reflection_generator = reflection_generator
        self.max_trials = max_trials
        self.success_threshold = success_threshold

        # Episodic Memory: 過去の反省を蓄積
        self.reflection_memory: list[Reflection] = []
        self.trial_history: list[Trial] = []

    def run(self, task: str) -> tuple[str, list[Trial]]:
        """
        タスクを実行（最大max_trials回試行）

        Args:
            task: 実行するタスク

        Returns:
            (best_result, trials): 最良の結果と試行履歴
        """
        print(f"\n{'=' * 60}")
        print(f"Reflexion Agent: {task}")
        print("=" * 60)

        trials = []
        best_result = ""
        best_score = 0.0

        for trial_num in range(1, self.max_trials + 1):
            print(f"\n--- Trial {trial_num}/{self.max_trials} ---")

            # 1. Actor: タスクを実行
            print("  [ACTOR] Executing task...")
            action, result = self.actor.execute(task, self.reflection_memory)
            print(f"  Action: {action[:100]}...")

            # 2. Evaluator: 結果を評価
            print("  [EVALUATOR] Evaluating result...")
            evaluation = self.evaluator.evaluate(task, action, result)
            print(
                f"  Result: {evaluation.result.value} "
                f"(score: {evaluation.score:.2f})"
            )
            print(f"  Feedback: {evaluation.feedback}")

            # Trial を記録
            trial = Trial(
                number=trial_num,
                action=action,
                result=result,
                evaluation=evaluation,
            )
            trials.append(trial)

            # 最良の結果を更新
            if evaluation.score > best_score:
                best_score = evaluation.score
                best_result = result

            # 成功したら終了
            if evaluation.is_success or evaluation.score >= self.success_threshold:
                print("  [SUCCESS] Task completed successfully!")
                break

            # 最後の試行でなければ反省を生成
            if trial_num < self.max_trials:
                print("  [REFLECTION] Generating reflection...")
                reflection = self.reflection_generator.generate(
                    task, trial, self.reflection_memory
                )
                trial.reflection = reflection
                self.reflection_memory.append(reflection)

                print(f"  What went wrong: {reflection.what_went_wrong}")
                print(f"  Why: {reflection.why_it_happened}")
                print(f"  How to improve: {reflection.how_to_improve}")

        self.trial_history.extend(trials)

        # 結果サマリー
        print(f"\n{'=' * 60}")
        print("Summary")
        print("=" * 60)
        print(f"Total trials: {len(trials)}")
        print(f"Best score: {best_score:.2f}")
        print(f"Final result: {evaluation.result.value}")

        return best_result, trials

    def get_learning_summary(self) -> str:
        """学習した内容のサマリーを取得"""
        if not self.reflection_memory:
            return "まだ反省がありません"

        summary = "学習した教訓:\n"
        for i, reflection in enumerate(self.reflection_memory, 1):
            summary += f"\n{i}. {reflection.how_to_improve}"
        return summary


# =============================================================================
# デモ用のシンプルな実装
# =============================================================================


class SimpleActor(Actor):
    """デモ用のシンプルなActor"""

    def __init__(self):
        self.attempt = 0

    def execute(
        self, task: str, past_reflections: list[Reflection]
    ) -> tuple[str, str]:
        self.attempt += 1

        # 反省からの学習をシミュレート
        learned_tips = [r.how_to_improve for r in past_reflections]

        if self.attempt == 1:
            return "基本的なアプローチで実行", "部分的に成功"
        elif self.attempt == 2:
            return "改善されたアプローチで実行", "ほぼ成功"
        else:
            return "最適化されたアプローチで実行", "完全に成功"


class SimpleEvaluator(Evaluator):
    """デモ用のシンプルなEvaluator"""

    def __init__(self):
        self.call_count = 0

    def evaluate(self, task: str, action: str, result: str) -> Evaluation:
        self.call_count += 1

        if "完全に成功" in result:
            return Evaluation(
                result=EvaluationResult.SUCCESS,
                score=1.0,
                feedback="タスクが正常に完了しました",
            )
        elif "ほぼ成功" in result:
            return Evaluation(
                result=EvaluationResult.PARTIAL,
                score=0.7,
                feedback="大部分は成功しましたが、改善の余地があります",
            )
        else:
            return Evaluation(
                result=EvaluationResult.FAILURE,
                score=0.3,
                feedback="タスクは完了しましたが、品質が不十分です",
            )


class SimpleReflectionGenerator(ReflectionGenerator):
    """デモ用のシンプルな反省生成"""

    def generate(
        self,
        task: str,
        trial: Trial,
        past_reflections: list[Reflection],
    ) -> Reflection:
        return Reflection(
            trial_number=trial.number,
            task=task,
            action_taken=trial.action,
            evaluation=trial.evaluation,
            what_went_wrong="アプローチが最適ではなかった",
            why_it_happened="経験不足による判断ミス",
            how_to_improve="より慎重にアプローチを検討し、エッジケースを考慮する",
        )


# =============================================================================
# メイン
# =============================================================================


def main():
    """デモ実行"""
    print("\n" + "#" * 60)
    print("# Reflexion Agent Demo")
    print("#" * 60)

    # シンプルな実装でデモ
    actor = SimpleActor()
    evaluator = SimpleEvaluator()
    reflection_gen = SimpleReflectionGenerator()

    agent = ReflexionAgent(
        actor=actor,
        evaluator=evaluator,
        reflection_generator=reflection_gen,
        max_trials=3,
        success_threshold=0.9,
    )

    # タスクを実行
    task = "複雑な計算タスクを実行"
    result, trials = agent.run(task)

    print("\n学習サマリー:")
    print(agent.get_learning_summary())


def main_with_llm():
    """LLMを使用したデモ（GEMINI_API_KEY が必要）"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is required")
        return

    from google import genai

    client = genai.Client(api_key=api_key)

    actor = LLMActor(client)
    evaluator = LLMEvaluator(client, success_criteria="正確な結果を返すこと")
    reflection_gen = LLMReflectionGenerator(client)

    agent = ReflexionAgent(
        actor=actor,
        evaluator=evaluator,
        reflection_generator=reflection_gen,
        max_trials=3,
    )

    task = "FizzBuzz問題を解くPythonコードを生成"
    result, trials = agent.run(task)

    print("\n最終結果:")
    print(result)


if __name__ == "__main__":
    # シンプルなデモを実行
    main()

    # LLMを使用する場合は以下をコメントアウト解除:
    # main_with_llm()
