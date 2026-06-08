"""
Client for fetching lyrics from lrclib.net.
"""
import re
import requests


_LRC_TIMESTAMP_RE = re.compile(r'\[\d{2}:\d{2}\.\d{2,3}\]')


def fetch_lyrics(track_name: str, artist_name: str):
    """
    Fetch plain lyrics for a track from lrclib.net.

    Returns plainLyrics if available; falls back to syncedLyrics with timestamps
    stripped. Returns None on 404, non-200 status, or any exception.

    Args:
        track_name: Track title.
        artist_name: Artist name.

    Returns:
        Lyrics string or None.
    """
    try:
        response = requests.get(
            'https://lrclib.net/api/get',
            params={'track_name': track_name, 'artist_name': artist_name},
            timeout=5
        )

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            return None

        data = response.json()

        plain = data.get('plainLyrics')
        if plain:
            return plain

        synced = data.get('syncedLyrics')
        if synced:
            return _LRC_TIMESTAMP_RE.sub('', synced).strip()

        return None

    except Exception:
        return None
