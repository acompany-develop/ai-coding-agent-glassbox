from abc import ABC, abstractmethod


class Tool(ABC):
    """ツールの基底クラス

    すべてのツールはこのクラスを継承し、
    LLMが利用できる形式でツール定義を提供する。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """ツール名"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """ツールの説明（LLMに渡す）"""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """入力スキーマ（JSON Schema形式）"""
        pass

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """ツールを実行

        Args:
            **kwargs: ツール固有の引数

        Returns:
            実行結果の文字列
        """
        pass

    def to_anthropic_tool(self) -> dict:
        """Anthropic API用のツール定義に変換

        Returns:
            Anthropic Messages APIのtools形式
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
