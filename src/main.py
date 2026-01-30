"""AI Coding Agent - Glass Box Implementation (Minimal Edition)

ガラスボックス設計のAIコーディングエージェント。
各コンポーネントの動作が見える教育目的の実装。

使用方法:
    python -m src.main                    # デフォルト（Gemini）
    python -m src.main --provider gemini  # Google Gemini
    python -m src.main --provider llama   # Llama 3.1 (Ollama)
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from .agent import Agent
from .colors import (
    cyan, green, bold,
    print_init, print_error, print_header,
)

# .env ファイルを読み込み（存在する場合）
load_dotenv(Path(__file__).parent.parent / ".env")
from .llm_clients import create_llm_client
from .tool_registry import ToolRegistry
from .tools import (
    ExecuteCommandTool,
    ListFilesTool,
    ReadFileTool,
    WriteFileTool,
)


SUPPORTED_PROVIDERS = ["gemini", "llama"]
DEFAULT_PROVIDER = "gemini"


def create_agent(provider: str, model: str | None = None) -> Agent:
    """エージェントを初期化して返す

    Args:
        provider: LLMプロバイダー名
        model: モデル名（省略時はプロバイダーのデフォルト）

    Returns:
        設定済みのAgentインスタンス
    """
    print_header("AI Coding Agent - Glass Box (Minimal Edition)")

    # LLMクライアントの初期化
    print_init(f"Initializing LLM client ({cyan(provider)})...")
    llm_client = create_llm_client(provider=provider, model=model)
    print_init(f"Provider: {cyan(llm_client.provider_name)}")

    # ツールレジストリの初期化
    print_init("Initializing tool registry...")
    tool_registry = ToolRegistry()

    # ツールの登録
    tools = [
        ReadFileTool(),
        WriteFileTool(),
        ListFilesTool(),
        ExecuteCommandTool(),
    ]
    tool_registry.register_all(tools)

    # エージェントの初期化
    print_init("Initializing agent...")
    agent = Agent(
        llm_client=llm_client,
        tool_registry=tool_registry,
    )

    print_init(green("Agent ready!"))
    print_init(f"Available tools: {tool_registry.list_tools()}")

    return agent


def run_interactive(agent: Agent) -> None:
    """対話モードでエージェントを実行

    Args:
        agent: 実行するエージェント
    """
    print()
    print_header("Interactive Mode - Type 'quit' or 'exit' to stop")

    while True:
        try:
            user_input = input("\n> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                print(green("\nGoodbye!"))
                break

            if user_input.lower() == "reset":
                agent.reset()
                print("Agent state has been reset.")
                continue

            # エージェントループを実行
            response = agent.run(user_input)

            print()
            print_header(green("FINAL RESPONSE"))
            print(response)

        except KeyboardInterrupt:
            print(green("\n\nInterrupted. Goodbye!"))
            break
        except Exception as e:
            print_error(str(e))
            import traceback
            traceback.print_exc()
            print_error("Agent state has been reset due to error.")
            agent.reset()


def parse_args() -> argparse.Namespace:
    """コマンドライン引数をパース"""
    parser = argparse.ArgumentParser(
        description="AI Coding Agent - Glass Box Implementation (Minimal Edition)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main                       # Use Gemini (default)
  python -m src.main --provider gemini     # Use Google Gemini
  python -m src.main --provider llama      # Use Llama 3.1 (Ollama)
  python -m src.main --provider gemini --model gemini-2.0-flash  # Specify model

Environment Variables:
  GEMINI_API_KEY     - Required for Gemini provider
  OLLAMA_BASE_URL    - Ollama API URL (default: http://localhost:11434)
        """,
    )

    parser.add_argument(
        "--provider", "-p",
        choices=SUPPORTED_PROVIDERS,
        default=DEFAULT_PROVIDER,
        help=f"LLM provider to use (default: {DEFAULT_PROVIDER})",
    )

    parser.add_argument(
        "--model", "-m",
        type=str,
        default=None,
        help="Model name (uses provider default if not specified)",
    )

    return parser.parse_args()


def main() -> None:
    """エントリーポイント"""
    args = parse_args()

    try:
        agent = create_agent(provider=args.provider, model=args.model)
        run_interactive(agent)
    except ValueError as e:
        print_error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
