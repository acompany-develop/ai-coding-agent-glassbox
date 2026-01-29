# サンドボックスパターン

LLM が生成したコードを安全に実行するための隔離環境です。

## 概要

LLM は任意のコードを生成できるため、そのまま実行すると：
- ファイルシステムへの不正アクセス
- ネットワーク経由の情報漏洩
- システムリソースの枯渇
- 悪意のあるコードの実行

といったリスクがあります。サンドボックスにより、これらを防止します。

## 隔離レベル

```
┌─────────────────────────────────────────────────────────────────┐
│                    Isolation Levels                              │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Level 1: Process Isolation                              │    │
│  │  • subprocess + 制限された権限                          │    │
│  │  • 基本的な分離（同一ホスト上）                         │    │
│  │  • 低コスト、高速                                       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Level 2: Container Isolation (Docker/LXC)               │    │
│  │  • ファイルシステム、ネットワークの分離                 │    │
│  │  • リソース制限（CPU、メモリ）                          │    │
│  │  • 中程度のコスト                                       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Level 3: MicroVM Isolation (Firecracker)               │    │
│  │  • ハードウェアレベルの仮想化                           │    │
│  │  • 最高のセキュリティ                                   │    │
│  │  • 起動時間: ~125ms                                     │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## セキュリティ対策一覧

| 脅威 | 対策 |
|------|------|
| ファイルシステムアクセス | Chroot、読み取り専用マウント |
| ネットワークアクセス | Network namespace、ファイアウォール |
| リソース枯渇 | cgroups（CPU、メモリ制限） |
| 特権昇格 | Seccomp、capabilities 制限 |
| プロンプトインジェクション | 入力検証、出力サニタイズ |

## 使用方法

```python
from sandbox import SimpleSandbox, SecurityPolicy

# ポリシーをカスタマイズ
policy = SecurityPolicy(
    blocked_modules={"os", "subprocess", "socket"},
    blocked_builtins={"open", "exec", "eval"},
    max_execution_time=5.0,
    max_memory=50 * 1024 * 1024,  # 50MB
)

sandbox = SimpleSandbox(policy)

# コードを安全に実行
result = sandbox.execute("""
import math
result = math.factorial(10)
print(f"10! = {result}")
""")

print(f"Success: {result.success}")
print(f"Output: {result.output}")
```

## 主要コンポーネント

### SecurityPolicy

許可/禁止するモジュール、ビルトイン、リソース制限を定義します。

```python
@dataclass
class SecurityPolicy:
    blocked_modules: set[str]  # os, subprocess, socket, ...
    blocked_builtins: set[str]  # open, exec, eval, ...
    max_execution_time: float   # 秒
    max_memory: int             # バイト
    max_output_length: int      # 文字数
```

### CodeAnalyzer

AST（抽象構文木）を使用して、コードを実行前に静的解析します。

```python
class CodeAnalyzer:
    def analyze(self, code: str) -> list[str]:
        """セキュリティ違反を検出"""
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # 禁止モジュールのチェック
            if isinstance(node, ast.Call):
                # 禁止関数のチェック
```

### SimpleSandbox

教育用のシンプルなサンドボックス実装です。

```python
class SimpleSandbox:
    def execute(self, code: str, inputs: dict = None) -> ExecutionResult:
        # 1. 静的解析
        violations = self.analyzer.analyze(code)
        if violations:
            return ExecutionResult(success=False, error=...)

        # 2. 安全なグローバル環境を作成
        safe_globals = self._create_safe_globals()

        # 3. タイムアウト付きで実行
        with timeout_context(self.policy.max_execution_time):
            exec(code, safe_globals)
```

## 本番環境向け推奨事項

**警告**: `SimpleSandbox` は教育目的です。本番環境では使用しないでください。

### 推奨サービス

| サービス | 特徴 |
|---------|------|
| [E2B](https://e2b.dev) | MicroVM ベース、高速起動、クラウドホスト |
| [Microsandbox](https://github.com/nickvidal/microsandbox) | セルフホスト、libkrun ベース |
| [Modal](https://modal.com) | サーバーレス、GPU 対応 |

### Docker 使用時の注意

コンテナ単体では不十分です。追加で：
- `--read-only` でファイルシステムを読み取り専用に
- `--network none` でネットワークを無効化
- `--memory` と `--cpus` でリソース制限
- Seccomp プロファイルで syscall を制限

```bash
docker run \
  --read-only \
  --network none \
  --memory 100m \
  --cpus 1 \
  --security-opt seccomp=profile.json \
  python:3.11-slim \
  python -c "print('Hello')"
```

## マルチエージェント環境での注意

研究によると、17の LLM のうち 82.4% が、「ピアエージェント」からの要求に応じて
悪意のあるツール呼び出しやコードを実行します。

つまり、1つのエージェントが侵害されると、システム全体が危険にさらされます。
各エージェントを個別にサンドボックス化することを検討してください。

## 参考文献

- [Code Sandboxes for LLMs and AI Agents](https://amirmalik.net/2025/03/07/code-sandboxes-for-llm-ai-agents)
- [ISOLATEGPT: Execution Isolation Architecture](https://cybersecurity.seas.wustl.edu/paper/wu2025isolate.pdf)
- [Secure Python Sandbox for LLM Agents](https://dida.do/blog/setting-up-a-secure-python-sandbox-for-llm-agents)
- [The Complete Guide to Sandboxing Autonomous Agents](https://www.ikangai.com/the-complete-guide-to-sandboxing-autonomous-agents-tools-frameworks-and-safety-essentials/)
- [Awesome Sandbox (curated list)](https://github.com/restyler/awesome-sandbox)

## ファイル

- [sandbox.py](./sandbox.py) - 実装コード
