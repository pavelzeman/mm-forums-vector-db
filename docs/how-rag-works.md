# How RAG works

## What is RAG?

RAG stands for **Retrieval Augmented Generation**. It combines two things:

1. **Retrieval** — find the most relevant pieces of knowledge from a database
2. **Generation** — use a language model to synthesize those pieces into a coherent answer

Without RAG, a language model only knows what it was trained on — it may be outdated,
hallucinate facts, or not know Mattermost-specific details at all. With RAG, you give the
model fresh, specific context at query time, and it answers from that context only.

---

## How it works in this project

### Step 1: Embed the question
The user's question is converted to a vector using the same embedding model used to
embed all the forum posts. This captures the *semantic meaning* of the question.

### Step 2: Retrieve relevant posts
Qdrant searches for the forum posts whose vectors are closest to the question vector
(ANN — approximate nearest neighbour search). The top 8 posts are retrieved.
This happens in milliseconds regardless of how many posts are in the database.

### Step 3: Fetch full text
The Qdrant payload contains a 300-character preview of each post. That's too short for
useful context. The full post text is fetched from Postgres using the post IDs.

### Step 4: Build the prompt
The retrieved posts are formatted and inserted into the LLM's prompt as context:

```
System: You are a Mattermost support expert. Answer the user's question using
        ONLY the forum posts provided below. If the answer isn't in the posts, say so.

[Post 1 — "How to configure LDAP with SSO" by someuser]
We had the same issue. The key is to set the LDAP filter correctly in the
System Console under Authentication > AD/LDAP. Make sure your BaseDN...
(up to 1000 chars per post)

[Post 2 — "LDAP + Okta SSO setup guide" by otheruser]
...

User: How do I configure LDAP with SSO?
```

### Step 5: Generate the answer
The LLM reads the prompt and generates a coherent, synthesized answer. It is instructed
to answer only from the provided posts and to cite sources where relevant.

### Step 6: Display
The answer is shown prominently in the UI. Below it, the source forum posts are shown
as collapsible sections with links back to the original threads.

---

## What "transfer" means

There is no transfer between systems. Everything happens on the server:

```
User question
     │
     ▼
Embedding model (local, on server)
     │
     ▼
Qdrant (local, on server) — returns post IDs + metadata
     │
     ▼
Postgres (local, on server) — returns full post text
     │
     ▼
LLM prompt assembled in memory
     │
     ▼ (if using Ollama)
Ollama (local, on server) — generates answer
     │
     ▼
Answer displayed in browser
```

When using Ollama, **no data leaves your server**. The forum posts, the question, and
the generated answer all stay within your infrastructure.

When using OpenAI or Anthropic, the prompt (question + retrieved post text) is sent to
their API. The forum data in the prompt is not stored by these providers beyond the
request, but it does leave your server.

---

## Provider options

Configured via `LLM_PROVIDER` in `.env`. No code changes needed to switch.

| Provider | Sovereign | Quality | Latency | Cost |
|---|---|---|---|---|
| `ollama` | Yes — stays on server | Good (depends on model) | 5–60s on CPU | Free |
| `anthropic` | No — data sent to Anthropic | Excellent | 2–5s | ~$0.01–0.05/query |
| `openai` | No — data sent to OpenAI | Excellent | 2–5s | ~$0.01–0.05/query |

### Ollama hardware requirements

Ollama runs open-source models locally. Performance depends on available RAM and GPU:

| Model | RAM needed | CPU speed | GPU speed |
|---|---|---|---|
| Llama 3.1 8B | ~8 GB | ~2 tok/s | ~60 tok/s |
| Mistral 7B | ~8 GB | ~2 tok/s | ~60 tok/s |
| Qwen2.5 14B | ~16 GB | ~1 tok/s | ~40 tok/s |
| Llama 3.1 70B | ~48 GB | very slow | ~30 tok/s |

At ~2 tok/s on CPU, a 200-word answer takes ~2 minutes. Acceptable for async use.
A GPU server cuts that to ~10 seconds.

### Setting up Ollama

Ollama runs as a Docker service (already in `docker-compose.yml`). Pull a model once
after the stack is up:

```bash
docker compose exec ollama ollama pull llama3.1
```

Then set in `.env`:
```
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1
```

---

## Why not just use the LLM without retrieval?

A general-purpose LLM knows about Mattermost from its training data, but:

- Training data has a cutoff — recent forum discussions aren't included
- It may hallucinate specific configuration details
- It doesn't know about your users' specific real-world issues and solutions

RAG grounds the answers in actual forum content — real questions, real solutions,
posted by real Mattermost users and staff. The LLM's job is synthesis and clarity,
not recall.

---

## Prompt design

The system prompt instructs the model to:
1. Answer only from the provided posts (no hallucination)
2. Say explicitly if the posts don't contain enough information
3. Cite which post or author information comes from
4. Be specific and technical rather than vague

This makes answers verifiable — every claim in the answer can be traced to a source post.
