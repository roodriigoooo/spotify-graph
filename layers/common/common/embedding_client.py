"""
Client for generating text embeddings via HuggingFace Inference API.
Uses sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (768-dim, 50+ languages).
"""
import requests


_HF_URL = 'https://router.huggingface.co/hf-inference/models/sentence-transformers/paraphrase-multilingual-mpnet-base-v2/pipeline/feature-extraction'
_MAX_CHARS = 2000


def get_embeddings_batch(texts: list, api_key: str) -> list:
    """
    Get embedding vectors for multiple texts in a single API call.

    Args:
        texts: List of input strings (each truncated to 2000 chars).
        api_key: HuggingFace Inference API key.

    Returns:
        list of list[float], one per input. Empty list on any error.
    """
    try:
        truncated = [t[:_MAX_CHARS] for t in texts]
        response = requests.post(
            _HF_URL,
            headers={'Authorization': f'Bearer {api_key}'},
            json={'inputs': truncated},
            timeout=30
        )

        if response.status_code != 200:
            print(f"[embedding] HTTP {response.status_code}: {response.text[:300]}")
            return []

        result = response.json()
        print(f"[embedding] response type={type(result).__name__} preview={str(result)[:200]}")

        # Batched response: [[vec1...], [vec2...], ...]
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
            return [[float(v) for v in vec] for vec in result]

        return []

    except Exception as e:
        print(f"[embedding] exception: {e}")
        return []


def average_embeddings(vectors: list) -> list:
    """
    Compute element-wise average of a list of embedding vectors.

    Args:
        vectors: List of equal-length lists of numbers.

    Returns:
        Averaged vector as list[float].
    """
    if not vectors:
        return []

    dim = len(vectors[0])
    total = [0.0] * dim

    for vec in vectors:
        for i, val in enumerate(vec):
            total[i] += float(val)

    n = len(vectors)
    return [v / n for v in total]
