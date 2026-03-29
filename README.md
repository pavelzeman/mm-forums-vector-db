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

## Re-running the pipeline

```bash
# Scrape new posts (resumable)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/run_scrape.py

# Embed any unembedded posts
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/run_embed.py

# Query from CLI
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/query.py "your search query"
```
