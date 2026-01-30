# メモリ管理パターン

エージェントが長期的なタスクを遂行し、過去の経験から学習するための仕組みです。

## 概要

LLM はステートレスです。各リクエストは独立しており、前の会話を覚えていません。
メモリ管理により、エージェントは：
- 過去の会話コンテキストを維持
- 成功/失敗パターンを学習
- 長期的な知識を蓄積

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                      Memory Architecture                         │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │  Working Memory  │  │   Main Memory    │  │   Archive    │  │
│  │  (短期記憶)      │  │   (中期記憶)     │  │  (長期記憶)  │  │
│  ├──────────────────┤  ├──────────────────┤  ├──────────────┤  │
│  │ • 現在の会話     │  │ • 最近の履歴     │  │ • 過去の成功 │  │
│  │ • アクティブな   │  │ • ツール結果     │  │   パターン   │  │
│  │   コンテキスト   │  │ • 中間成果物     │  │ • 学習した   │  │
│  │ • ツール状態     │  │                  │  │   知識       │  │
│  └──────────────────┘  └──────────────────┘  └──────────────┘  │
│         ↑                      ↑                     ↑          │
│         │                      │                     │          │
│         └──────────────────────┴─────────────────────┘          │
│                         Retrieval Layer                          │
│                    (Vector DB / Semantic Search)                 │
└─────────────────────────────────────────────────────────────────┘
```

## メモリの種類

| メモリタイプ | 保持期間 | 実装方法 | 用途 |
|-------------|---------|---------|------|
| Working Memory | 現在のセッション | In-memory list | 会話コンテキスト |
| Main Memory | タスク単位 | Redis / SQLite | ツール実行結果 |
| Archive Memory | 永続 | Vector DB | 類似タスクの検索 |
| Procedural Memory | 永続 | Code/Config | 学習したスキル |

## 使用方法

```python
from memory import HierarchicalMemory, DummyEmbeddingProvider

# 階層的メモリを作成
embedding_provider = DummyEmbeddingProvider(dimension=64)
memory = HierarchicalMemory(
    working_max_tokens=4000,
    main_max_items=100,
    embedding_provider=embedding_provider,
)

# 記憶を追加（重要度に応じて適切な層に保存）
memory.remember("ユーザーはPythonを好む", importance=0.9)
memory.remember("一時的なメモ", importance=0.3)

# 関連する記憶を検索
results = memory.recall("プログラミング言語の好み", k=5)
for item in results:
    print(f"[{item.importance:.1f}] {item.content}")
```

## 主要クラス

### HierarchicalMemory

3層の階層的メモリを統合管理します。

```python
class HierarchicalMemory:
    def remember(self, content: str, importance: float = 0.5) -> None:
        """重要度に応じて適切な層に保存"""

    def recall(self, query: str, k: int = 5) -> list[MemoryItem]:
        """Working → Main → Archive の順で検索"""

    def get_context_window(self) -> str:
        """現在のコンテキストウィンドウを取得"""
```

### WorkingMemory

現在のセッションのコンテキストを管理します。
トークン制限を超えると古いものから削除されます。

### MainMemory

最近の履歴と中間成果物を保持します。
アイテム数制限があり、重要度の低いものから削除されます。

### ArchiveMemory

永続的な知識を Vector DB に保存します。
セマンティック検索で関連する記憶を取得できます。

## 本番環境での推奨事項

- **Vector DB**: Pinecone, Weaviate, pgvector
- **Embedding**: OpenAI Embeddings, Sentence-BERT
- **キャッシュ**: Redis for Working/Main Memory
- **永続化**: 定期的な Archive への移行

## 参考文献

- [Memory in the Age of AI Agents: A Survey](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)
- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12345)
- [Google ADK Multi-Agent Framework](https://developers.googleblog.com/architecting-efficient-context-aware-multi-agent-framework-for-production/)

## ファイル

- [memory.py](./memory.py) - 実装コード
