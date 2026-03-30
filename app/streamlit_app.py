import streamlit as st
from qdrant_client import QdrantClient

from mm_forum.config import Settings
from mm_forum.db.store import get_session
from mm_forum.embedder.local import LocalEmbedder
from mm_forum.embedder.openai_embedder import OpenAIEmbedder
from mm_forum.vectordb.qdrant_store import QdrantStore

st.set_page_config(page_title="Mattermost Forum Search", layout="wide")

settings = Settings()


@st.cache_resource
def get_qdrant():
    return QdrantStore(url=settings.qdrant_url, collection=settings.qdrant_collection)


@st.cache_resource
def get_embedder():
    if settings.embedding_model == "openai":
        return OpenAIEmbedder(api_key=settings.openai_api_key)
    return LocalEmbedder(model_name=settings.local_model_name)


st.title("Mattermost Forum Search")
st.caption("Semantic search over Mattermost community forum posts")

query = st.text_input("Search", placeholder="e.g. how to configure LDAP with SSO")

col1, col2 = st.columns([1, 3])
with col1:
    top_k = st.slider("Results", min_value=3, max_value=20, value=10)

if query:
    with st.spinner("Searching..."):
        try:
            embedder = get_embedder()
            qdrant = get_qdrant()
            vector = embedder.embed([query])[0]
            results = qdrant.search(vector, limit=top_k)
        except Exception as e:
            st.error(f"Search failed: {e}")
            results = []

    if not results:
        st.info("No results found.")
    else:
        for r in results:
            payload = r.payload or {}
            title = payload.get("title") or payload.get("topic_title") or "Untitled"
            author = payload.get("username", "unknown")
            preview = payload.get("text_preview") or payload.get("cooked_text", "")
            score = r.score

            # Construct Discourse URL from topic_id + post_number
            topic_id = payload.get("topic_id")
            post_number = payload.get("post_number", 1)
            base = settings.forum_base_url.rstrip("/")
            url = f"{base}/t/{topic_id}/{post_number}" if topic_id else "#"

            with st.expander(f"**{title}** — score {score:.3f}"):
                st.markdown(f"**Author:** {author} | [Open post]({url})")
                st.markdown(preview[:800] + ("…" if len(preview) > 800 else ""))

st.divider()

with st.expander("Stats"):
    try:
        from sqlalchemy import text
        with get_session() as s:
            topic_count = s.execute(text("SELECT COUNT(*) FROM topics")).scalar()
            post_count = s.execute(text("SELECT COUNT(*) FROM posts")).scalar()
            embedded = s.execute(
                text("SELECT COUNT(*) FROM posts WHERE embedded = true")
            ).scalar()
        st.metric("Topics", topic_count)
        st.metric("Posts", post_count)
        st.metric("Embedded", embedded)
    except Exception as e:
        st.warning(f"Could not load stats: {e}")
