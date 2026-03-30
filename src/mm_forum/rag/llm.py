from __future__ import annotations

from typing import Protocol, runtime_checkable

from mm_forum.config import settings

_SYSTEM_PROMPT = """\
You are a Mattermost support expert. Answer the user's question using ONLY the forum \
posts provided below as context. Synthesize the information into a clear, direct answer.

Rules:
- Base your answer strictly on the provided posts. Do not add information not present in them.
- If the posts do not contain enough information to answer the question, say so clearly.
- Where relevant, mention which post or author the information comes from.
- Be concise but complete. Prefer specific technical details over vague generalities.
"""


def _build_context(context_posts: list[dict]) -> str:
    parts = []
    for i, post in enumerate(context_posts, 1):
        title = post.get("title", "Untitled")
        username = post.get("username", "unknown")
        text = (post.get("raw_text") or post.get("text_preview") or "").strip()
        text = text[:1000] + ("…" if len(text) > 1000 else "")
        parts.append(f"[Post {i} — \"{title}\" by {username}]\n{text}")
    return "\n\n".join(parts)


@runtime_checkable
class LLMClient(Protocol):
    def answer(self, question: str, context_posts: list[dict]) -> str: ...


class AnthropicClient:
    def __init__(self) -> None:
        import anthropic
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def answer(self, question: str, context_posts: list[dict]) -> str:
        context = _build_context(context_posts)
        message = self._client.messages.create(
            model=settings.llm_model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Forum posts:\n\n{context}\n\nQuestion: {question}",
                }
            ],
        )
        return message.content[0].text


class OpenAIClient:
    def __init__(self) -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=settings.openai_api_key)

    def answer(self, question: str, context_posts: list[dict]) -> str:
        context = _build_context(context_posts)
        response = self._client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Forum posts:\n\n{context}\n\nQuestion: {question}",
                },
            ],
            max_tokens=1024,
        )
        return response.choices[0].message.content


class OllamaClient:
    def __init__(self) -> None:
        from openai import OpenAI
        # Ollama exposes an OpenAI-compatible API
        self._client = OpenAI(base_url=settings.llm_base_url + "/v1", api_key="ollama")

    def answer(self, question: str, context_posts: list[dict]) -> str:
        context = _build_context(context_posts)
        response = self._client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Forum posts:\n\n{context}\n\nQuestion: {question}",
                },
            ],
            max_tokens=1024,
        )
        return response.choices[0].message.content


def get_llm_client() -> LLMClient:
    provider = settings.llm_provider
    if provider == "anthropic":
        return AnthropicClient()
    if provider == "openai":
        return OpenAIClient()
    if provider == "ollama":
        return OllamaClient()
    raise ValueError(f"Unknown LLM provider: {provider!r}. Choose: anthropic, openai, ollama")
