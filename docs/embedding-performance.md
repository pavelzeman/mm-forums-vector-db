# Embedding performance

## The three phases of search — and where GPU matters

### 1. Bulk embedding (inference)
Converting all scraped posts to vectors. This is the slow, compute-heavy phase.
Runs once on initial load, then incrementally for new posts.
**GPU makes a large difference here.**

### 2. Query embedding (inference)
When a user types a search query, it goes through the same model to produce a vector.
This is a single short text — takes ~5 ms even on CPU. GPU not needed.

### 3. Vector search (ANN — approximate nearest neighbour)
Qdrant compares the query vector against all stored vectors to find the closest matches.
This is pure math (cosine similarity / dot product), not model inference.
Qdrant is optimised for it and runs fast on CPU regardless of collection size.

**Summary: GPU is only worth considering for phase 1 (bulk embedding).**

---

## What drives bulk embedding speed

| Factor | Impact | Notes |
|---|---|---|
| GPU | 50–100x | By far the biggest lever |
| CPU cores/speed | 2–4x | Matrix math parallelises well |
| Batch size | 2–3x | Larger batches amortise overhead |
| RAM | Minimal | Model fits in ~500 MB, rarely the bottleneck |

---

## Throughput benchmarks for `all-MiniLM-L6-v2`

| Hardware | Throughput | Time for ~150k posts |
|---|---|---|
| CX33 (4 vCPU) — current server | ~20 posts/s | ~2–3 hrs |
| 16-core CPU | ~80 posts/s | ~30 min |
| RTX 4090 | ~2,000 posts/s | ~90 sec |
| H100 | ~10,000 posts/s | ~15 sec |

---

## Practical options if speed matters

### Option A: Bump batch size (free, ~20% gain)
In `src/mm_forum/embedder/local.py`, increase `batch_size` from 64 to 256.
Helps if the model is underutilised between batches.

### Option B: Spot GPU instance for the initial run (~$1–2)
Spin up an AWS `g5.xlarge` (NVIDIA A10G, ~$0.50/hr spot) or similar.
Run the embedder, finish in minutes, shut it down.
The server running the app day-to-day doesn't need a GPU.

### Option C: Switch to OpenAI embeddings (offload entirely)
Set `EMBEDDING_MODEL=openai` in `.env`.
Pros: no local compute, fast, no GPU needed ever.
Cons: ~$0.02 per million tokens (probably <$1 for the whole forum),
requires `OPENAI_API_KEY`, adds latency per query embedding, external dependency.

---

## Terminology

**Inference** — running a trained model to produce outputs (embeddings, predictions).
Both bulk embedding and query embedding are inference. The model weights don't change.

**Training** — updating model weights on new data. We never do this;
we use a pre-trained model as-is.

**ANN (approximate nearest neighbour)** — the algorithm Qdrant uses to find the
closest vectors to a query vector. Not model inference — pure mathematical search.
Fast on CPU, scales well with collection size.

---

## Incremental runs

After the initial bulk embed, weekly re-runs only process posts added since the last run
(`WHERE embedding_id IS NULL`). At typical forum activity levels this is hundreds of posts,
taking seconds on CPU. GPU is irrelevant for incremental runs.
