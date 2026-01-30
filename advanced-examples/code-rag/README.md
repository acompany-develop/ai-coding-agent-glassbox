# コードベース用 RAG（Retrieval-Augmented Generation）

大規模コードベースから関連するコードを検索し、LLM のコンテキストとして提供します。

## 概要

LLM のコンテキストウィンドウには制限があります。
RAG により、必要な時に必要なコードだけを検索してコンテキストに含めることで、
大規模コードベースでも効果的に作業できます。

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                    Code RAG Architecture                         │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Indexing Pipeline                       │  │
│  │                                                            │  │
│  │  Source Code ──▶ Chunking ──▶ Embedding ──▶ Vector DB     │  │
│  │      │              │                                      │  │
│  │      │         [関数/クラス/                               │  │
│  │      │          ファイル単位]                              │  │
│  │      ▼                                                     │  │
│  │  AST Parser ──▶ Knowledge Graph (依存関係)                 │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Retrieval Pipeline                      │  │
│  │                                                            │  │
│  │  Query ──▶ Embedding ──▶ Vector Search ──▶ Re-ranking     │  │
│  │                              │              (LLM)          │  │
│  │                              ▼                             │  │
│  │                    Top-K Candidates ──▶ Context            │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## チャンキング戦略

コードは自然言語と異なり、構造を意識したチャンキングが重要です。

| 戦略 | 粒度 | メリット | デメリット |
|------|-----|---------|-----------|
| 固定長 | 行数/文字数 | シンプル | 構造を壊す |
| 関数単位 | function/method | 意味的に完結 | サイズ不均一 |
| クラス単位 | class | 関連機能がまとまる | 大きすぎる場合あり |
| AST ベース | 構文木 | 正確な境界 | パーサー必要 |

## 使用方法

```python
from code_rag import CodeRAG

# RAGインスタンスを作成
rag = CodeRAG()

# ディレクトリをインデックス化
stats = rag.index_directory("./src", extensions=[".py"])
print(f"Indexed {stats['files']} files, {stats['chunks']} chunks")

# コードを検索
results = rag.search("認証処理の実装", k=5)
for result in results:
    print(f"{result.chunk.location} (score: {result.score:.3f})")

# LLMコンテキストを構築
context = rag.build_context(results, max_tokens=4000)
```

## 2段階検索

精度を高めるため、2段階の検索を行います。

### Stage 1: Vector Search（高速・大量）

埋め込みベクトルの類似度で候補を絞り込みます。

```python
# 検索候補を多めに取得
candidates = vector_store.search(query_embedding, k=30)
```

### Stage 2: LLM Re-ranking（精度向上）

LLM を使って関連性を再評価し、最終的な結果を選択します。

```python
def rerank_with_llm(query: str, candidates: list, k: int) -> list:
    prompt = f"""
    Query: {query}

    以下のコード片を関連性順にランク付けしてください。
    {format_candidates(candidates)}

    最も関連性の高い{k}件のIDを返してください。
    """
    ranking = llm.generate(prompt)
    return select_top_k(candidates, ranking, k)
```

## 主要クラス

### CodeRAG

```python
class CodeRAG:
    def index_file(self, file_path: str) -> int:
        """ファイルをインデックス化"""

    def index_directory(self, directory: str, extensions: list) -> dict:
        """ディレクトリを再帰的にインデックス化"""

    def search(self, query: str, k: int = 10) -> list[SearchResult]:
        """コードを検索"""

    def build_context(self, results: list, max_tokens: int) -> str:
        """検索結果からLLMコンテキストを構築"""
```

### ASTChunker

Python の AST（抽象構文木）を使用して、関数やクラス単位でチャンク化します。

```python
class ASTChunker:
    def chunk(self, content: str, file_path: str) -> list[CodeChunk]:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # 関数をチャンクとして抽出
            elif isinstance(node, ast.ClassDef):
                # クラスをチャンクとして抽出
```

## 本番環境での推奨事項

- **Vector DB**: Pinecone, Weaviate, Chroma, pgvector
- **Embedding**: OpenAI `text-embedding-3-small`, CodeBERT
- **Code Parser**: Tree-sitter（多言語対応）
- **Knowledge Graph**: Neo4j（依存関係の可視化）

## 参考文献

- [RAG for a Codebase with 10k Repos](https://www.qodo.ai/blog/rag-for-large-scale-code-repos/)
- [Code-Graph RAG](https://github.com/vitali87/code-graph-rag)
- [Retrieval-Augmented Code Generation Survey](https://arxiv.org/html/2510.04905v1)
- [What Is RAG for Codebases](https://codeforgeek.com/rag-retrieval-augmented-generation-for-codebases/)

## ファイル

- [code_rag.py](./code_rag.py) - 実装コード
