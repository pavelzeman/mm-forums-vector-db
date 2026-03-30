# No Over-Engineering: A Workflow Guide for Early-Stage Projects

A pattern that emerged while building `mm-forums-vector-db` — a semantic search tool
over the Mattermost community forum. The core lesson: match your infrastructure
complexity to your project's maturity. Don't build for scale you don't have yet.

---

## The Over-Engineered Starting Point

The project launched with a "professional" CI/CD pipeline on day one:

- GitHub Actions builds a Docker image on every push to `main`
- Image pushed to GitHub Container Registry (GHCR)
- Deploy job SSHes into the server, pulls the new image, restarts containers

This sounds clean. In practice, it was a grind:

- Every code change triggered a multi-minute GitHub Actions run
- The Python image with `sentence-transformers` + PyTorch is ~1.2 GB
- Even with layer caching, full rebuilds in CI took 4–8 minutes cold
- Debugging a failed deploy meant reading CI logs, fixing, pushing, waiting again
- The feedback loop from "write code" to "see it running" was 10+ minutes

The pipeline was solving a problem the project didn't have yet: reliable automated
deploys for a stable codebase. Instead it was adding friction to a codebase that
changed every hour.

**Commit that reflects the wrong path:**
```
8c8bc27 Add Dockerfile, Streamlit app, and GitHub Actions CI/CD deploy pipeline
```

---

## The Shift: Build on the Server, Not in CI

The fix was a one-commit simplification:

```
ef89eb4 Simplify deployment: build on server, remove CI/CD pipeline

Too early for a full registry/CI deploy pipeline on a test VPS.
Server builds the image locally from source via docker compose up --build.
CI/CD deploy job can be added properly when moving to AWS.
```

The new deploy workflow:

```bash
# On the Hetzner VPS
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

That's it. No registry, no GitHub Actions deploy job, no waiting for remote CI.

The feedback loop collapsed from 10+ minutes to under 2 minutes for source-only
changes — because Docker layer caching on the server meant only the application
code layer was rebuilt (~30 seconds), not PyTorch and all dependencies again.

---

## Why This Works: Docker Layer Caching on the Server

The Dockerfile is structured so heavy layers come first and change rarely:

```
Layer 1: system packages (gcc, libpq-dev, etc.)      — changes rarely
Layer 2: PyTorch CPU-only wheel                       — changes rarely
Layer 3: remaining Python dependencies                — changes when pyproject.toml changes
Layer 4: source code (src/, app/, scripts/)           — changes every iteration
```

When you `git pull` and run `--build`, Docker reuses layers 1–3 from cache and only
rebuilds layer 4. On a server with a warm cache, that's ~30 seconds per deploy.

In CI, the cache is cold (or partially restored from cache artifacts, which is fiddly).
Every run risks a full rebuild. On the server, the cache is always warm.

---

## The Infrastructure That Actually Worked

**Server:** Hetzner VPS (CX22, ~€4/month). Provisioned with a `cloud-init.yml` that
installs Docker, creates a non-root `deploy` user, and configures UFW. No app code
starts automatically — the first deploy is a manual `git clone` + `docker compose up`.

**Deploy process during active development:**
1. Write code locally, run tests locally
2. `git push`
3. SSH to server, `git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
4. Check `docker compose logs -f streamlit` to verify

**CI (GitHub Actions):** Kept for testing only — runs `pytest` against ephemeral
Postgres + Qdrant service containers. No build, no push, no deploy. Fast, reliable,
and actually useful as a gating signal.

```yaml
# ci.yml — tests only, no deploy job
# TODO: add build-and-deploy job when moving to AWS
```

This separation is intentional: CI validates correctness; deployment is a manual
human decision while the project is still being shaped.

---

## The Hetzner + `git pull` Pattern in Practice

The pattern treats the server like a slightly more permanent local machine:

- No image registry to manage
- No deploy secrets to rotate
- No CI runner timeouts to fight
- Rollback = `git checkout <previous-commit> && docker compose up --build`
- The server is the source of truth for what's running; `git log` tells you exactly

This works because:
1. It's one server, not a fleet
2. Downtime during `up --build` is acceptable at this stage
3. You can `docker compose logs` and `docker exec` directly — no abstraction layers

---

## When to Add CI/CD Back

The server-side `git pull` workflow has a natural end of life. Add a proper CI/CD
pipeline when:

- The codebase is **stable** — you're shipping features, not rewriting architecture weekly
- You have **multiple environments** (staging, prod) that need to stay in sync
- You're moving to **managed infrastructure** (AWS ECS, Fly.io, etc.) where
  the deploy mechanism is fundamentally different from `docker compose up`
- You need **zero-downtime deploys** (blue/green, rolling)
- More than one person is deploying

In this project, the trigger was planned migration from Hetzner to AWS. The CI workflow
already has a placeholder comment marking where the build-and-deploy job goes.

Don't add it earlier than you need it.

---

## Key Principles

**1. Match infrastructure complexity to project maturity.**
A test VPS with `git pull` is correct infrastructure for an exploratory project.
A full CI/CD pipeline is correct infrastructure for a stable, multi-person project.
Neither is universally right.

**2. Optimize the feedback loop above everything else.**
10-minute deploy cycles compound into hours of wasted time over a week of iteration.
The single highest-leverage action early on is making deploys fast and frictionless.

**3. Keep CI for what it's good at: automated testing.**
Tests in CI catch regressions before they reach the server. Deploy automation in CI
is overhead until the project is ready for it. These are separable concerns.

**4. Use Docker layer ordering to get fast iterative builds.**
Heavy dependencies first, application source last. On a server with a warm cache,
source-only rebuilds take seconds regardless of image size.

**5. Simple infra is observable infra.**
`docker compose logs`, `docker exec`, `git log` on the server give you a complete
picture of what's running and why. The moment you add a registry and a deploy pipeline,
you add layers of indirection that make failures harder to diagnose.

---

## Summary

| Phase | Deploy method | Feedback loop | When to use |
|---|---|---|---|
| Exploration / MVP | `git pull` + `docker compose up --build` on VPS | ~1–2 min | Unstable, single-dev, changing frequently |
| Growth | CI builds image, pushes to registry, deploys | ~5–10 min | Stable contracts, multiple devs |
| Scale | Managed infra (ECS, GKE), blue/green | Varies | Production traffic, zero-downtime requirement |

Start at the top. Move down only when the current level becomes the bottleneck.
