"""
DAG（有向非巡回グラフ）ベースの並列実行 Executor

基本の Plan-and-Execute は直列実行ですが、このファイルでは
依存関係グラフに基づいて並列実行を行う発展的な実装を示します。

例:
    直列実行: Step1 → Step2 → Step3 → Step4
    並列実行: Step1 → [Step2a, Step2b, Step3] → Step4
                       (同時実行可能)

使用方法:
    python dag_executor.py
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class StepStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DAGStep:
    """DAG内のステップ"""

    id: str
    name: str
    action: Callable[..., str]  # 実行する関数
    params: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)  # 依存するステップID
    status: StepStatus = StepStatus.PENDING
    result: str = ""
    error: str | None = None


@dataclass
class DAGExecutionResult:
    """DAG実行結果"""

    steps: list[DAGStep]
    total_time: float
    parallel_speedup: float  # 直列実行と比較した速度向上

    @property
    def success_count(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.FAILED)


class DAGExecutor:
    """
    依存関係グラフに基づく並列実行 Executor

    特徴:
    - 依存関係が解決されたステップを自動的に並列実行
    - 失敗したステップに依存するステップは自動的にスキップ
    - 実行状況のリアルタイム表示
    """

    def __init__(self, max_concurrency: int = 5):
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)

    def build_dependency_graph(
        self, steps: list[DAGStep]
    ) -> dict[str, set[str]]:
        """依存関係グラフを構築"""
        graph = {}
        for step in steps:
            graph[step.id] = set(step.depends_on)
        return graph

    def get_ready_steps(
        self, steps: list[DAGStep], completed: set[str], failed: set[str]
    ) -> list[DAGStep]:
        """
        実行可能なステップを取得
        - 依存関係がすべて完了している
        - まだ実行されていない
        - 依存先が失敗していない
        """
        ready = []
        for step in steps:
            if step.status != StepStatus.PENDING:
                continue

            # 依存先が失敗していればスキップ
            if any(dep in failed for dep in step.depends_on):
                step.status = StepStatus.SKIPPED
                step.error = "Dependency failed"
                continue

            # すべての依存先が完了していれば実行可能
            if all(dep in completed for dep in step.depends_on):
                step.status = StepStatus.READY
                ready.append(step)

        return ready

    async def execute_step(self, step: DAGStep) -> DAGStep:
        """1つのステップを非同期で実行"""
        async with self.semaphore:
            step.status = StepStatus.RUNNING
            print(f"  [RUNNING] {step.id}: {step.name}")

            try:
                # 同期関数を非同期で実行
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, lambda: step.action(**step.params)
                )

                step.result = result
                step.status = StepStatus.COMPLETED
                print(f"  [DONE]    {step.id}: {step.name}")

            except Exception as e:
                step.error = str(e)
                step.status = StepStatus.FAILED
                print(f"  [FAILED]  {step.id}: {step.name} - {e}")

            return step

    async def execute(self, steps: list[DAGStep]) -> DAGExecutionResult:
        """DAGを並列実行"""
        import time

        start_time = time.time()
        completed: set[str] = set()
        failed: set[str] = set()

        print("\n" + "=" * 50)
        print("DAG Parallel Execution")
        print("=" * 50)

        # 依存関係のないステップは即座に実行可能
        for step in steps:
            if not step.depends_on:
                step.status = StepStatus.READY

        iteration = 0
        while True:
            iteration += 1
            print(f"\n--- Iteration {iteration} ---")

            # 実行可能なステップを取得
            ready_steps = self.get_ready_steps(steps, completed, failed)

            if not ready_steps:
                # 実行中のステップもなければ終了
                running = [s for s in steps if s.status == StepStatus.RUNNING]
                if not running:
                    break
                # 実行中があれば待機
                await asyncio.sleep(0.1)
                continue

            print(f"Ready steps: {[s.id for s in ready_steps]}")

            # 並列実行
            tasks = [self.execute_step(step) for step in ready_steps]
            results = await asyncio.gather(*tasks)

            # 結果を記録
            for step in results:
                if step.status == StepStatus.COMPLETED:
                    completed.add(step.id)
                elif step.status == StepStatus.FAILED:
                    failed.add(step.id)

        total_time = time.time() - start_time

        # 直列実行との比較（概算）
        serial_time = sum(
            1.0 for s in steps if s.status == StepStatus.COMPLETED
        )  # 各ステップ1秒と仮定
        speedup = serial_time / total_time if total_time > 0 else 1.0

        return DAGExecutionResult(
            steps=steps, total_time=total_time, parallel_speedup=speedup
        )


# =============================================================================
# デモ用のサンプルタスク
# =============================================================================


def simulate_task(name: str, duration: float = 0.5) -> str:
    """タスクをシミュレート"""
    import time

    time.sleep(duration)
    return f"Completed: {name}"


def create_sample_dag() -> list[DAGStep]:
    """
    サンプルDAGを作成

    依存関係グラフ:
        fetch_data ──┬──▶ process_a ──┬──▶ merge_results ──▶ generate_report
                     ├──▶ process_b ──┤
                     └──▶ process_c ──┘

    直列実行: 6ステップ × 0.5秒 = 3秒
    並列実行: 4レベル × 0.5秒 = 2秒（process_a/b/c が並列）
    """
    return [
        DAGStep(
            id="fetch_data",
            name="データ取得",
            action=lambda: simulate_task("fetch_data"),
            depends_on=[],
        ),
        DAGStep(
            id="process_a",
            name="処理A（分析）",
            action=lambda: simulate_task("process_a"),
            depends_on=["fetch_data"],
        ),
        DAGStep(
            id="process_b",
            name="処理B（変換）",
            action=lambda: simulate_task("process_b"),
            depends_on=["fetch_data"],
        ),
        DAGStep(
            id="process_c",
            name="処理C（検証）",
            action=lambda: simulate_task("process_c"),
            depends_on=["fetch_data"],
        ),
        DAGStep(
            id="merge_results",
            name="結果統合",
            action=lambda: simulate_task("merge_results"),
            depends_on=["process_a", "process_b", "process_c"],
        ),
        DAGStep(
            id="generate_report",
            name="レポート生成",
            action=lambda: simulate_task("generate_report"),
            depends_on=["merge_results"],
        ),
    ]


def visualize_dag(steps: list[DAGStep]) -> None:
    """DAGを可視化（テキスト）"""
    print("\nDAG Structure:")
    print("-" * 40)

    # レベルごとにグループ化
    levels: dict[int, list[DAGStep]] = {}
    step_levels: dict[str, int] = {}

    for step in steps:
        if not step.depends_on:
            level = 0
        else:
            level = max(step_levels.get(dep, 0) for dep in step.depends_on) + 1
        step_levels[step.id] = level

        if level not in levels:
            levels[level] = []
        levels[level].append(step)

    for level in sorted(levels.keys()):
        step_names = [f"{s.id}" for s in levels[level]]
        if level == 0:
            print(f"Level {level}: {', '.join(step_names)}")
        else:
            print(f"    ↓")
            print(f"Level {level}: {', '.join(step_names)}")


async def main():
    """デモ実行"""
    print("\n" + "#" * 60)
    print("# DAG-based Parallel Executor Demo")
    print("#" * 60)

    # サンプルDAGを作成
    steps = create_sample_dag()
    visualize_dag(steps)

    # 並列実行
    executor = DAGExecutor(max_concurrency=3)
    result = await executor.execute(steps)

    # 結果表示
    print("\n" + "=" * 50)
    print("Execution Results")
    print("=" * 50)
    print(f"Total time: {result.total_time:.2f}s")
    print(f"Success: {result.success_count}, Failed: {result.failed_count}")
    print(f"Parallel speedup: {result.parallel_speedup:.2f}x")

    print("\nStep Details:")
    for step in result.steps:
        status_icon = {
            StepStatus.COMPLETED: "✓",
            StepStatus.FAILED: "✗",
            StepStatus.SKIPPED: "⊘",
        }.get(step.status, "?")
        print(f"  {status_icon} {step.id}: {step.status.value}")


if __name__ == "__main__":
    asyncio.run(main())
