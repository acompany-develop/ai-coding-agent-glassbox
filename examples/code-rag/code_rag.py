"""
コードベース用 RAG（Retrieval-Augmented Generation）

大規模コードベースから関連するコードを検索し、
LLMのコンテキストとして提供します。

アーキテクチャ:
1. Indexing: コードをチャンク化 → 埋め込み → Vector DB に保存
2. Retrieval: クエリ → Vector Search → LLM Re-ranking
3. Generation: 検索結果をコンテキストとしてLLMに渡す
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# =============================================================================
# データ構造
# =============================================================================


@dataclass
class CodeChunk:
    """コードのチャンク（断片）"""

    id: str
    content: str
    file_path: str
    start_line: int
    end_line: int
    chunk_type: str  # function, class, module, block
    name: str = ""  # 関数名、クラス名など
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None

    @property
    def location(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"

    def to_context(self) -> str:
        """LLMコンテキスト用の形式"""
        return f"""
# {self.location} ({self.chunk_type}: {self.name})
```
{self.content}
```
"""


@dataclass
class SearchResult:
    """検索結果"""

    chunk: CodeChunk
    score: float
    match_type: str = "semantic"  # semantic, keyword, exact


# =============================================================================
# チャンキング戦略
# =============================================================================


class ChunkingStrategy(ABC):
    """チャンキング戦略の抽象基底クラス"""

    @abstractmethod
    def chunk(self, content: str, file_path: str) -> list[CodeChunk]:
        pass


class FixedSizeChunker(ChunkingStrategy):
    """固定サイズでチャンク化"""

    def __init__(self, chunk_size: int = 50, overlap: int = 10):
        self.chunk_size = chunk_size  # 行数
        self.overlap = overlap

    def chunk(self, content: str, file_path: str) -> list[CodeChunk]:
        lines = content.split("\n")
        chunks = []

        for i in range(0, len(lines), self.chunk_size - self.overlap):
            chunk_lines = lines[i : i + self.chunk_size]
            chunk_content = "\n".join(chunk_lines)

            chunk_id = hashlib.md5(
                f"{file_path}:{i}:{chunk_content}".encode()
            ).hexdigest()[:12]

            chunks.append(
                CodeChunk(
                    id=chunk_id,
                    content=chunk_content,
                    file_path=file_path,
                    start_line=i + 1,
                    end_line=i + len(chunk_lines),
                    chunk_type="block",
                )
            )

        return chunks


class ASTChunker(ChunkingStrategy):
    """AST（抽象構文木）ベースでチャンク化（Python用）"""

    def __init__(self, min_lines: int = 5, max_lines: int = 100):
        self.min_lines = min_lines
        self.max_lines = max_lines

    def chunk(self, content: str, file_path: str) -> list[CodeChunk]:
        chunks = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            # パース失敗時は固定サイズにフォールバック
            return FixedSizeChunker().chunk(content, file_path)

        lines = content.split("\n")

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunk = self._extract_chunk(
                    node, lines, file_path, "function", node.name
                )
                if chunk:
                    chunks.append(chunk)

            elif isinstance(node, ast.ClassDef):
                chunk = self._extract_chunk(
                    node, lines, file_path, "class", node.name
                )
                if chunk:
                    chunks.append(chunk)

        # チャンクがない場合はモジュール全体を1チャンクに
        if not chunks:
            chunk_id = hashlib.md5(f"{file_path}:module".encode()).hexdigest()[:12]
            chunks.append(
                CodeChunk(
                    id=chunk_id,
                    content=content,
                    file_path=file_path,
                    start_line=1,
                    end_line=len(lines),
                    chunk_type="module",
                )
            )

        return chunks

    def _extract_chunk(
        self,
        node: ast.AST,
        lines: list[str],
        file_path: str,
        chunk_type: str,
        name: str,
    ) -> CodeChunk | None:
        """ASTノードからチャンクを抽出"""
        start_line = node.lineno
        end_line = node.end_lineno or start_line

        # サイズ制限をチェック
        num_lines = end_line - start_line + 1
        if num_lines < self.min_lines or num_lines > self.max_lines:
            return None

        content = "\n".join(lines[start_line - 1 : end_line])
        chunk_id = hashlib.md5(
            f"{file_path}:{chunk_type}:{name}".encode()
        ).hexdigest()[:12]

        return CodeChunk(
            id=chunk_id,
            content=content,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            chunk_type=chunk_type,
            name=name,
        )


# =============================================================================
# 埋め込みプロバイダー
# =============================================================================


class EmbeddingProvider(ABC):
    """埋め込みベクトル生成の抽象基底クラス"""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        pass

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        pass


class DummyEmbeddingProvider(EmbeddingProvider):
    """ダミーの埋め込みプロバイダー（教育用）"""

    def __init__(self, dimension: int = 128):
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        """テキストのハッシュに基づく疑似埋め込み"""
        hash_bytes = hashlib.sha256(text.encode()).digest()
        embedding = []
        for i in range(0, min(self.dimension * 4, len(hash_bytes)), 4):
            value = int.from_bytes(hash_bytes[i : i + 4], "big")
            embedding.append((value / (2**32)) * 2 - 1)

        # 次元が足りない場合はパディング
        while len(embedding) < self.dimension:
            embedding.append(0.0)

        return embedding[: self.dimension]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


# =============================================================================
# ベクトルストア
# =============================================================================


class SimpleVectorStore:
    """シンプルなベクトルストア（教育用）"""

    def __init__(self):
        self.chunks: list[CodeChunk] = []

    def add(self, chunk: CodeChunk) -> None:
        self.chunks.append(chunk)

    def add_batch(self, chunks: list[CodeChunk]) -> None:
        self.chunks.extend(chunks)

    def search(
        self, query_embedding: list[float], k: int = 10
    ) -> list[tuple[CodeChunk, float]]:
        """コサイン類似度で検索"""
        if not self.chunks:
            return []

        results = []
        for chunk in self.chunks:
            if chunk.embedding:
                similarity = self._cosine_similarity(query_embedding, chunk.embedding)
                results.append((chunk, similarity))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def clear(self) -> None:
        self.chunks = []


# =============================================================================
# Code RAG
# =============================================================================


class CodeRAG:
    """
    コードベース用 RAG

    使用方法:
        rag = CodeRAG()
        rag.index_directory("./src")
        results = rag.search("認証処理の実装")
        context = rag.build_context(results)
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        chunking_strategy: ChunkingStrategy | None = None,
    ):
        self.embedding_provider = embedding_provider or DummyEmbeddingProvider()
        self.chunking_strategy = chunking_strategy or ASTChunker()
        self.vector_store = SimpleVectorStore()
        self.indexed_files: set[str] = set()

    def index_file(self, file_path: str) -> int:
        """ファイルをインデックス化"""
        if file_path in self.indexed_files:
            return 0

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return 0

        # チャンク化
        chunks = self.chunking_strategy.chunk(content, file_path)

        # 埋め込みを生成
        for chunk in chunks:
            chunk.embedding = self.embedding_provider.embed(chunk.content)

        # ベクトルストアに追加
        self.vector_store.add_batch(chunks)
        self.indexed_files.add(file_path)

        return len(chunks)

    def index_directory(
        self,
        directory: str,
        extensions: list[str] = None,
        exclude_patterns: list[str] = None,
    ) -> dict:
        """ディレクトリを再帰的にインデックス化"""
        extensions = extensions or [".py"]
        exclude_patterns = exclude_patterns or ["__pycache__", ".git", "venv", ".venv"]

        stats = {"files": 0, "chunks": 0, "errors": 0}

        for root, dirs, files in os.walk(directory):
            # 除外パターンに一致するディレクトリをスキップ
            dirs[:] = [
                d
                for d in dirs
                if not any(pattern in d for pattern in exclude_patterns)
            ]

            for file in files:
                if not any(file.endswith(ext) for ext in extensions):
                    continue

                file_path = os.path.join(root, file)

                try:
                    num_chunks = self.index_file(file_path)
                    stats["files"] += 1
                    stats["chunks"] += num_chunks
                except Exception as e:
                    stats["errors"] += 1
                    print(f"Error indexing {file_path}: {e}")

        return stats

    def search(
        self,
        query: str,
        k: int = 10,
        rerank: bool = True,
        llm: Any = None,
    ) -> list[SearchResult]:
        """
        コードを検索

        Args:
            query: 検索クエリ
            k: 返す結果の数
            rerank: LLMで再ランキングするか
            llm: 再ランキング用のLLMクライアント

        Returns:
            SearchResult のリスト
        """
        # Stage 1: Vector Search
        query_embedding = self.embedding_provider.embed(query)
        candidates = self.vector_store.search(query_embedding, k=k * 3)

        results = [
            SearchResult(chunk=chunk, score=score, match_type="semantic")
            for chunk, score in candidates
        ]

        # Stage 2: LLM Re-ranking (オプション)
        if rerank and llm and len(results) > k:
            results = self._rerank_with_llm(query, results, k, llm)
        else:
            results = results[:k]

        return results

    def _rerank_with_llm(
        self,
        query: str,
        results: list[SearchResult],
        k: int,
        llm: Any,
    ) -> list[SearchResult]:
        """LLMで検索結果を再ランキング"""
        # 候補をフォーマット
        candidates_text = "\n\n".join(
            f"[{i}] {r.chunk.location}\n{r.chunk.content[:200]}..."
            for i, r in enumerate(results)
        )

        prompt = f"""以下のコード片を、クエリへの関連性順にランク付けしてください。

クエリ: {query}

コード片:
{candidates_text}

最も関連性の高い{k}件のインデックス番号をカンマ区切りで返してください。
例: 2,0,5,1,3
"""

        try:
            response = llm.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )

            # インデックスをパース
            indices_str = response.text.strip()
            indices = [int(i.strip()) for i in indices_str.split(",") if i.strip().isdigit()]

            # 結果を再順序付け
            reranked = []
            for idx in indices[:k]:
                if 0 <= idx < len(results):
                    results[idx].match_type = "reranked"
                    reranked.append(results[idx])

            return reranked

        except Exception:
            # 再ランキング失敗時は元の順序を返す
            return results[:k]

    def build_context(
        self,
        results: list[SearchResult],
        max_tokens: int = 4000,
    ) -> str:
        """
        検索結果からLLMコンテキストを構築

        Args:
            results: 検索結果
            max_tokens: 最大トークン数

        Returns:
            LLMに渡すコンテキスト文字列
        """
        context_parts = []
        total_chars = 0
        max_chars = max_tokens * 4  # 1トークン ≈ 4文字

        for result in results:
            chunk_context = result.chunk.to_context()
            if total_chars + len(chunk_context) > max_chars:
                break
            context_parts.append(chunk_context)
            total_chars += len(chunk_context)

        return "\n---\n".join(context_parts)

    def get_stats(self) -> dict:
        """インデックスの統計情報"""
        return {
            "indexed_files": len(self.indexed_files),
            "total_chunks": len(self.vector_store.chunks),
            "chunk_types": self._count_chunk_types(),
        }

    def _count_chunk_types(self) -> dict:
        counts = {}
        for chunk in self.vector_store.chunks:
            counts[chunk.chunk_type] = counts.get(chunk.chunk_type, 0) + 1
        return counts


# =============================================================================
# デモ
# =============================================================================


def main():
    """デモ実行"""
    print("=" * 60)
    print("Code RAG Demo")
    print("=" * 60)

    # RAGインスタンスを作成
    rag = CodeRAG()

    # サンプルコードをインデックス化
    sample_code = '''
def authenticate_user(username: str, password: str) -> bool:
    """ユーザー認証を行う"""
    user = get_user_by_username(username)
    if user is None:
        return False
    return verify_password(password, user.password_hash)

def hash_password(password: str) -> str:
    """パスワードをハッシュ化"""
    import hashlib
    salt = generate_salt()
    return hashlib.sha256((password + salt).encode()).hexdigest()

class UserService:
    """ユーザー管理サービス"""

    def __init__(self, db):
        self.db = db

    def create_user(self, username: str, email: str) -> User:
        """新規ユーザーを作成"""
        user = User(username=username, email=email)
        self.db.add(user)
        return user

    def get_user(self, user_id: int) -> User:
        """ユーザーを取得"""
        return self.db.query(User).filter_by(id=user_id).first()
'''

    # 一時ファイルに書き込んでインデックス化
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(sample_code)
        temp_path = f.name

    try:
        # インデックス化
        print("\n--- Indexing ---")
        num_chunks = rag.index_file(temp_path)
        print(f"Indexed {num_chunks} chunks")

        stats = rag.get_stats()
        print(f"Stats: {stats}")

        # 検索テスト
        print("\n--- Search Tests ---")
        queries = ["認証", "ユーザー作成", "パスワード"]

        for query in queries:
            print(f"\nQuery: '{query}'")
            results = rag.search(query, k=2)

            for i, result in enumerate(results):
                print(f"  [{i + 1}] {result.chunk.location} (score: {result.score:.3f})")
                print(f"      Type: {result.chunk.chunk_type}, Name: {result.chunk.name}")

        # コンテキスト構築
        print("\n--- Context Building ---")
        results = rag.search("ユーザー認証の実装方法", k=3)
        context = rag.build_context(results, max_tokens=2000)
        print(f"Context length: {len(context)} chars")
        print("Context preview:")
        print(context[:500] + "...")

    finally:
        os.unlink(temp_path)


if __name__ == "__main__":
    main()
