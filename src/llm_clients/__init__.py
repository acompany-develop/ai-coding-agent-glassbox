from .base import BaseLLMClient, LLMResponse, ToolCall
from .gemini_client import GeminiClient
from .llama_client import LlamaClient

__all__ = [
    "BaseLLMClient",
    "LLMResponse",
    "ToolCall",
    "GeminiClient",
    "LlamaClient",
]


def create_llm_client(
    provider: str,
    api_key: str | None = None,
    model: str | None = None,
) -> BaseLLMClient:
    """プロバイダー名からLLMクライアントを作成するファクトリ関数

    Args:
        provider: プロバイダー名 ("gemini", "llama")
        api_key: APIキー（省略時は環境変数から取得、llamaは不要）
        model: モデル名（省略時はデフォルト）

    Returns:
        LLMクライアントインスタンス

    Raises:
        ValueError: 不明なプロバイダー名の場合
    """
    provider = provider.lower()

    if provider == "gemini":
        return GeminiClient(api_key=api_key, model=model)
    elif provider == "llama":
        return LlamaClient(api_key=api_key, model=model)
    else:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Supported providers: gemini, llama"
        )
