"""Unit tests for embedders — library imports are mocked for speed."""
from unittest.mock import MagicMock, patch


def test_local_embedder_embed_returns_correct_shape():
    mock_model = MagicMock()
    mock_model.encode.return_value = [[0.1] * 384, [0.2] * 384]
    mock_model.get_sentence_embedding_dimension.return_value = 384

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
        from mm_forum.embedder.local import LocalEmbedder
        embedder = LocalEmbedder(model_name="test-model")
        result = embedder.embed(["hello", "world"])

    assert len(result) == 2
    assert len(result[0]) == 384
    assert embedder.dimension == 384
    assert embedder.model_name == "test-model"


def test_local_embedder_empty_input():
    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 384

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
        from mm_forum.embedder.local import LocalEmbedder
        embedder = LocalEmbedder(model_name="test-model")
        result = embedder.embed([])

    assert result == []
    mock_model.encode.assert_not_called()


def test_openai_embedder_embed():
    mock_openai_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(embedding=[0.5] * 1536),
        MagicMock(embedding=[0.6] * 1536),
    ]
    mock_openai_client.embeddings.create.return_value = mock_response

    with patch("openai.OpenAI", return_value=mock_openai_client):
        from mm_forum.embedder.openai_embedder import OpenAIEmbedder
        embedder = OpenAIEmbedder(model="text-embedding-3-small")
        result = embedder.embed(["hello", "world"])

    assert len(result) == 2
    assert len(result[0]) == 1536
    assert embedder.dimension == 1536


def test_embedder_protocol_compliance():
    """Verify that LocalEmbedder satisfies the Embedder protocol."""
    from mm_forum.embedder.base import Embedder

    mock_model = MagicMock()
    mock_model.encode.return_value = [[0.1] * 384]
    mock_model.get_sentence_embedding_dimension.return_value = 384

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
        from mm_forum.embedder.local import LocalEmbedder
        embedder = LocalEmbedder(model_name="test")

    assert isinstance(embedder, Embedder)
