"""
archetypes — the landmark taste profiles that populate the graph even with zero friends.

The app is a *pairwise* taste graph: a lone user is one node and the whole point (similarity,
the facet breakdown, the honest layout) has nothing to compare against. Archetypes fix that
without faking anything. Each one is a recognizable persona defined by a **genre shape** —
real Spotify genre tags, the same strings the engine reads off a real user's artists — so the
genre facet (`_sparse_cosine` over genre distributions) scores you against it honestly.

Honesty rules these obey, by construction:
  - They are defined ONLY on signals they genuinely express. Right now that's the genre facet.
    They carry no `artistWeights`, so `score_pair` *drops* the artist facet for them (it would
    otherwise report a misleading 0% artist overlap). They carry no lyric embeddings, so the
    lyric facet drops too. The breakdown panel shows exactly the facet(s) that applied.
  - They flow through the *same* `build_profile` -> `score_pair` -> MDS pipeline as people, and
    land at engine-computed coordinates — not the hardcoded screen-corner anchors v1 had.
  - They live only in the `/graph` response. They are never written to Users / Friends /
    MusicProfiles, so the friend mechanism (search, requests, accept) literally cannot see them.

Node ids are prefixed `archetype:` so they can never collide with a real (uuid) userId, and so
`graph_core` can tag them `kind:"archetype"` for the UI.

Phase 2 (parked): give each archetype real per-track lyric embeddings (embed representative
lyrics offline via the same HF model), so the lyric/theme facet — the showcase — also applies.
Until then archetypes are genre-defined, which is honest and already enough to populate the map.
"""
from typing import Dict, List

ARCHETYPE_PREFIX = "archetype:"


# Each archetype: a slug, a display name, a one-line persona description (shown in the node
# card), and a genre weight vector. The genre strings are real Spotify artist-genre tags; the
# weights are relative (the adapter L1-normalizes them into a distribution).
_ARCHETYPES: List[Dict] = [
    {
        "slug": "indie",
        "name": "the indie purist",
        "description": "guitars, reverb, and feelings — lives in the 4-to-8k monthly-listener range.",
        "genres": {
            "indie rock": 1.0, "indie pop": 0.8, "art rock": 0.6, "indietronica": 0.5,
            "chamber pop": 0.4, "dream pop": 0.4, "permanent wave": 0.3, "modern rock": 0.3,
        },
    },
    {
        "slug": "pop",
        "name": "the pop maximalist",
        "description": "hooks first — the charts are a playlist, not a compromise.",
        "genres": {
            "pop": 1.0, "dance pop": 0.9, "electropop": 0.6, "pop rock": 0.5,
            "synthpop": 0.5, "post-teen pop": 0.4,
        },
    },
    {
        "slug": "hiphop",
        "name": "the hip-hop head",
        "description": "bars, beats, and producer credits — knows who sampled what.",
        "genres": {
            "hip hop": 1.0, "rap": 0.9, "trap": 0.7, "conscious hip hop": 0.5,
            "southern hip hop": 0.5, "melodic rap": 0.4,
        },
    },
    {
        "slug": "electronic",
        "name": "the rave architect",
        "description": "four-on-the-floor as a lifestyle — the drop is the chorus.",
        "genres": {
            "edm": 0.9, "house": 0.9, "techno": 0.8, "electro house": 0.6,
            "progressive house": 0.6, "deep house": 0.5, "trance": 0.4,
        },
    },
    {
        "slug": "soul",
        "name": "the jazz & soul digger",
        "description": "warmth, groove, and crate-dug rarities — a vinyl-shaped taste.",
        "genres": {
            "soul": 0.9, "neo soul": 0.8, "jazz": 0.8, "funk": 0.7,
            "r&b": 0.7, "motown": 0.4, "bebop": 0.3,
        },
    },
    {
        "slug": "metal",
        "name": "the heavy one",
        "description": "loud, fast, cathartic — the breakdown is the point.",
        "genres": {
            "metal": 0.9, "alternative metal": 0.8, "hard rock": 0.7,
            "metalcore": 0.6, "nu metal": 0.5, "hardcore": 0.4,
        },
    },
    {
        "slug": "folk",
        "name": "the songwriter's songwriter",
        "description": "lyrics over production — one voice, one guitar, no apologies.",
        "genres": {
            "folk": 0.9, "indie folk": 0.8, "singer-songwriter": 0.8,
            "americana": 0.6, "folk rock": 0.5, "chamber folk": 0.4,
        },
    },
    {
        "slug": "latin",
        "name": "the reggaetonero",
        "description": "perreo, dembow, and verano energy — the function in audio form.",
        "genres": {
            "reggaeton": 1.0, "urbano latino": 0.9, "latin": 0.7, "latin pop": 0.7,
            "trap latino": 0.6, "perreo": 0.5, "reggaeton colombiano": 0.4,
        },
    },
    {
        "slug": "global",
        "name": "the global pop omnivore",
        "description": "no borders on the playlist — k-pop, afrobeats, and chart-pop alike.",
        "genres": {
            "k-pop": 0.9, "pop": 0.7, "afrobeats": 0.7, "dance pop": 0.6,
            "j-pop": 0.5, "amapiano": 0.4, "afropop": 0.4,
        },
    },
]


def archetype_id(slug: str) -> str:
    return f"{ARCHETYPE_PREFIX}{slug}"


def is_archetype(user_id: str) -> bool:
    return isinstance(user_id, str) and user_id.startswith(ARCHETYPE_PREFIX)


def archetype_ids() -> List[str]:
    return [archetype_id(a["slug"]) for a in _ARCHETYPES]


def archetype_profile_records() -> Dict[str, Dict]:
    """
    userId -> a MusicProfiles-shaped record `build_profile` can consume. Genre-only: just a
    `genreVector`, which the adapter normalizes into the genre distribution.
    """
    return {
        archetype_id(a["slug"]): {
            "userId": archetype_id(a["slug"]),
            "genreVector": dict(a["genres"]),
        }
        for a in _ARCHETYPES
    }


def archetype_user_records() -> Dict[str, Dict]:
    """userId -> a Users-shaped record (display name + persona description for the node card)."""
    return {
        archetype_id(a["slug"]): {
            "userId": archetype_id(a["slug"]),
            "displayName": a["name"],
            "description": a["description"],
            "spotifyId": "",
        }
        for a in _ARCHETYPES
    }
