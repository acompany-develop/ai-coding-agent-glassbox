# A1. 一般的なエージェントループの実装パターン

AI Coding Agent で広く使われているエージェントループの設計パターンを解説します。

## 主要なパターン

| パターン | 特徴 | 採用例 |
|---------|------|--------|
| ReAct | Reasoning + Acting の交互実行 | Claude Code, Cursor |
| Plan-and-Execute | 事前計画 → 順次実行 | Devin, AutoGPT |
| Self-Reflection | 実行後の自己評価・修正 | Reflexion |
| Multi-Agent | 複数エージェントの協調 | MetaGPT, ChatDev |

---

## 1. ReAct パターン

**Reasoning and Acting** の略。思考と行動を交互に繰り返すパターン。

### 基本フロー

```
User: "バグを修正して"
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ Thought: まずエラーログを確認する必要がある              │
│ Action: read_file("error.log")                         │
│ Observation: "TypeError: undefined is not a function"  │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ Thought: main.js でエラーが起きている。コードを確認     │
│ Action: read_file("main.js")                           │
│ Observation: "function greet() { ... }"                │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ Thought: 関数名のタイポを発見。修正する                 │
│ Action: edit_file("main.js", old="gree()", new="greet()") │
│ Observation: "Successfully edited"                     │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ Thought: 修正完了。テストを実行して確認                 │
│ Action: execute_command("npm test")                    │
│ Observation: "All tests passed"                        │
└─────────────────────────────────────────────────────────┘
     │
     ▼
Final Answer: "バグを修正しました。タイポを直して..."
```

### 特徴

- **逐次的**: 一度に1つのアクションを実行
- **適応的**: Observation を見て次の行動を決定
- **透明性**: 思考過程が見える

### 実装

```python
def react_loop(user_input: str) -> str:
    messages = [{"role": "user", "content": user_input}]

    while True:
        # LLM に Thought + Action を生成させる
        response = llm.chat(messages, tools=available_tools)

        if response.stop_reason == "end_turn":
            return response.text

        # Action を実行
        for action in response.tool_calls:
            observation = execute_tool(action)
            messages.append(format_observation(observation))
```

### 採用例

- **Claude Code**: Anthropic の公式 CLI ツール
- **Cursor**: AI コードエディタ
- **Aider**: Git 対応 AI コーディングツール

---

## 2. Plan-and-Execute パターン

最初に計画を立て、その後順次実行するパターン。

### 基本フロー

```
User: "認証機能を追加して"
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ Planning Phase                                          │
│                                                         │
│ 計画:                                                   │
│ 1. 現在のコードベース構造を確認                          │
│ 2. 認証ライブラリを選定（JWT vs Session）                │
│ 3. ユーザーモデルを作成                                 │
│ 4. 認証ミドルウェアを実装                               │
│ 5. ログイン/ログアウトエンドポイントを追加               │
│ 6. テストを作成                                        │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ Execution Phase                                         │
│                                                         │
│ Step 1: list_files("src/")                             │
│ Step 2: ask_user("JWTとSessionどちらを使いますか？")     │
│ Step 3: write_file("src/models/user.js", ...)          │
│ ...                                                    │
└─────────────────────────────────────────────────────────┘
```

### 特徴

- **構造化**: 事前に全体像を把握
- **予測可能**: ユーザーが計画を確認・修正可能
- **複雑なタスク向け**: 長期的なタスクに適している

### 実装

```python
def plan_and_execute(user_input: str) -> str:
    # Phase 1: Planning
    plan = llm.chat([
        {"role": "system", "content": "Create a step-by-step plan."},
        {"role": "user", "content": user_input},
    ])

    steps = parse_plan(plan.text)

    # Phase 2: Execution
    for step in steps:
        result = execute_step(step)

        # 必要に応じて計画を修正（Re-planning）
        if needs_replan(result):
            steps = replan(steps, result)
```

### 採用例

- **Devin**: Cognition の AI ソフトウェアエンジニア
- **AutoGPT**: 自律型 AI エージェント
- **BabyAGI**: タスク駆動型自律エージェント

---

## 3. Self-Reflection パターン

実行結果を評価し、必要に応じて修正を行うパターン。

### 基本フロー

```
User: "テストが通るコードを書いて"
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ Initial Attempt                                         │
│                                                         │
│ Action: write_file("solution.py", ...)                 │
│ Action: execute_command("pytest")                       │
│ Result: "2 tests failed"                               │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ Reflection                                              │
│                                                         │
│ "テストが失敗した。エラーメッセージを分析すると、       │
│  境界値のケースを考慮していなかった。                   │
│  次は境界値チェックを追加する。"                        │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ Retry with Reflection                                   │
│                                                         │
│ Action: edit_file("solution.py", ...)  # 修正          │
│ Action: execute_command("pytest")                       │
│ Result: "All tests passed"                             │
└─────────────────────────────────────────────────────────┘
```

### 特徴

- **自己改善**: 失敗から学習
- **品質向上**: 反復により精度向上
- **コスト増**: LLM 呼び出し回数が増加

### 実装

```python
def reflexion_loop(user_input: str, max_retries: int = 3) -> str:
    reflections = []

    for attempt in range(max_retries):
        # 過去の反省を含めて実行
        result = execute_with_reflections(user_input, reflections)

        if is_success(result):
            return result

        # 失敗時: 反省を生成
        reflection = llm.chat([
            {"role": "system", "content": "Analyze the failure and suggest improvements."},
            {"role": "user", "content": f"Result: {result}"},
        ])
        reflections.append(reflection.text)

    return "Max retries reached"
```

### 採用例

- **Reflexion**: 自己反省による学習フレームワーク
- **Self-Refine**: 反復的な自己改善

---

## 4. Multi-Agent パターン

複数の専門エージェントが協調して作業するパターン。

### 基本フロー

```
User: "Webアプリを作って"
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ Orchestrator (指揮者)                                   │
│                                                         │
│ タスクを分解して各エージェントに割り当て                 │
└─────────────────────────────────────────────────────────┘
     │
     ├──────────────┬──────────────┬──────────────┐
     ▼              ▼              ▼              ▼
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
│ Planner │   │ Coder   │   │ Tester  │   │ Reviewer│
│         │   │         │   │         │   │         │
│ 設計担当 │   │ 実装担当 │   │ テスト  │   │ レビュー │
└─────────┘   └─────────┘   └─────────┘   └─────────┘
     │              │              │              │
     └──────────────┴──────────────┴──────────────┘
                           │
                           ▼
                    最終成果物
```

### 特徴

- **専門化**: 各エージェントが特定タスクに特化
- **並列化**: 独立したタスクを同時実行可能
- **スケーラブル**: エージェント追加で機能拡張

### 実装

```python
class MultiAgentSystem:
    def __init__(self):
        self.planner = PlannerAgent()
        self.coder = CoderAgent()
        self.tester = TesterAgent()
        self.reviewer = ReviewerAgent()

    def execute(self, user_input: str) -> str:
        # 1. 計画フェーズ
        plan = self.planner.create_plan(user_input)

        # 2. 実装フェーズ
        code = self.coder.implement(plan)

        # 3. テストフェーズ
        test_results = self.tester.test(code)

        # 4. レビューフェーズ
        review = self.reviewer.review(code, test_results)

        # 5. 必要に応じて修正ループ
        while not review.approved:
            code = self.coder.fix(code, review.feedback)
            test_results = self.tester.test(code)
            review = self.reviewer.review(code, test_results)

        return code
```

### 採用例

- **MetaGPT**: ソフトウェア会社をシミュレート
- **ChatDev**: 仮想ソフトウェア開発チーム
- **AutoGen**: Microsoft のマルチエージェントフレームワーク

---

## パターンの比較

| パターン | 複雑さ | 適したタスク | トークン効率 |
|---------|--------|-------------|-------------|
| ReAct | 低 | 単発〜中程度のタスク | 高 |
| Plan-and-Execute | 中 | 複雑な長期タスク | 中 |
| Self-Reflection | 中 | 精度が重要なタスク | 低 |
| Multi-Agent | 高 | 大規模プロジェクト | 低 |

## 本実装（minimal/）の位置づけ

本実装は **ReAct パターン** を採用しています。

```python
# agent.py - ReAct ループ
for iteration in range(max_iterations):
    # Thought (暗黙的に LLM 内部で実行)
    response = llm_client.chat(messages, tools)

    # Action
    for tool_call in response.tool_calls:
        result = tool_registry.execute(tool_call)

        # Observation
        message_history.add_tool_result(result)
```

理由：
- **シンプル**: 実装が理解しやすい
- **汎用的**: 多くのタスクに対応
- **実績**: Claude Code, Cursor など主要ツールで採用

---

## 参考文献

- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)
- [Plan-and-Solve Prompting](https://arxiv.org/abs/2305.04091)
- [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366)
- [MetaGPT: Meta Programming for Multi-Agent Collaborative Framework](https://arxiv.org/abs/2308.00352)
