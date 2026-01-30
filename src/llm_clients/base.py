from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolCall:
    """ツール呼び出しを表す統一データクラス

    各プロバイダーのレスポンス形式を統一するために使用。
    """
    id: str
    name: str
    input: dict


@dataclass
class LLMResponse:
    """LLMレスポンスを表す統一データクラス

    各プロバイダーのレスポンス形式を統一するために使用。
    """
    text: str | None
    tool_calls: list[ToolCall]
    stop_reason: str  # "end_turn" or "tool_use"
    raw_response: object  # プロバイダー固有のレスポンスオブジェクト


class BaseLLMClient(ABC):
    """LLMクライアントの抽象基底クラス

    各プロバイダー（Gemini, Llama等）の実装はこのクラスを継承する。
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """プロバイダー名を返す"""
        pass

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
    ) -> LLMResponse:
        """LLMにリクエストを送信

        Args:
            messages: メッセージ履歴
            tools: 利用可能なツールのリスト（共通形式）
            system: システムプロンプト

        Returns:
            統一されたLLMResponseオブジェクト
        """
        pass

    @abstractmethod
    def format_tool_result(self, tool_call_id: str, result: str) -> dict:
        """ツール実行結果をプロバイダー固有の形式にフォーマット

        Args:
            tool_call_id: ツール呼び出しのID
            result: ツール実行結果

        Returns:
            プロバイダー固有の形式のメッセージ
        """
        pass
