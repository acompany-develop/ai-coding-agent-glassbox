"""
Plan-and-Execute エージェントの基本実装

このファイルは Plan-and-Execute パターンの教育目的の実装です。
minimal/ や standard/ とは独立した実装例として提供しています。

使用方法:
    python plan_execute_agent.py

必要な環境変数:
    GEMINI_API_KEY: Google Gemini API キー
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types


# =============================================================================
# データ構造
# =============================================================================


@dataclass
class PlanStep:
    """計画の1ステップを表現"""

    id: int
    action: str  # 自然言語での説明
    tool: str  # 使用するツール名
    params: dict = field(default_factory=dict)  # ツールのパラメータ
    depends_on: list[int] = field(default_factory=list)  # 依存するステップID


@dataclass
class StepResult:
    """ステップの実行結果"""

    step: PlanStep
    status: str  # "success", "failed", "skipped"
    result: str
    error: str | None = None


@dataclass
class PlanExecuteState:
    """エージェントの状態"""

    goal: str
    plan: list[PlanStep] = field(default_factory=list)
    current_step_index: int = 0
    step_results: list[StepResult] = field(default_factory=list)
    status: str = "planning"  # planning, executing, replanning, completed, failed

    @property
    def current_step(self) -> PlanStep | None:
        if self.current_step_index < len(self.plan):
            return self.plan[self.current_step_index]
        return None

    @property
    def remaining_steps(self) -> list[PlanStep]:
        return self.plan[self.current_step_index :]

    @property
    def completed_steps(self) -> list[StepResult]:
        return self.step_results


# =============================================================================
# ツール定義
# =============================================================================


class Tool(ABC):
    """ツールの基底クラス"""

    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, **kwargs) -> str:
        pass


class ReadFileTool(Tool):
    name = "read_file"
    description = "ファイルの内容を読み込む"

    def execute(self, path: str) -> str:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except Exception as e:
            return f"Error: {e}"


class WriteFileTool(Tool):
    name = "write_file"
    description = "ファイルに内容を書き込む"

    def execute(self, path: str, content: str) -> str:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote to {path}"
        except Exception as e:
            return f"Error: {e}"


class ListFilesTool(Tool):
    name = "list_files"
    description = "ディレクトリ内のファイル一覧を取得"

    def execute(self, path: str = ".") -> str:
        try:
            from pathlib import Path

            p = Path(path)
            if not p.exists():
                return f"Error: Path does not exist: {path}"
            items = sorted(p.iterdir())
            result = []
            for item in items:
                prefix = "[DIR]" if item.is_dir() else "[FILE]"
                result.append(f"{prefix} {item.name}")
            return "\n".join(result) or "(empty directory)"
        except Exception as e:
            return f"Error: {e}"


class CalculateTool(Tool):
    name = "calculate"
    description = "数式を計算する"

    def execute(self, expression: str) -> str:
        try:
            # 安全のため、限定的な評価
            allowed = set("0123456789+-*/().  ")
            if not all(c in allowed for c in expression):
                return "Error: Invalid characters in expression"
            result = eval(expression)  # 教育目的のみ
            return str(result)
        except Exception as e:
            return f"Error: {e}"


# =============================================================================
# Planner（計画者）
# =============================================================================


class Planner:
    """ユーザーのゴールから計画を生成"""

    def __init__(self, llm_client: Any, tools: list[Tool]):
        self.llm = llm_client
        self.tools = tools
        self.tool_descriptions = self._format_tool_descriptions()

    def _format_tool_descriptions(self) -> str:
        return "\n".join(
            f"- {tool.name}: {tool.description}" for tool in self.tools
        )

    def plan(self, goal: str) -> list[PlanStep]:
        """ゴールから計画を生成"""
        prompt = f"""あなたはタスク計画の専門家です。
以下のゴールを達成するための計画を作成してください。

ゴール: {goal}

利用可能なツール:
{self.tool_descriptions}

以下のJSON形式で計画を出力してください:
{{
    "steps": [
        {{
            "id": 1,
            "action": "何をするかの説明",
            "tool": "使用するツール名",
            "params": {{"param1": "value1"}},
            "depends_on": []
        }},
        {{
            "id": 2,
            "action": "次のステップの説明",
            "tool": "ツール名",
            "params": {{}},
            "depends_on": [1]
        }}
    ]
}}

注意:
- 各ステップは具体的で実行可能にしてください
- depends_on には、このステップが依存する前のステップのIDを指定してください
- ツールはリストにあるものだけを使用してください
- JSONのみを出力し、他の説明は不要です
"""

        response = self.llm.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
            ),
        )

        return self._parse_plan(response.text)

    def _parse_plan(self, response: str) -> list[PlanStep]:
        """LLMのレスポンスから計画をパース"""
        # JSON部分を抽出
        json_match = re.search(r"\{[\s\S]*\}", response)
        if not json_match:
            raise ValueError(f"Could not parse plan from response: {response}")

        try:
            data = json.loads(json_match.group())
            steps = []
            for step_data in data.get("steps", []):
                steps.append(
                    PlanStep(
                        id=step_data["id"],
                        action=step_data["action"],
                        tool=step_data["tool"],
                        params=step_data.get("params", {}),
                        depends_on=step_data.get("depends_on", []),
                    )
                )
            return steps
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON parse error: {e}\nResponse: {response}") from e


# =============================================================================
# Executor（実行者）
# =============================================================================


class Executor:
    """計画の各ステップを実行"""

    def __init__(self, tools: list[Tool]):
        self.tools = {tool.name: tool for tool in tools}

    def execute_step(
        self, step: PlanStep, previous_results: list[StepResult]
    ) -> StepResult:
        """1つのステップを実行"""
        print(f"\n  [EXECUTE] Step {step.id}: {step.action}")
        print(f"            Tool: {step.tool}, Params: {step.params}")

        # ツールが存在するか確認
        if step.tool not in self.tools:
            return StepResult(
                step=step,
                status="failed",
                result="",
                error=f"Unknown tool: {step.tool}",
            )

        # 依存関係のチェック
        for dep_id in step.depends_on:
            dep_result = next(
                (r for r in previous_results if r.step.id == dep_id), None
            )
            if dep_result and dep_result.status == "failed":
                return StepResult(
                    step=step,
                    status="skipped",
                    result="",
                    error=f"Dependency step {dep_id} failed",
                )

        # ツールを実行
        try:
            tool = self.tools[step.tool]
            result = tool.execute(**step.params)
            print(f"            Result: {result[:100]}..." if len(result) > 100 else f"            Result: {result}")

            # エラーチェック
            if result.startswith("Error:"):
                return StepResult(
                    step=step, status="failed", result=result, error=result
                )

            return StepResult(step=step, status="success", result=result)

        except Exception as e:
            return StepResult(
                step=step, status="failed", result="", error=str(e)
            )


# =============================================================================
# Replanner（再計画者）
# =============================================================================


class Replanner:
    """実行結果に基づいて計画を修正"""

    def __init__(self, llm_client: Any, tools: list[Tool]):
        self.llm = llm_client
        self.tools = tools
        self.tool_descriptions = "\n".join(
            f"- {tool.name}: {tool.description}" for tool in tools
        )

    def should_replan(
        self, step_result: StepResult, remaining_steps: list[PlanStep]
    ) -> bool:
        """再計画が必要かどうかを判断"""
        # 失敗した場合は再計画を検討
        if step_result.status == "failed":
            return True
        return False

    def replan(
        self,
        original_goal: str,
        completed_results: list[StepResult],
        current_result: StepResult,
        remaining_steps: list[PlanStep],
    ) -> list[PlanStep]:
        """計画を修正"""
        completed_summary = "\n".join(
            f"  Step {r.step.id}: {r.step.action} -> {r.status}"
            for r in completed_results
        )

        remaining_summary = "\n".join(
            f"  Step {s.id}: {s.action}" for s in remaining_steps
        )

        prompt = f"""あなたはタスク計画の専門家です。
以下の状況で計画を修正してください。

元のゴール: {original_goal}

完了したステップ:
{completed_summary}

現在のステップの結果:
  Step {current_result.step.id}: {current_result.step.action}
  Status: {current_result.status}
  Error: {current_result.error}

残りの計画:
{remaining_summary}

利用可能なツール:
{self.tool_descriptions}

以下の選択肢から最適な対応を選び、JSONで出力してください:
1. "continue" - 残りの計画をそのまま続行
2. "modify" - 計画を修正して続行
3. "abort" - 計画を中止

{{
    "decision": "continue" | "modify" | "abort",
    "reason": "判断の理由",
    "new_steps": [...]  // "modify"の場合のみ、新しいステップのリスト
}}
"""

        response = self.llm.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
            ),
        )

        return self._parse_replan(response.text, remaining_steps)

    def _parse_replan(
        self, response: str, remaining_steps: list[PlanStep]
    ) -> list[PlanStep]:
        """再計画の結果をパース"""
        json_match = re.search(r"\{[\s\S]*\}", response)
        if not json_match:
            # パース失敗時は残りの計画をそのまま返す
            return remaining_steps

        try:
            data = json.loads(json_match.group())
            decision = data.get("decision", "continue")

            print(f"\n  [REPLAN] Decision: {decision}")
            print(f"           Reason: {data.get('reason', 'N/A')}")

            if decision == "abort":
                return []
            elif decision == "modify" and "new_steps" in data:
                return [
                    PlanStep(
                        id=s["id"],
                        action=s["action"],
                        tool=s["tool"],
                        params=s.get("params", {}),
                        depends_on=s.get("depends_on", []),
                    )
                    for s in data["new_steps"]
                ]
            else:
                return remaining_steps

        except json.JSONDecodeError:
            return remaining_steps


# =============================================================================
# Plan-and-Execute Agent
# =============================================================================


class PlanExecuteAgent:
    """Plan-and-Execute エージェント"""

    def __init__(self, llm_client: Any, tools: list[Tool]):
        self.planner = Planner(llm_client, tools)
        self.executor = Executor(tools)
        self.replanner = Replanner(llm_client, tools)
        self.tools = tools

    def run(self, goal: str) -> str:
        """エージェントを実行"""
        state = PlanExecuteState(goal=goal)

        # Phase 1: PLAN
        print("\n" + "=" * 60)
        print("Phase 1: PLANNING")
        print("=" * 60)
        print(f"Goal: {goal}")

        state.plan = self.planner.plan(goal)
        state.status = "executing"

        print(f"\nGenerated Plan ({len(state.plan)} steps):")
        for step in state.plan:
            deps = f" (depends on: {step.depends_on})" if step.depends_on else ""
            print(f"  {step.id}. {step.action}{deps}")

        # Phase 2: EXECUTE
        print("\n" + "=" * 60)
        print("Phase 2: EXECUTING")
        print("=" * 60)

        while state.current_step is not None:
            step = state.current_step

            # ステップを実行
            result = self.executor.execute_step(step, state.step_results)
            state.step_results.append(result)

            # 失敗時は再計画を検討
            if result.status == "failed":
                print(f"\n  [FAILED] Step {step.id} failed: {result.error}")

                if self.replanner.should_replan(result, state.remaining_steps[1:]):
                    state.status = "replanning"
                    new_remaining = self.replanner.replan(
                        state.goal,
                        state.step_results,
                        result,
                        state.remaining_steps[1:],
                    )

                    if not new_remaining:
                        state.status = "failed"
                        break

                    # 計画を更新
                    completed_steps = state.plan[: state.current_step_index + 1]
                    state.plan = completed_steps + new_remaining
                    state.status = "executing"

            # 次のステップへ
            state.current_step_index += 1

        # 完了
        if state.status != "failed":
            state.status = "completed"

        # 結果サマリー
        print("\n" + "=" * 60)
        print("EXECUTION SUMMARY")
        print("=" * 60)
        print(f"Status: {state.status}")
        print(f"Steps executed: {len(state.step_results)}")

        success_count = sum(1 for r in state.step_results if r.status == "success")
        failed_count = sum(1 for r in state.step_results if r.status == "failed")
        skipped_count = sum(1 for r in state.step_results if r.status == "skipped")

        print(f"  - Success: {success_count}")
        print(f"  - Failed: {failed_count}")
        print(f"  - Skipped: {skipped_count}")

        # 最後の成功結果を返す
        successful_results = [r for r in state.step_results if r.status == "success"]
        if successful_results:
            return successful_results[-1].result
        return f"Task completed with status: {state.status}"


# =============================================================================
# メイン
# =============================================================================


def main():
    """デモ実行"""
    # API キーを取得
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is required")
        return

    # LLM クライアントを初期化
    client = genai.Client(api_key=api_key)

    # ツールを準備
    tools = [
        ReadFileTool(),
        WriteFileTool(),
        ListFilesTool(),
        CalculateTool(),
    ]

    # エージェントを作成
    agent = PlanExecuteAgent(client, tools)

    # デモタスクを実行
    print("\n" + "#" * 60)
    print("# Plan-and-Execute Agent Demo")
    print("#" * 60)

    # シンプルなタスク
    goal = "カレントディレクトリのファイル一覧を表示してください"
    result = agent.run(goal)
    print(f"\nFinal Result:\n{result}")


if __name__ == "__main__":
    main()
