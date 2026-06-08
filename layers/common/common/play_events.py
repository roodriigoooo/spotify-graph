"""
play_events — turn Spotify "recently played" items into PlayEvents rows.

This is the write side of the continuous footprint (taste-engine v2): every play becomes one
DynamoDB row, later aggregated with a recency half-life rather than read as a top-N snapshot.
Pure stdlib so it's trivially testable; the handler does the Spotify fetch + the batch write.

Row shape (PlayEventsTable: userId HASH, sk RANGE):
    userId    : the listener
    sk        : "<playedAtEpochMs:013d>#<trackId>"  -> newest-first, unique per play
    trackId   : Spotify track id
    artistIds : [artist id, ...]   (credits every artist on the track)
    playedAt  : unix seconds (int)
    ttl       : unix seconds when the row self-expires (bounds storage)
    + a little context for cards (trackName, artistName)
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

DEFAULT_TTL_DAYS = 180


def parse_played_at(iso: str) -> Optional[float]:
    """Parse Spotify's ISO-8601 played_at ('2024-01-02T03:04:05.678Z') to unix seconds."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:           # naive timestamp -> assume UTC
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def to_play_events(
    recently_played_items: Sequence[Dict],
    user_id: str,
    now_ts: Optional[float] = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> List[Dict]:
    """
    Build PlayEvents rows from a Spotify recently-played `items` list.

    Skips items without a track id or a parseable timestamp, and de-duplicates by sort key
    (Spotify can repeat the boundary item across pages). Returns rows ready for batch write.
    """
    if not user_id or not recently_played_items:
        return []
    if now_ts is None:
        import time
        now_ts = time.time()
    ttl = int(now_ts + ttl_days * 86400)

    rows: Dict[str, Dict] = {}
    for item in recently_played_items:
        track = (item or {}).get("track") or {}
        track_id = track.get("id")
        played_at = parse_played_at(item.get("played_at", ""))
        if not track_id or played_at is None:
            continue

        artists = track.get("artists") or []
        artist_ids = [a.get("id") for a in artists if a.get("id")]
        played_ms = int(played_at * 1000)
        sk = f"{played_ms:013d}#{track_id}"

        rows[sk] = {
            "userId": user_id,
            "sk": sk,
            "trackId": track_id,
            "trackName": track.get("name", ""),
            "artistIds": artist_ids,
            "artistName": (artists[0].get("name", "") if artists else ""),
            "playedAt": int(played_at),
            "ttl": ttl,
        }
    return list(rows.values())
