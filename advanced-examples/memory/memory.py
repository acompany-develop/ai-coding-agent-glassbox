"""
階層的メモリ管理

エージェントが長期的なタスクを遂行し、過去の経験から学習するための
3層メモリアーキテクチャを実装します。

アーキテクチャ:
- Working Memory: 現在のセッション（短期）
- Main Memory: 最近の履歴（中期）
- Archive Memory: 永続的な知識（長期、Vector DB）
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# データ構造
# =============================================================================


@dataclass
class MemoryItem:
    """メモリに保存する項目"""

    content: str
    timestamp: float = field(default_factory=time.time)
    importance: float = 0.5  # 0.0 - 1.0
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "timestamp": self.timestamp,
            "importance": self.importance,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryItem":
        return cls(**data)


# =============================================================================
# 抽象ベースクラス
# =============================================================================


class MemoryStore(ABC):
    """メモリストアの抽象基底クラス"""

    @abstractmethod
    def add(self, item: MemoryItem) -> None:
        pass

    @abstractmethod
    def search(self, query: str, k: int = 5) -> list[MemoryItem]:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


class EmbeddingProvider(ABC):
    """埋め込みベクトル生成の抽象基底クラス"""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        pass

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        pass


# =============================================================================
# Working Memory（短期記憶）
# =============================================================================


class WorkingMemory(MemoryStore):
    """
    Working Memory - 現在のセッションのコンテキスト

    特徴:
    - In-memory リスト
    - トークン制限あり
    - セッション終了で消去
    """

    def __init__(self, max_tokens: int = 4000):
        self.items: list[MemoryItem] = []
        self.max_tokens = max_tokens

    def add(self, item: MemoryItem) -> None:
        self.items.append(item)
        self._enforce_limit()

    def _enforce_limit(self) -> None:
        """トークン制限を超えた場合、古いものから削除"""
        total_tokens = sum(self._estimate_tokens(i.content) for i in self.items)
        while total_tokens > self.max_tokens and self.items:
            removed = self.items.pop(0)
            total_tokens -= self._estimate_tokens(removed.content)

    def _estimate_tokens(self, text: str) -> int:
        """トークン数を概算（1トークン ≈ 4文字）"""
        return len(text) // 4

    def search(self, query: str, k: int = 5) -> list[MemoryItem]:
        """最近のk件を返す（単純な実装）"""
        return self.items[-k:]

    def get_context(self) -> str:
        """現在のコンテキストを文字列として取得"""
        return "\n".join(item.content for item in self.items)

    def clear(self) -> None:
        self.items = []


# =============================================================================
# Main Memory（中期記憶）
# =============================================================================


class MainMemory(MemoryStore):
    """
    Main Memory - 最近の履歴と中間成果物

    特徴:
    - アイテム数制限あり
    - 重要度に基づく保持
    - キーワード検索対応
    """

    def __init__(self, max_items: int = 100):
        self.items: list[MemoryItem] = []
        self.max_items = max_items

    def add(self, item: MemoryItem) -> None:
        self.items.append(item)
        self._enforce_limit()

    def _enforce_limit(self) -> None:
        """制限を超えた場合、重要度の低いものから削除"""
        if len(self.items) > self.max_items:
            # 重要度でソートし、低いものを削除
            self.items.sort(key=lambda x: x.importance, reverse=True)
            self.items = self.items[: self.max_items]
            # タイムスタンプで再ソート
            self.items.sort(key=lambda x: x.timestamp)

    def search(self, query: str, k: int = 5) -> list[MemoryItem]:
        """キーワードマッチングで検索"""
        query_words = set(query.lower().split())
        scored = []

        for item in self.items:
            content_words = set(item.content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                score = overlap / len(query_words)
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:k]]

    def get_recent(self, k: int = 10) -> list[MemoryItem]:
        """最近のk件を取得"""
        return self.items[-k:]

    def clear(self) -> None:
        self.items = []


# =============================================================================
# Archive Memory（長期記憶）
# =============================================================================


class SimpleVectorStore:
    """
    シンプルなベクトルストア（教育用）

    本番環境では Pinecone, Weaviate, pgvector 等を使用してください。
    """

    def __init__(self):
        self.items: list[tuple[list[float], MemoryItem]] = []

    def add(self, embedding: list[float], item: MemoryItem) -> None:
        self.items.append((embedding, item))

    def search(self, query_embedding: list[float], k: int = 5) -> list[MemoryItem]:
        """コサイン類似度で検索"""
        if not self.items:
            return []

        scored = []
        for embedding, item in self.items:
            similarity = self._cosine_similarity(query_embedding, embedding)
            scored.append((similarity, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:k]]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """コサイン類似度を計算"""
        if len(a) != len(b):
            return 0.0
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def clear(self) -> None:
        self.items = []


class ArchiveMemory(MemoryStore):
    """
    Archive Memory - 永続的な知識

    特徴:
    - Vector DB を使用したセマンティック検索
    - 過去の成功パターン、学習した知識を保存
    - 永続化対応
    """

    def __init__(
        self,
        vector_store: SimpleVectorStore | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.vector_store = vector_store or SimpleVectorStore()
        self.embedding_provider = embedding_provider

    def add(self, item: MemoryItem) -> None:
        if self.embedding_provider and item.embedding is None:
            item.embedding = self.embedding_provider.embed(item.content)

        if item.embedding:
            self.vector_store.add(item.embedding, item)

    def search(self, query: str, k: int = 5) -> list[MemoryItem]:
        if not self.embedding_provider:
            return []

        query_embedding = self.embedding_provider.embed(query)
        return self.vector_store.search(query_embedding, k)

    def clear(self) -> None:
        self.vector_store.clear()


# =============================================================================
# 階層的メモリマネージャー
# =============================================================================


class HierarchicalMemory:
    """
    3層の階層的メモリを統合管理

    使用方法:
        memory = HierarchicalMemory()
        memory.remember("ユーザーはPythonを好む", importance=0.9)
        results = memory.recall("プログラミング言語の好み")
    """

    def __init__(
        self,
        working_max_tokens: int = 4000,
        main_max_items: int = 100,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.working = WorkingMemory(max_tokens=working_max_tokens)
        self.main = MainMemory(max_items=main_max_items)
        self.archive = ArchiveMemory(embedding_provider=embedding_provider)

    def remember(
        self,
        content: str,
        importance: float = 0.5,
        metadata: dict | None = None,
    ) -> None:
        """
        コンテンツを記憶

        Args:
            content: 記憶する内容
            importance: 重要度（0.0-1.0）
            metadata: 追加のメタデータ
        """
        item = MemoryItem(
            content=content,
            importance=importance,
            metadata=metadata or {},
        )

        # 常にWorking Memoryに追加
        self.working.add(item)

        # 重要度が0.5以上ならMain Memoryにも追加
        if importance >= 0.5:
            self.main.add(item)

        # 重要度が0.8以上ならArchiveにも追加
        if importance >= 0.8:
            self.archive.add(item)

    def recall(self, query: str, k: int = 5) -> list[MemoryItem]:
        """
        関連する記憶を検索

        Working → Main → Archive の順で検索し、
        必要な件数が集まるまで探索を続けます。
        """
        results = []

        # Working Memoryから検索
        working_results = self.working.search(query, k)
        results.extend(working_results)

        # 足りなければMain Memoryから検索
        if len(results) < k:
            main_results = self.main.search(query, k - len(results))
            results.extend(main_results)

        # まだ足りなければArchiveから検索
        if len(results) < k:
            archive_results = self.archive.search(query, k - len(results))
            results.extend(archive_results)

        return results[:k]

    def get_context_window(self) -> str:
        """現在のコンテキストウィンドウを取得"""
        return self.working.get_context()

    def summarize_and_archive(self, llm: Any) -> None:
        """
        Working Memoryを要約してArchiveに保存

        長時間のセッションで定期的に呼び出すことで、
        重要な情報を長期記憶に移行します。
        """
        context = self.working.get_context()
        if not context:
            return

        # LLMで要約（実装は省略）
        summary_prompt = f"""
        以下の会話を要約し、重要なポイントを抽出してください:

        {context}

        出力形式:
        - 重要なポイント1
        - 重要なポイント2
        ...
        """
        # summary = llm.generate(summary_prompt)
        # self.remember(summary, importance=0.9)

    def clear_working(self) -> None:
        """Working Memoryをクリア"""
        self.working.clear()

    def clear_all(self) -> None:
        """すべてのメモリをクリア"""
        self.working.clear()
        self.main.clear()
        self.archive.clear()


# =============================================================================
# ダミー埋め込みプロバイダー（デモ用）
# =============================================================================


class DummyEmbeddingProvider(EmbeddingProvider):
    """
    ダミーの埋め込みプロバイダー（教育用）

    本番環境では OpenAI Embeddings, Sentence-BERT 等を使用してください。
    """

    def __init__(self, dimension: int = 128):
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        """テキストのハッシュに基づく疑似埋め込み"""
        import hashlib

        hash_bytes = hashlib.sha256(text.encode()).digest()
        embedding = []
        for i in range(0, self.dimension * 4, 4):
            if i + 4 <= len(hash_bytes):
                value = int.from_bytes(hash_bytes[i : i + 4], "big")
                embedding.append((value / (2**32)) * 2 - 1)  # -1 to 1
        return embedding[: self.dimension]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


# =============================================================================
# デモ
# =============================================================================


def main():
    """デモ実行"""
    print("=" * 60)
    print("Hierarchical Memory Demo")
    print("=" * 60)

    # ダミー埋め込みプロバイダーを使用
    embedding_provider = DummyEmbeddingProvider(dimension=64)

    # 階層的メモリを作成
    memory = HierarchicalMemory(
        working_max_tokens=1000,
        main_max_items=50,
        embedding_provider=embedding_provider,
    )

    # 様々な重要度で記憶を追加
    memories = [
        ("ユーザーはPythonでコーディングを好む", 0.9),
        ("前回のタスクでテストを書いた", 0.6),
        ("現在の作業ディレクトリは /home/user/project", 0.3),
        ("エラーハンドリングのベストプラクティスを学んだ", 0.85),
        ("git commit メッセージの形式を確認した", 0.4),
    ]

    print("\n記憶を追加:")
    for content, importance in memories:
        memory.remember(content, importance=importance)
        print(f"  [{importance:.1f}] {content}")

    # 検索テスト
    print("\n検索テスト:")
    queries = ["プログラミング言語", "git", "テスト"]

    for query in queries:
        print(f"\n  Query: '{query}'")
        results = memory.recall(query, k=3)
        for item in results:
            print(f"    - [{item.importance:.1f}] {item.content}")

    # コンテキストウィンドウ
    print("\n現在のコンテキスト:")
    print(memory.get_context_window())


if __name__ == "__main__":
    main()
