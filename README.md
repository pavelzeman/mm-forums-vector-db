# mm-forums-vector-db

Semantic search over the [Mattermost community forum](https://forum.mattermost.com).
Scrapes Discourse posts, embeds them with sentence-transformers or OpenAI, stores vectors
in Qdrant, and serves a Streamlit search UI.

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

## Local development

**Prerequisites:** Docker, Python 3.12+

```bash
# Start Postgres + Qdrant
docker compose up -d

# Install package with dev extras
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run scraper
python scripts/run_scrape.py

# Run embedder
python scripts/run_embed.py

# Launch Streamlit
streamlit run app/streamlit_app.py
```

Copy `.env.example` to `.env` and adjust values before running locally.

---

## Deploying to Hetzner

### 1. Prerequisites

- Hetzner Cloud account + API token
- SSH key registered in your Hetzner project
- A domain with DNS you control
- GitHub repository with Actions enabled

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

### 5. Set up the deploy user's SSH access for GitHub Actions

Generate a dedicated deploy key pair (one-time):

```bash
ssh-keygen -t ed25519 -C "github-mm-forum-actions-deploy" -f ./deploy/deploy-key -N ""
```

Add the public key to the server:

```bash
ssh root@<server-ipv4> '
  mkdir -p /home/deploy/.ssh
  echo "<paste contents of deploy/deploy-key.pub>" >> /home/deploy/.ssh/authorized_keys
  chown -R deploy:deploy /home/deploy/.ssh
  chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys
'
```

> Do not commit `deploy/deploy-key` (private key) to the repo.

### 6. Add GitHub Actions secrets

In **github.com/\<org\>/mm-forums-vector-db → Settings → Secrets → Actions**, add:

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | Server IPv4 |
| `DEPLOY_SSH_KEY` | Contents of `deploy/deploy-key` (the private key) |

When pasting the private key, copy it directly from the file — do not retype it, as
whitespace corruption will cause `ssh: no key found` errors.

### 7. Create the app directory on the server

```bash
ssh root@<server-ipv4> 'mkdir -p /srv/mm-forums/nginx && chown -R deploy:deploy /srv/mm-forums'
```

### 8. Create the `.env` file on the server

```bash
scp .env.example root@<server-ipv4>:/srv/mm-forums/.env
ssh root@<server-ipv4> 'chown deploy:deploy /srv/mm-forums/.env && chmod 600 /srv/mm-forums/.env'
```

Then edit `/srv/mm-forums/.env` on the server and set:
- `DOMAIN=<your-domain>`
- `POSTGRES_PASSWORD=<strong-random-password>` — generate one with `openssl rand -base64 32`
- `DATABASE_URL=postgresql://mm:<password>@postgres:5432/mm_forum` (use port `5432`, not `5433`)
- `OPENAI_API_KEY` if using OpenAI embeddings

### 9. Provision the SSL certificate

```bash
ssh root@<server-ipv4> 'certbot certonly --standalone -d <your-domain>'
```

Certbot sets up automatic renewal. The certs land in `/etc/letsencrypt/live/<your-domain>/`
and are bind-mounted into the nginx container.

### 10. Trigger the first deploy

Push any commit to `main`. GitHub Actions will:

1. Run tests
2. Build the Docker image and push to `ghcr.io/pavelzeman/mm-forums-vector-db:latest`
3. SCP the compose files to `/srv/mm-forums/` on the server
4. SSH in, pull the new image, and restart the stack
5. Run `alembic upgrade head` (database migrations)

Watch the run at **github.com/pavelzeman/mm-forums-vector-db/actions**.

### 11. Run the data pipeline (first time only)

SSH into the server as the `deploy` user:

```bash
ssh root@<server-ipv4>
su - deploy
cd /srv/mm-forums
```

Run migrations (if the automatic migration in CI didn't apply):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit alembic upgrade head
```

Scrape the forum (takes a while — resumable if interrupted):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/run_scrape.py
```

Embed the posts:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/run_embed.py
```

The Streamlit search UI will return results once embedding is complete.

---

## CI/CD pipeline

Every push to `main`:

1. **test** — runs pytest with Postgres + Qdrant service containers
2. **build-and-deploy** (only on `main` push, after tests pass):
   - Builds Docker image → pushes to GHCR
   - SCPs `docker-compose.yml`, `docker-compose.prod.yml`, `nginx/default.conf.template` to server
   - SSHes in as `deploy` → `docker compose pull` + `up -d` + `alembic upgrade head`

Rollback: re-run any previous successful Actions workflow, or on the server:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull ghcr.io/pavelzeman/mm-forums-vector-db:<sha>
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

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
embeddings will have a per-token cost and require `OPENAI_API_KEY`.

---

## Re-running the pipeline

```bash
# Scrape new posts only (resumable)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/run_scrape.py

# Embed any unembedded posts
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/run_embed.py

# Query from CLI
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec streamlit python scripts/query.py "your search query"
```
