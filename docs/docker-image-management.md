# Docker image management

## Layer structure

The Dockerfile is ordered to maximize cache reuse:

```
Layer 1: system packages (gcc, libpq-dev, etc.)      — changes rarely
Layer 2: PyTorch CPU-only wheel                       — changes rarely
Layer 3: remaining Python dependencies                — changes when pyproject.toml changes
Layer 4: source code (src/, app/, scripts/)           — changes frequently
```

When you change only application code, Docker reuses layers 1–3 and only rebuilds layer 4.
This makes iterative rebuilds take seconds rather than minutes.

## PyTorch CPU-only wheel

The default PyTorch pip wheel includes CUDA binaries for GPU support (~800 MB).
This server has no GPU, so we install the CPU-only variant (~200 MB):

```dockerfile
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
```

This alone cuts ~600 MB from the image size and significantly speeds up the first build.

## Dependency caching trick

pip needs the package source to resolve dependencies. To avoid copying `src/` before
the pip install step (which would bust the cache on every source change), we stub out
the package with an empty `__init__.py`:

```dockerfile
COPY pyproject.toml .
RUN mkdir -p src/mm_forum && touch src/mm_forum/__init__.py && \
    pip install --no-cache-dir ".[app]"

# Real source copied after — only invalidates layers below, not pip install
COPY src/ src/
```

## Build times

| Scenario | Expected time |
|---|---|
| First ever build (cold cache) | 4–8 min (downloading PyTorch + all deps) |
| After `pyproject.toml` change | 3–5 min (reinstalls deps) |
| After source-only change | ~30 s (only COPY layers rebuild) |

## Rebuilding on the server

```bash
cd ~/projects/mm-forums-vector-db
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

After a source-only change the `--build` step completes in ~30 s.

## Image size vs embedding model

If build time or image size is still a concern, switch to the OpenAI embedder —
it removes sentence-transformers and PyTorch from the image entirely:

```bash
# In .env on the server
EMBEDDING_MODEL=openai
OPENAI_API_KEY=<your-key>
```

Trade-off: embeddings cost money per token and require an internet call per batch,
vs free local inference with a ~1 GB image.
