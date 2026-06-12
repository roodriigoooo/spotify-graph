"""
Similarity computation functions for taste and lyric modes.
Pure Python — no numpy required.
"""
import math


RANGE_WEIGHTS = {'long_term': 3, 'medium_term': 2, 'short_term': 1}
FOLLOWED_WEIGHT = 1


def compute_genre_vector(top_artists_by_range: dict) -> dict:
    """
    Build a normalized genre frequency vector from top artists across time ranges.

    Args:
        top_artists_by_range: {'long_term': [...], 'medium_term': [...], 'short_term': [...]}
            Each list contains artist objects with a 'genres' list.

    Returns:
        Normalized dict mapping genre -> weight float.
    """
    counts = {}
    for range_name, artists in top_artists_by_range.items():
        weight = RANGE_WEIGHTS.get(range_name, 1)
        for artist in artists:
            for genre in artist.get('genres', []):
                counts[genre] = counts.get(genre, 0) + weight

    total = sum(counts.values())
    if total == 0:
        return {}
    return {genre: count / total for genre, count in counts.items()}


def cosine_similarity(vec_a: dict, vec_b: dict) -> float:
    """
    Cosine similarity between two sparse vectors represented as dicts.

    Args:
        vec_a: dict mapping key -> float
        vec_b: dict mapping key -> float

    Returns:
        Float in [0.0, 1.0], or 0.0 if either vector is zero.
    """
    dot = sum(float(vec_a[k]) * float(vec_b[k]) for k in vec_a if k in vec_b)
    mag_a = math.sqrt(sum(float(v) ** 2 for v in vec_a.values()))
    mag_b = math.sqrt(sum(float(v) ** 2 for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _build_artist_multiset(profile: dict) -> dict:
    """
    Build weighted artist multiset from a music profile.
    Uses top artists across all ranges (with range weights) plus followed artists (weight=1).
    """
    counts = {}
    top_artists = profile.get('topArtists', {})
    for range_name, artists in top_artists.items():
        weight = RANGE_WEIGHTS.get(range_name, 1)
        for artist in artists:
            artist_id = artist.get('id') or artist.get('artistId')
            if artist_id:
                counts[artist_id] = counts.get(artist_id, 0) + weight

    for artist in profile.get('followedArtists', []):
        artist_id = artist.get('id') or artist.get('artistId')
        if artist_id:
            counts[artist_id] = counts.get(artist_id, 0) + FOLLOWED_WEIGHT

    return counts


def _jaccard_weighted(multiset_a: dict, multiset_b: dict) -> float:
    """Weighted Jaccard similarity between two multisets."""
    keys = set(multiset_a) | set(multiset_b)
    if not keys:
        return 0.0
    intersection = sum(min(multiset_a.get(k, 0), multiset_b.get(k, 0)) for k in keys)
    union = sum(max(multiset_a.get(k, 0), multiset_b.get(k, 0)) for k in keys)
    if union == 0:
        return 0.0
    return intersection / union


def taste_similarity(profile_a: dict, profile_b: dict) -> float:
    """
    Taste similarity: 0.5 * artist_jaccard + 0.5 * genre_cosine.

    Args:
        profile_a: Music profile dict with topArtists, followedArtists, genreVector.
        profile_b: Same structure.

    Returns:
        Float in [0.0, 1.0].
    """
    multiset_a = _build_artist_multiset(profile_a)
    multiset_b = _build_artist_multiset(profile_b)
    artist_score = _jaccard_weighted(multiset_a, multiset_b)

    genre_a = {k: float(v) for k, v in profile_a.get('genreVector', {}).items()}
    genre_b = {k: float(v) for k, v in profile_b.get('genreVector', {}).items()}
    genre_score = cosine_similarity(genre_a, genre_b)

    return 0.5 * artist_score + 0.5 * genre_score


def lyric_similarity(profile_a: dict, profile_b: dict) -> float:
    """
    Lyric similarity: cosine on averaged lyric embedding vectors.

    Args:
        profile_a: Profile dict with optional 'lyricVector' list[float].
        profile_b: Same structure.

    Returns:
        Float in [0.0, 1.0], or 0.0 if either profile is missing its lyricVector.
    """
    vec_a = profile_a.get('lyricVector')
    vec_b = profile_b.get('lyricVector')
    if not vec_a or not vec_b:
        return 0.0

    vec_a = [float(v) for v in vec_a]
    vec_b = [float(v) for v in vec_b]

    # Use indexed dict for cosine_similarity helper
    dict_a = {i: v for i, v in enumerate(vec_a)}
    dict_b = {i: v for i, v in enumerate(vec_b)}
    return cosine_similarity(dict_a, dict_b)
