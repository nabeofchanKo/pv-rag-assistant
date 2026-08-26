# 埋め込みプロバイダ 検索ベンチ（Phase 5a）

> LLM非依存・決定的。gold事象語 → 正解MedDRA PT が top-k に入るか（hit@k）を、
> hybrid（exact⊕BM25⊕vector）と vector単独（埋め込み単体の質）で比較。`hard`=exact一致なし
> の難語サブセット＝埋め込みが実際に効く領域。`experiments/scripts/embedding_retrieval_bench.py` で再現。

- 対象: in-scope gold **23事象**（うち exact一致 13／**hard(exact無) 10**）
- プロバイダ: openai `text-embedding-3-small`(1536次元)、ollama `bge-m3`(1024次元)

## 全事象（n=23）

| プロバイダ | hybrid@1 | hybrid@3 | hybrid@5 | vector@1 | vector@3 | vector@5 |
|---|---|---|---|---|---|---|
| openai `text-embedding-3-small` | 96% (22/23) | 100% (23/23) | 100% (23/23) | 100% (23/23) | 100% (23/23) | 100% (23/23) |
| ollama `bge-m3` | 96% (22/23) | 100% (23/23) | 100% (23/23) | 96% (22/23) | 100% (23/23) | 100% (23/23) |

## hard サブセット（exact一致なし n=10）

| プロバイダ | hybrid@1 | hybrid@3 | hybrid@5 | vector@1 | vector@3 | vector@5 |
|---|---|---|---|---|---|---|
| openai `text-embedding-3-small` | 90% (9/10) | 100% (10/10) | 100% (10/10) | 100% (10/10) | 100% (10/10) | 100% (10/10) |
| ollama `bge-m3` | 90% (9/10) | 100% (10/10) | 100% (10/10) | 90% (9/10) | 100% (10/10) | 100% (10/10) |

## レイテンシ・インデックス構築

| プロバイダ | クエリ検索 平均(ms) | インデックス構築(ms, 56PT) |
|---|---|---|
| openai `text-embedding-3-small` | 189.3 | 1648 |
| ollama `bge-m3` | 259.8 | 7750 |

## vector@3 の食い違い（hard サブセット）

_（hard サブセットで vector@3 の差異なし）_

## 読み方（限界）

- これは**検索の質**のみ（埋め込み単体を分離）。実運用の最終精度は後段LLMのcandidate選択に依存＝別途end-to-endで測る。
- exact/BM25 が効く語では埋め込みは無関係。差が出るのは **hard サブセット**。標本が小さいので百分率は高分散。
- hybrid は exact⊕BM25 を含むため、vector単独が弱くても hybrid は保たれ得る（＝ローカル埋め込みの弱さを字句が吸収する構造）。
- **クエリ検索レイテンシは3回warmup後の定常値**（初回VRAMロードを除外）。インデックス構築(ms)は初回モデルロードを含む一回限りコスト。ローカルはGPU、OpenAIはネットワーク往復。