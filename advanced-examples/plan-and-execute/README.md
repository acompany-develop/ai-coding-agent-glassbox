# Plan-and-Execute エージェントパターン

Plan-and-Execute（計画→実行）は、ReAct パターンとは異なるエージェントアーキテクチャです。
タスクを最初に計画し、その後順番に実行する2フェーズ方式を採用しています。

## 概要

### ReAct vs Plan-and-Execute

| 観点 | ReAct | Plan-and-Execute |
|------|-------|------------------|
| アプローチ | 逐次的（Think→Act→Observe の繰り返し） | 2フェーズ（Plan → Execute） |
| 計画の粒度 | 1ステップずつ判断 | 事前に全体計画を作成 |
| LLM 呼び出し | 各ツール実行ごとに呼び出し | 計画時 + 再計画時のみ |
| 応答速度 | 速い（2,000-3,000 tokens） | 遅い（3,000-4,500 tokens） |
| タスク完了精度 | 85% | 92% |
| コスト/タスク | $0.06-0.09 | $0.09-0.14 |

### いつ使うべきか

**Plan-and-Execute が適するケース:**
- 複数ステップを要する複雑なタスク
- 高い精度が求められる場面（財務分析、データ処理）
- 長期的な計画が必要なシナリオ（プロジェクト計画、戦略決定）
- ステップ間の依存関係があるタスク

**ReAct が適するケース:**
- 単純で直接的なタスク
- リアルタイムの対話が必要な場面（カスタマーサービス）
- コスト重視のアプリケーション
- 素早い応答が求められる場面

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                     Plan-and-Execute Agent                       │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Phase 1: PLAN                          │   │
│  │                                                           │   │
│  │   User Goal ──▶ Planner LLM ──▶ Structured Plan          │   │
│  │                                                           │   │
│  │   "ファイルをリファクタ"  ──▶  [                          │   │
│  │                                  Step 1: ファイル読み込み │   │
│  │                                  Step 2: 構造解析         │   │
│  │                                  Step 3: 変更適用         │   │
│  │                                  Step 4: テスト実行       │   │
│  │                                ]                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Phase 2: EXECUTE                        │   │
│  │                                                           │   │
│  │   for step in plan:                                      │   │
│  │       result = executor.execute(step)                    │   │
│  │       if needs_replan(result):                           │   │
│  │           plan = replanner.replan(plan, result)          │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Phase 3: REPLAN (optional)              │   │
│  │                                                           │   │
│  │   - 実行結果を評価                                        │   │
│  │   - 計画の修正が必要か判断                                │   │
│  │   - 必要に応じて残りのステップを更新                      │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## コンポーネント詳細

### 1. Planner（計画者）

ユーザーのゴールを受け取り、構造化された計画を生成します。

```python
class Planner:
    """
    ユーザーのゴールを分解して実行可能なステップのリストを生成
    """

    def plan(self, goal: str, context: dict) -> list[PlanStep]:
        prompt = f"""
        Goal: {goal}
        Available Tools: {context['tools']}

        Create a step-by-step plan to achieve this goal.
        Each step should be:
        - Specific and actionable
        - Independent or clearly dependent on previous steps
        - Executable with the available tools

        Output format:
        {{
            "steps": [
                {{"id": 1, "action": "...", "tool": "...", "depends_on": []}},
                {{"id": 2, "action": "...", "tool": "...", "depends_on": [1]}}
            ]
        }}
        """
        response = self.llm.generate(prompt)
        return self.parse_plan(response)
```

**重要なポイント:**
- ステップ間の依存関係を明示
- 各ステップに使用するツールを指定
- 失敗時の代替案も考慮（高度な実装）

### 2. Executor（実行者）

計画の各ステップを実際に実行します。Executor の知性レベルには3段階あります。

#### Level 1: Simple Executor（シンプル）

```python
class SimpleExecutor:
    """単純なforループで計画を実行"""

    def execute(self, plan: list[PlanStep]) -> list[StepResult]:
        results = []
        for step in plan:
            # 事前定義された関数を直接呼び出し
            tool = self.tools[step.tool]
            result = tool.execute(**step.params)
            results.append(StepResult(step=step, result=result))
        return results
```

#### Level 2: Intelligent Executor（インテリジェント）

```python
class IntelligentExecutor:
    """小型LLMを使用してステップをツール呼び出しに変換"""

    def execute(self, step: PlanStep, context: dict) -> StepResult:
        # 自然言語のステップを具体的なツール呼び出しにマッピング
        prompt = f"""
        Step to execute: {step.action}
        Available tools: {self.tool_definitions}
        Previous results: {context['previous_results']}

        Map this step to a specific tool call with parameters.
        """
        tool_call = self.small_llm.generate(prompt)
        return self.execute_tool(tool_call)
```

#### Level 3: Agentic Executor（エージェンティック）

```python
class AgenticExecutor:
    """各ステップを内部でReActエージェントとして実行"""

    def execute(self, step: PlanStep, context: dict) -> StepResult:
        # 各ステップ自体が小さなReActループ
        sub_agent = ReActAgent(
            goal=step.action,
            tools=self.tools,
            max_iterations=5
        )
        return sub_agent.run()
```

### 3. Replanner（再計画者）

実行結果を評価し、必要に応じて計画を修正します。

```python
class Replanner:
    """実行結果に基づいて計画を修正"""

    def should_replan(self, step_result: StepResult, remaining_plan: list) -> bool:
        """再計画が必要かどうかを判断"""
        # 失敗した場合
        if step_result.status == "failed":
            return True
        # 予期しない結果の場合
        if step_result.unexpected:
            return True
        return False

    def replan(
        self,
        original_goal: str,
        completed_steps: list[StepResult],
        remaining_steps: list[PlanStep],
        current_result: StepResult
    ) -> list[PlanStep]:
        prompt = f"""
        Original Goal: {original_goal}

        Completed Steps:
        {self.format_completed(completed_steps)}

        Current Step Result:
        {current_result}

        Remaining Plan:
        {remaining_steps}

        Based on the current result, should we:
        1. Continue with the remaining plan as-is
        2. Modify the remaining steps
        3. Add new steps
        4. Finish early (goal already achieved)

        Provide the updated plan.
        """
        response = self.llm.generate(prompt)
        return self.parse_replan(response)
```

## 状態管理

Plan-and-Execute では、以下の状態を管理する必要があります：

```python
@dataclass
class PlanExecuteState:
    """Plan-and-Execute エージェントの状態"""

    # 入力
    goal: str

    # 計画
    plan: list[PlanStep]
    current_step_index: int = 0

    # 実行結果
    step_results: list[StepResult] = field(default_factory=list)

    # 状態
    status: str = "planning"  # planning, executing, replanning, completed, failed

    @property
    def current_step(self) -> PlanStep | None:
        if self.current_step_index < len(self.plan):
            return self.plan[self.current_step_index]
        return None

    @property
    def remaining_steps(self) -> list[PlanStep]:
        return self.plan[self.current_step_index:]
```

## 高度なパターン

### DAG ベースの並列実行

基本的な Plan-and-Execute は直列実行ですが、依存関係グラフ（DAG）を使用して並列実行が可能です。

```
基本（直列）:
  Step 1 → Step 2 → Step 3 → Step 4

DAG（並列）:
  Step 1 ──┬──▶ Step 2a ──┬──▶ Step 4
           └──▶ Step 2b ──┘
           └──▶ Step 3 ────────┘
```

```python
class DAGExecutor:
    """依存関係グラフに基づく並列実行"""

    async def execute(self, plan: list[PlanStep]) -> list[StepResult]:
        # 依存関係グラフを構築
        graph = self.build_dependency_graph(plan)
        results = {}

        while not self.is_complete(graph, results):
            # 実行可能なステップを取得（依存関係が解決済み）
            ready_steps = self.get_ready_steps(graph, results)

            # 並列実行
            step_results = await asyncio.gather(*[
                self.execute_step(step) for step in ready_steps
            ])

            # 結果を記録
            for step, result in zip(ready_steps, step_results):
                results[step.id] = result

        return list(results.values())
```

### Human-in-the-Loop（HITL）

重要な決定点でユーザーの承認を求めます。

```python
class HITLPlanner:
    """人間の承認を含むPlanner"""

    def plan_with_approval(self, goal: str) -> list[PlanStep]:
        # 計画を生成
        plan = self.planner.plan(goal)

        # 危険なステップをマーク
        risky_steps = self.identify_risky_steps(plan)

        if risky_steps:
            print("以下のステップには承認が必要です:")
            for step in risky_steps:
                print(f"  - {step.action}")

            if not self.get_user_approval():
                return self.plan_with_approval(goal)  # 再計画

        return plan
```

## ReAct との組み合わせ（ハイブリッドアプローチ）

実務では、タスクの複雑さに応じて両パターンを組み合わせることが推奨されます。

```python
class HybridAgent:
    """ReAct と Plan-and-Execute のハイブリッド"""

    def run(self, task: str) -> str:
        complexity = self.assess_complexity(task)

        if complexity == "simple":
            # 単純なタスクは ReAct で即座に対応
            return self.react_agent.run(task)
        else:
            # 複雑なタスクは Plan-and-Execute
            return self.plan_execute_agent.run(task)

    def assess_complexity(self, task: str) -> str:
        """タスクの複雑さを評価"""
        indicators = {
            "multiple": task contains multiple objectives,
            "steps": requires more than 3 steps,
            "dependencies": steps have dependencies,
        }
        if sum(indicators.values()) >= 2:
            return "complex"
        return "simple"
```

## セキュリティ考慮事項

Plan-and-Execute は、間接的なプロンプトインジェクション攻撃に対して本質的に耐性があります。

**理由:**
1. **計画と実行の分離**: 計画フェーズで全体を検証できる
2. **制御フローの整合性**: 計画されたステップのみが実行される
3. **事前検証**: 危険な操作を実行前に検出可能

```python
class SecurePlanExecutor:
    """セキュリティ検証を含むExecutor"""

    def validate_plan(self, plan: list[PlanStep]) -> bool:
        for step in plan:
            # 危険なパターンをチェック
            if self.is_dangerous(step):
                raise SecurityError(f"Dangerous step detected: {step}")

            # 許可されたツールのみ使用可能
            if step.tool not in self.allowed_tools:
                raise SecurityError(f"Unauthorized tool: {step.tool}")

        return True
```

## 参考文献

- [LangGraph Plan-and-Execute Tutorial](https://langchain-ai.github.io/langgraph/tutorials/plan-and-execute/plan-and-execute/)
- [LangChain Blog: Planning Agents](https://www.blog.langchain.com/planning-agents/)
- [ArXiv: Architecting Resilient LLM Agents](https://arxiv.org/abs/2509.08646)
- [ReAct vs Plan-and-Execute Comparison](https://dev.to/jamesli/react-vs-plan-and-execute-a-practical-comparison-of-llm-agent-patterns-4gh9)

## 関連ファイル

- [plan_execute_agent.py](./plan_execute_agent.py) - 基本実装
- [dag_executor.py](./dag_executor.py) - DAG並列実行（発展）
