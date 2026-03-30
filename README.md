# mm-forums-vector-db

Semantic search over the [Mattermost community forum](https://forum.mattermost.com).
Scrapes Discourse posts, embeds them with sentence-transformers or OpenAI, stores vectors
in Qdrant, and serves a Streamlit search UI.

## Key concepts

**Streamlit** — Python library that turns a Python script into an interactive web app.
No HTML/CSS/JS needed. Used here as the search UI.

**Alembic** — Database migration tool for SQLAlchemy. Tracks schema changes over time
(like git for your database). `alembic upgrade head` brings any environment to the current
schema. Always run this after deploying a new version.

**Qdrant** — Vector database. Stores post embeddings and answers nearest-neighbour queries
(semantic search). Runs as a Docker container alongside Postgres.

**sentence-transformers** — Python library for generating text embeddings locally using
pre-trained models. Requires PyTorch, which makes the Docker image large (~1.2 GB).

**Inference** — running a trained model to produce outputs (embeddings). Happens twice:
once in bulk when embedding all posts, and once per search query to embed the query text.
The model weights never change — we use a pre-trained model as-is.

**ANN (approximate nearest neighbour)** — the algorithm Qdrant uses to find vectors
closest to the query vector. Not model inference — pure mathematical search (cosine
similarity). Fast on CPU, unaffected by the embedding model size.

**RAG (Retrieval Augmented Generation)** — the pattern that powers Answer mode.
Retrieve relevant forum posts via vector search, pass their text as context to an LLM,
and let the LLM synthesize a grounded answer. The LLM answers only from what the posts
contain — no hallucination, every claim traceable to a source. See
[docs/how-rag-works.md](docs/how-rag-works.md) for a detailed explanation.

## Architecture

```
Discourse forum
      │
      ▼
run_scrape.py  ──►  PostgreSQL (topics, posts, categories)
                          │
run_embed.py   ──►  Qdrant (vector embeddings)
                          │
streamlit_app.py ──►  https://mmforums.mattermosteng.online
      ├── Search mode: returns ranked forum post links
      └── Answer mode: RAG — retrieves posts → LLM generates answer
```

## Docker Compose files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Base services (Postgres, Qdrant) — no external ports exposed |
| `docker-compose.dev.yml` | Adds external ports for local access (Postgres: 5433, Qdrant: 6333) |
| `docker-compose.prod.yml` | Prod overrides: nginx, letsencrypt, restart policies, streamlit service |

Local dev: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`
Prod: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`

---

## Local development

**Prerequisites:** Docker, Python 3.12+

```bash
# Start Postgres + Qdrant with local ports exposed
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Install package with dev extras
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run migrations
alembic upgrade head

# Run scraper
python scripts/run_scrape.py

# Run embedder
python scripts/run_embed.py

# Launch Streamlit
streamlit run app/streamlit_app.py
```

Copy `.env.example` to `.env` and adjust values before running locally.
In `.env`, use `DATABASE_URL=postgresql://mm:changeme@localhost:5433/mm_forum` (port 5433 for local dev).

---

## Deploying to Hetzner

### 1. Prerequisites

- Hetzner Cloud account + API token
- SSH key registered in your Hetzner project
- A domain with DNS you control
- If your SSH key is in 1Password: enable the 1Password SSH agent (Settings → Developer →
  Use the SSH agent) and add this to `~/.ssh/config`:
  ```
  Host *
      IdentityAgent "~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock"
  ```

### 2. Provision the server

```bash
HCLOUD_TOKEN=<token> \
HCLOUD_SSH_KEY=<key-name-in-hetzner> \
DOMAIN=<your-domain> \
HCLOUD_LOCATION=fsn1 \
HCLOUD_SERVER_TYPE=cx33 \
bash deploy/provision_hetzner.sh
```

Note the server IPv4 from the output.

### 3. Point DNS

Add an **A record**: `<your-domain>` → `<server-ipv4>`

If using Cloudflare, set it to **DNS only (grey cloud)** — the orange proxy will break
certbot. You can re-enable it after SSL is provisioned.

### 4. Wait for cloud-init

```bash
ssh root@<server-ipv4> 'cloud-init status --wait'
```

This installs Docker, Docker Compose, certbot, and UFW (~60–90 s).

### 5. Provision the SSL certificate

```bash
ssh root@<server-ipv4> 'certbot certonly --standalone -d <your-domain>'
```

Certbot sets up automatic renewal. Certs land in `/etc/letsencrypt/live/<your-domain>/`
and are bind-mounted read-only into the nginx container.

### 6. Clone the repo and create `.env`

The repo is public so no auth is needed:

```bash
ssh root@<server-ipv4>
git clone https://github.com/pavelzeman/mm-forums-vector-db.git /home/deploy/projects/mm-forums-vector-db
chown -R deploy:deploy /home/deploy/projects
```

Create the `.env` file:

```bash
cp /home/deploy/projects/mm-forums-vector-db/.env.example \
   /home/deploy/projects/mm-forums-vector-db/.env
chmod 600 /home/deploy/projects/mm-forums-vector-db/.env
nano /home/deploy/projects/mm-forums-vector-db/.env
```

Set these values:
- `DOMAIN=<your-domain>`
- `POSTGRES_PASSWORD=<strong-random-password>` — generate with `openssl rand -base64 32`
- `DATABASE_URL=postgresql://mm:<password>@postgres:5432/mm_forum` — use port `5432` (not `5433`, which is local dev only)
- `OPENAI_API_KEY` if using OpenAI embeddings

### 7. Start the stack

```bash
su - deploy
cd ~/projects/mm-forums-vector-db
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The first build takes several minutes due to PyTorch (see [Why is the first build slow?](#why-is-the-first-build-slow)).

### 8. Run migrations and the data pipeline

```bash
# Run as deploy user from ~/projects/mm-forums-vector-db

# Apply database schema
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit alembic upgrade head

# Scrape the forum (resumable if interrupted)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/run_scrape.py

# Embed the posts
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/run_embed.py
```

The Streamlit search UI will return results once embedding is complete.

---

## Updating the server

```bash
su - deploy
cd ~/projects/mm-forums-vector-db
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit alembic upgrade head
```

---

## CI/CD pipeline

Every push to `main` runs tests (pytest with Postgres + Qdrant service containers).
A full build-and-deploy pipeline will be added when moving to AWS.

---

## Why is the first build slow?

The Docker image is large (~1.2 GB) because `sentence-transformers` bundles:

- **PyTorch** (~800 MB) — the deep learning framework, includes CUDA binaries even on CPU-only servers
- **Hugging Face Transformers** (~200 MB)
- **Model weights** — `all-MiniLM-L6-v2` is ~90 MB
- **NumPy, SciPy, tokenizers** — ~100 MB

PyTorch is the main culprit. Subsequent builds are fast because Docker caches the layer.

**Alternative:** set `EMBEDDING_MODEL=openai` in `.env` to skip local inference entirely and
use the OpenAI API instead. The image will be much smaller and builds will be faster, but
embeddings have a per-token cost and require `OPENAI_API_KEY`.

---

## Migrating to AWS

When ready to move from Hetzner to AWS, use `deploy/migrate_to_aws.sh`. It requires
SSH access to both servers from your laptop and no intermediate storage (S3, etc.).

```bash
HETZNER_HOST=46.224.111.133 \
AWS_HOST=<ec2-ip> \
AWS_USER=ec2-user \
bash deploy/migrate_to_aws.sh
```

What it does:
- **Postgres** — streams `pg_dump | pg_restore` directly Hetzner → laptop → AWS (no temp file)
- **Qdrant** — takes a snapshot on Hetzner, stages it locally, uploads and restores on AWS
- Prints a verification checklist before you flip DNS

AWS prerequisite: the stack must be running (`docker compose up -d`) with an empty database
before you run the script — it overwrites whatever is there.

Migration order:
1. Provision AWS infra and start the empty stack
2. Run `migrate_to_aws.sh`
3. Verify the app works on the AWS IP
4. Update DNS A record to AWS IP
5. Wait for TTL to expire, then shut down the Hetzner server

---

## What the embedder does

The scraper stores raw post text in Postgres. The embedder reads those posts and converts
each one into a **vector** — a list of ~384 numbers representing the semantic meaning of
the text. Similar meaning = similar numbers = close together in vector space.

When you search, your query is converted to a vector the same way, and Qdrant finds the
posts whose vectors are closest to it. This is why a query like
*"users not receiving email notifications after SMTP setup"* finds relevant posts even if
no post contains those exact words — it matches on **meaning**, not keywords.

The vectors are stored in Qdrant. Postgres keeps the raw text and metadata. The two are
linked by `embedding_id` on each post row.

Run the embedder after every scrape to keep the vector index current:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/run_embed.py
```

---

## Sample search queries

Use these to verify the search is working after embedding completes.
Open **https://mmforums.mattermosteng.online** and try them in order.

### Basic — single concept, obvious keyword match
1. `how to install Mattermost`
2. `reset password`
3. `LDAP configuration`
4. `mobile app notifications`
5. `create a new channel`

### Medium — multi-concept, less obvious phrasing
1. `users not receiving email notifications after SMTP setup`
2. `difference between team and channel admin permissions`
3. `migrate from Slack to Mattermost`
4. `webhook payload format for incoming messages`
5. `plugin not showing up after install`

### Advanced — situational, requires context understanding
1. `server upgrade broke existing integrations and bots stopped responding`
2. `high memory usage on self-hosted instance with many concurrent users`
3. `guest accounts can see channels they shouldn't have access to`
4. `how to archive old channels without losing message history for compliance`
5. `custom emoji not syncing across cluster nodes`

### Super advanced — cross-cutting, nuanced, expert-level
These are the real test. A keyword search would struggle; semantic search should surface
relevant threads even when the exact words don't appear in any post.

1. `trade-offs between database connection pooling settings and Mattermost performance under load`
2. `SAML SSO with Okta works for web but mobile app falls back to password auth`
3. `configuring rate limiting to protect the API without breaking high-volume bot integrations`
4. `recommended approach for zero-downtime Mattermost upgrades in a Kubernetes deployment`
5. `audit log gaps when using read replicas — some user actions not appearing in compliance exports`

---

## Re-running the pipeline

```bash
# Scrape new posts (resumable)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/run_scrape.py

# Embed any unembedded posts
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/run_embed.py

# Query from CLI
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/query.py "your search query"
```
