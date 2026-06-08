"""
adapter — turn what's in DynamoDB into what the engine speaks.

The store holds two generations of data:

  - the v1 snapshot profile (``topArtists`` / ``followedArtists`` / ``genreVector`` and the
    old averaged ``lyricVector``), and
  - the v2 continuous footprint (``PlayEvents`` rows + per-track lyric embeddings cached in
    ``TrackEmbeddings``).

``build_profile`` folds whichever of those exist into a single normalized
``UserTasteProfile`` the rest of the engine consumes. It prefers the richer v2 signals when
present and falls back to the snapshot so the graph keeps working mid-migration. Pure stdlib
— it runs on the Lambda request path. The only transform it applies is whitening (cheap,
parameter-driven); heavy fitting stays offline.

Everything here is defensive about types: DynamoDB hands numbers back as ``Decimal`` and any
field may be missing, so we coerce hard and never raise on a malformed row.
"""
from typing import Dict, List, Mapping, Optional, Sequence

from .aggregation import recency_weight, normalize, genre_distribution, DEFAULT_HALF_LIFE_DAYS
from .distributions import fit_diag_gaussian
from .facets import UserTasteProfile
from .params import EngineParams

# Snapshot fallback weights (mirror the v1 engine so behaviour is continuous pre-migration).
RANGE_WEIGHTS = {"long_term": 3.0, "medium_term": 2.0, "short_term": 1.0}
FOLLOWED_WEIGHT = 1.0


# ─── coercion helpers (DynamoDB Decimal / missing-field safe) ─────────────────
def _f(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _vec(seq) -> List[float]:
    if not seq:
        return []
    return [_f(x) for x in seq]


def _genre_map(raw: Optional[Mapping]) -> Dict[str, float]:
    if not raw:
        return {}
    return {str(k): _f(v) for k, v in raw.items()}


# ─── artist facet inputs ──────────────────────────────────────────────────────
def _artist_weights_from_record(record: Mapping) -> Dict[str, float]:
    """Range-weighted top artists + followed artists — the snapshot fallback."""
    counts: Dict[str, float] = {}
    top = record.get("topArtists") or {}
    if isinstance(top, Mapping):
        for range_name, artists in top.items():
            w = RANGE_WEIGHTS.get(range_name, 1.0)
            for a in artists or []:
                aid = a.get("id") or a.get("artistId")
                if aid:
                    counts[aid] = counts.get(aid, 0.0) + w
    for a in record.get("followedArtists") or []:
        aid = a.get("id") or a.get("artistId")
        if aid:
            counts[aid] = counts.get(aid, 0.0) + FOLLOWED_WEIGHT
    return counts


def _artist_genres_from_record(record: Mapping) -> Dict[str, List[str]]:
    """artistId -> [genres], harvested from whatever artist objects the record carries."""
    out: Dict[str, List[str]] = {}
    top = record.get("topArtists") or {}
    if isinstance(top, Mapping):
        for artists in top.values():
            for a in artists or []:
                aid = a.get("id") or a.get("artistId")
                if aid and a.get("genres"):
                    out[aid] = [str(g) for g in a["genres"]]
    return out


def _artist_weights_from_events(
    events: Sequence[Mapping], now_ts: float, half_life_days: float
) -> Dict[str, float]:
    """Recency-weighted artist plays. Each event credits every artist on the track."""
    out: Dict[str, float] = {}
    for ev in events:
        artist_ids = ev.get("artistIds") or ([ev["artistId"]] if ev.get("artistId") else [])
        if not artist_ids:
            continue
        w = recency_weight(_f(ev.get("playedAt", now_ts), now_ts), now_ts, half_life_days)
        for aid in artist_ids:
            out[aid] = out.get(aid, 0.0) + w
    return out


def _track_weights_from_events(
    events: Sequence[Mapping], now_ts: float, half_life_days: float
) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for ev in events:
        tid = ev.get("trackId")
        if not tid:
            continue
        w = recency_weight(_f(ev.get("playedAt", now_ts), now_ts), now_ts, half_life_days)
        out[tid] = out.get(tid, 0.0) + w
    return out


# ─── the one public call ──────────────────────────────────────────────────────
def build_profile(
    record: Optional[Mapping] = None,
    play_events: Optional[Sequence[Mapping]] = None,
    track_embeddings: Optional[Sequence[Sequence[float]]] = None,
    track_ids: Optional[Sequence[str]] = None,
    params: Optional[EngineParams] = None,
    now_ts: Optional[float] = None,
) -> UserTasteProfile:
    """
    Fold the stored data for one user into a ``UserTasteProfile``.

    Args:
        record: the ``MusicProfiles`` item (may be empty / None).
        play_events: ``PlayEvents`` rows (each {trackId, artistIds, playedAt}). When present,
            artist + genre + track weights are recency-weighted from these; otherwise the
            v1 snapshot in ``record`` is used.
        track_embeddings: raw per-track lyric embeddings (parallel to ``track_ids``). Falls
            back to ``record['trackEmbeddings']``. Whitened here via ``params.whitening``.
        track_ids: ids parallel to ``track_embeddings``, used to weight each track by recency
            when ``play_events`` are available (else uniform weight).
        params: engine params (whitening transform + half-life). Defaults are safe.
        now_ts: reference "now" in unix seconds (defaults to wall clock).

    Returns:
        A ``UserTasteProfile``. Missing signals simply yield empty fields, which the facets
        handle by dropping themselves from the blend.
    """
    record = record or {}
    params = params or EngineParams()
    if now_ts is None:
        import time
        now_ts = time.time()
    half_life = params.half_life_days or DEFAULT_HALF_LIFE_DAYS
    events = list(play_events or [])

    user_id = str(record.get("userId", ""))

    # ── artist facet ──
    if events:
        artist_weights = _artist_weights_from_events(events, now_ts, half_life)
    else:
        artist_weights = _artist_weights_from_record(record)

    # ── genre facet ──
    artist_genres = _artist_genres_from_record(record)
    if events and artist_genres:
        genre_dist = genre_distribution(artist_weights, artist_genres)
    else:
        genre_dist = normalize(_genre_map(record.get("genreVector")))

    # ── lyric facet: per-track whitened embeddings ──
    raw_embeddings = track_embeddings
    if raw_embeddings is None:
        raw_embeddings = record.get("trackEmbeddings")
    if track_ids is None:
        track_ids = record.get("trackIds")

    whitened: List[List[float]] = []
    weights: List[float] = []
    if raw_embeddings:
        track_recency = _track_weights_from_events(events, now_ts, half_life) if events else {}
        record_weights = _vec(record.get("trackWeights")) if record.get("trackWeights") else []
        for i, emb in enumerate(raw_embeddings):
            vec = _vec(emb)
            if not vec:
                continue
            whitened.append(params.whitening.apply(vec))
            if track_ids and i < len(track_ids) and track_ids[i] in track_recency:
                weights.append(track_recency[track_ids[i]])
            elif i < len(record_weights):
                weights.append(record_weights[i])
            else:
                weights.append(1.0)

    gaussian = fit_diag_gaussian(whitened) if whitened else None

    return UserTasteProfile(
        user_id=user_id,
        artist_weights=artist_weights,
        genre_dist=genre_dist,
        track_embeddings=whitened,
        track_weights=weights,
        gaussian=gaussian,
    )
