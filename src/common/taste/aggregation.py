"""
Continuous footprint — recency-weighted aggregation of play history.

The whole point of v2: stop treating a user as a snapshot of their top-N. Instead,
accumulate *plays over time* and weight each play by how recent it is, with an
exponential half-life. A play heard today counts fully; one heard `half_life_days`
ago counts half; older fades smoothly toward zero.

    weight(play) = 0.5 ** (age_days / half_life_days)

This is what makes the representation "continuous and less snapshot-y". Pure stdlib so
it runs in Lambda and ports to the WASM kernel.
"""
from typing import Dict, List, Mapping, Sequence

SECONDS_PER_DAY = 86400.0
DEFAULT_HALF_LIFE_DAYS = 30.0


def recency_weight(played_at: float, now_ts: float, half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    """Exponential-decay weight for a single play. Future timestamps are clamped to now."""
    age_days = max(0.0, (now_ts - played_at) / SECONDS_PER_DAY)
    return 0.5 ** (age_days / half_life_days)


def recency_weighted_counts(
    events: Sequence[Mapping],
    now_ts: float,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    key: str = "itemId",
    ts_key: str = "playedAt",
) -> Dict[str, float]:
    """
    Collapse a stream of play events into a recency-weighted multiset.

    Args:
        events: iterable of dicts each carrying an item id and a unix timestamp.
        now_ts: reference "now" (unix seconds).
        half_life_days: decay half-life.
        key: event field holding the item id (e.g. trackId / artistId).
        ts_key: event field holding the play timestamp.

    Returns:
        dict mapping item id -> summed recency weight.
    """
    out: Dict[str, float] = {}
    for ev in events:
        item = ev.get(key)
        if item is None:
            continue
        w = recency_weight(float(ev.get(ts_key, now_ts)), now_ts, half_life_days)
        out[item] = out.get(item, 0.0) + w
    return out


def normalize(weights: Mapping[str, float]) -> Dict[str, float]:
    """L1-normalize a weight dict into a distribution that sums to 1 (empty -> {})."""
    total = sum(weights.values())
    if total <= 0.0:
        return {}
    return {k: v / total for k, v in weights.items()}


def genre_distribution(
    artist_weights: Mapping[str, float],
    artist_genres: Mapping[str, Sequence[str]],
) -> Dict[str, float]:
    """
    Build a normalized genre distribution from recency-weighted artist plays.

    Each artist contributes its recency weight, split evenly across its genres so that
    prolific-genre artists don't double-count. The result sums to 1.
    """
    counts: Dict[str, float] = {}
    for artist_id, w in artist_weights.items():
        genres = artist_genres.get(artist_id) or []
        if not genres:
            continue
        share = w / len(genres)
        for g in genres:
            counts[g] = counts.get(g, 0.0) + share
    return normalize(counts)


def top_items(weights: Mapping[str, float], n: int = 10) -> List[str]:
    """Return the ids of the n highest-weighted items (for previews / cards)."""
    return [k for k, _ in sorted(weights.items(), key=lambda kv: kv[1], reverse=True)[:n]]
