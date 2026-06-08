#!/usr/bin/env python3
"""
make_figures.py — regenerate the paper-like figures used in the README.

Runs the real taste engine on synthetic listening data and emits hand-rolled SVGs
(no matplotlib) into docs/figures/. SVG keeps them crisp, dependency-free, diff-able, and
on-brand with the terminal/mono aesthetic. These are *documentation* — the actual app UI
stays abstracted; here we lift the lid on the representation.

    python3 scripts/make_figures.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "common")))

from taste import UserTasteProfile, EngineParams, score_pair, recency_weight  # noqa: E402
from taste.fit import fit_whitening  # noqa: E402
from taste.setmetric import transport_plan, cosine_cost_matrix  # noqa: E402
from taste.linalg import cosine  # noqa: E402

FIGDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "figures"))

BG = "#0a0e0a"
PANEL = "#0e140e"
GREEN = "#00FF41"
INK = "#c9d1c9"
MUTED = "#5a635a"
GRID = "#1c241c"
AMBER = "#d9a441"
BLUE = "#8AB4F8"
FONT = "'JetBrains Mono','SF Mono',ui-monospace,monospace"


# ─── tiny SVG builder ────────────────────────────────────────────────────────
class Svg:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" font-family="{FONT}">'
        ]
        self.rect(0, 0, w, h, BG, 1)

    def rect(self, x, y, w, h, fill, opacity=1.0, rx=0):
        self.parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                          f'rx="{rx}" fill="{fill}" fill-opacity="{opacity:.3f}"/>')

    def line(self, x1, y1, x2, y2, stroke, w=1.0, opacity=1.0, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                          f'stroke="{stroke}" stroke-width="{w}" stroke-opacity="{opacity:.3f}"{d}/>')

    def text(self, x, y, s, size=12, fill=INK, anchor="start", weight=400, opacity=1.0, spacing=None):
        ls = f' letter-spacing="{spacing}"' if spacing else ""
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
                          f'fill-opacity="{opacity:.3f}" text-anchor="{anchor}" '
                          f'font-weight="{weight}"{ls}>{_esc(s)}</text>')

    def circle(self, cx, cy, r, fill, opacity=1.0, stroke=None, sw=1.0):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" '
                          f'fill-opacity="{opacity:.3f}"{st}/>')

    def polyline(self, pts, stroke, w=2.0, opacity=1.0):
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.parts.append(f'<polyline points="{p}" fill="none" stroke="{stroke}" '
                          f'stroke-width="{w}" stroke-opacity="{opacity:.3f}"/>')

    def save(self, name):
        self.parts.append("</svg>")
        os.makedirs(FIGDIR, exist_ok=True)
        path = os.path.join(FIGDIR, name)
        with open(path, "w") as f:
            f.write("\n".join(self.parts))
        return path


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ─── synthetic listening population ──────────────────────────────────────────
def population(seed=7, n_users=44, tracks=14, dim=24):
    """Each user = a cloud of track embeddings sharing a strong anisotropic common direction."""
    rng = np.random.default_rng(seed)
    common = np.zeros(dim); common[0] = 1.0
    users, themes = [], []
    for _ in range(n_users):
        theme = rng.normal(size=dim); theme[0] = 0.0; theme /= np.linalg.norm(theme)
        cloud = [rng.normal(8.0, 3.0) * common + theme + 0.15 * rng.normal(size=dim)
                 for _ in range(tracks)]
        users.append(np.array(cloud)); themes.append(theme)
    return users, np.array(themes)


def _pairwise(centroids):
    n = len(centroids)
    return [cosine(centroids[i].tolist(), centroids[j].tolist())
            for i in range(n) for j in range(i + 1, n)]


# ─── figure 1 — anisotropy collapse ──────────────────────────────────────────
def fig_anisotropy():
    users, _ = population()
    raw = _pairwise([u.mean(axis=0) for u in users])
    wp = fit_whitening(np.vstack(users).tolist(), remove_top=1)  # all-but-the-top
    white = _pairwise([np.mean([wp.apply(t) for t in u.tolist()], axis=0) for u in users])

    W, H = 720, 360
    L, R, T, B = 70, 30, 56, 64
    s = Svg(W, H)
    s.text(L, 30, "anisotropy collapse", 16, INK, weight=700)
    s.text(L, 47, "pairwise cosine over 44 users — averaged (raw) vs all-but-the-top whitened",
           11, MUTED)

    lo, hi, bins = -0.4, 1.0, 30
    edges = np.linspace(lo, hi, bins + 1)
    hraw, _ = np.histogram(raw, bins=edges)
    hwht, _ = np.histogram(white, bins=edges)
    ymax = max(hraw.max(), hwht.max()) * 1.1

    def px(v): return L + (v - lo) / (hi - lo) * (W - L - R)
    def py(c): return (H - B) - c / ymax * (H - B - T)

    for gx in np.linspace(lo, hi, 8):
        s.line(px(gx), T, px(gx), H - B, GRID, 1)
        s.text(px(gx), H - B + 16, f"{gx:.1f}", 10, MUTED, "middle")
    s.line(L, H - B, W - R, H - B, MUTED, 1)
    s.text((L + W - R) / 2, H - 12, "cosine similarity", 11, MUTED, "middle")

    bw = (W - L - R) / bins
    for i in range(bins):
        if hraw[i] > 0:
            s.rect(px(edges[i]) + 1, py(hraw[i]), bw - 1, (H - B) - py(hraw[i]), GREEN, 0.32)
    for i in range(bins):
        if hwht[i] > 0:
            s.rect(px(edges[i]) + 1, py(hwht[i]), bw - 1, (H - B) - py(hwht[i]), AMBER, 0.85)

    s.rect(W - R - 196, T + 4, 10, 10, GREEN, 0.32)
    s.text(W - R - 180, T + 13, "raw (averaged) — collapsed", 11, INK)
    s.rect(W - R - 196, T + 22, 10, 10, AMBER, 0.85)
    s.text(W - R - 180, T + 31, "whitened — spread restored", 11, INK)
    return s.save("anisotropy_collapse.svg")


# ─── figure 2 — recency decay ────────────────────────────────────────────────
def fig_recency():
    W, H = 720, 300
    L, R, T, B = 64, 30, 52, 56
    s = Svg(W, H)
    s.text(L, 30, "recency-weighted footprint", 16, INK, weight=700)
    s.text(L, 47, "every play decays with a 30-day half-life — continuous, not a snapshot", 11, MUTED)

    half_life = 30.0
    days = np.linspace(0, 120, 200)
    w = [recency_weight(1.0 - d * 86400.0, 1.0, half_life) for d in days]

    def px(d): return L + d / 120.0 * (W - L - R)
    def py(v): return (H - B) - v * (H - B - T)

    for gv in [0, 0.25, 0.5, 0.75, 1.0]:
        s.line(L, py(gv), W - R, py(gv), GRID, 1)
        s.text(L - 8, py(gv) + 3, f"{gv:.2f}", 10, MUTED, "end")
    for gd in [0, 30, 60, 90, 120]:
        s.text(px(gd), H - B + 16, f"{gd}d", 10, MUTED, "middle")

    s.polyline([(px(d), py(v)) for d, v in zip(days, w)], GREEN, 2.4)
    s.line(px(half_life), py(0), px(half_life), py(0.5), GREEN, 1, 0.5, "3 3")
    s.line(L, py(0.5), px(half_life), py(0.5), GREEN, 1, 0.5, "3 3")
    s.circle(px(half_life), py(0.5), 3.2, GREEN)
    s.text(px(half_life) + 8, py(0.5) - 8, "half-life = 30d → weight 0.5", 11, GREEN)
    s.text((L + W - R) / 2, H - 12, "age of play", 11, MUTED, "middle")
    return s.save("recency_decay.svg")


# ─── figure 3 — facet breakdown (comparative imagery) ────────────────────────
def fig_facets():
    a = UserTasteProfile(
        user_id="you",
        artist_weights={"bon_iver": 3, "phoebe": 2, "big_thief": 2, "alex_g": 1},
        genre_dist={"indie folk": 0.5, "slowcore": 0.3, "bedroom pop": 0.2},
        track_embeddings=[[1, 0, 0, 0], [0.9, 0.2, 0, 0], [0.8, 0, 0.3, 0]],
        track_weights=[3, 2, 1],
    )
    b = UserTasteProfile(
        user_id="sam",
        artist_weights={"phoebe": 2, "big_thief": 3, "sufjan": 2, "alex_g": 1},
        genre_dist={"indie folk": 0.4, "slowcore": 0.2, "chamber pop": 0.4},
        track_embeddings=[[0.85, 0.1, 0, 0], [0.7, 0.3, 0.2, 0], [0.6, 0, 0.5, 0]],
        track_weights=[2, 2, 2],
    )
    r = score_pair(a, b, EngineParams())

    W, H = 560, 320
    L = 40
    s = Svg(W, H)
    s.rect(16, 16, W - 32, H - 32, PANEL, 1, rx=4)
    s.line(16, 58, W - 16, 58, GRID, 1)
    s.text(L, 44, "echo · you ✕ sam", 15, INK, weight=700)
    s.text(W - L, 44, f"{round(r['similarity'] * 100)}% match", 15, GREEN, "end", 700)

    facets = [("artists", "artist"), ("genres", "genre"), ("themes", "lyric")]
    y = 96
    barL, barW = L + 86, 300
    for label, key in facets:
        val = r["facets"].get(key, 0.0)
        wgt = r["weights"].get(key, 0.0)
        s.text(L, y + 4, label, 12, INK)
        s.rect(barL, y - 9, barW, 14, GRID, 1, rx=2)
        s.rect(barL, y - 9, barW * val, 14, GREEN, 0.85, rx=2)
        s.text(barL + barW + 10, y + 4, f"{val:.2f}", 12, INK, "start", 600)
        s.text(barL, y + 22, f"weight {wgt:.2f}", 9, MUTED)
        y += 52

    s.line(16, y - 8, W - 16, y - 8, GRID, 1)
    s.text(L, y + 18, "blended", 12, MUTED)
    s.text(barL, y + 18, f"{r['blended']:.2f} raw", 12, INK)
    s.text(W - L, y + 18, "calibrated percentile", 10, MUTED, "end")
    return s.save("facet_breakdown.svg")


# ─── figure 4 — 2D taste space ───────────────────────────────────────────────
def fig_taste_space():
    users, _ = population(seed=11, n_users=40)
    wp = fit_whitening(np.vstack(users).tolist(), remove_top=1)
    centroids = np.array([np.mean([wp.apply(t) for t in u.tolist()], axis=0) for u in users])

    # PCA to 2D over the whitened centroids
    mean = centroids.mean(axis=0)
    Xc = centroids - mean
    cov = (Xc.T @ Xc) / (len(Xc) - 1)
    vals, vecs = np.linalg.eigh(cov)
    top2 = vecs[:, np.argsort(vals)[::-1][:2]]
    coords = Xc @ top2

    W, H = 640, 460
    pad = 56
    cx = coords[:, 0]; cy = coords[:, 1]
    def mapx(v): return pad + (v - cx.min()) / (np.ptp(cx) + 1e-9) * (W - 2 * pad)
    def mapy(v): return (H - pad) - (v - cy.min()) / (np.ptp(cy) + 1e-9) * (H - 2 * pad)

    s = Svg(W, H)
    s.text(pad, 32, "taste space", 16, INK, weight=700)
    s.text(pad, 49, "2D projection of whitened listening profiles — distance ≈ dissimilarity",
           11, MUTED)
    for gx in np.linspace(pad, W - pad, 6):
        s.line(gx, pad + 10, gx, H - pad, GRID, 1)
    for gy in np.linspace(pad + 10, H - pad, 5):
        s.line(pad, gy, W - pad, gy, GRID, 1)

    # faint edges between near neighbours (honest: only close pairs connect)
    for i in range(len(coords)):
        for j in range(i + 1, len(coords)):
            d = cosine(centroids[i].tolist(), centroids[j].tolist())
            if d > 0.55:
                s.line(mapx(cx[i]), mapy(cy[i]), mapx(cx[j]), mapy(cy[j]), GREEN, 0.8, 0.10 + d * 0.12)

    for i in range(len(coords)):
        you = (i == 0)
        s.circle(mapx(cx[i]), mapy(cy[i]), 6 if you else 4, GREEN, 1.0 if you else 0.5)
    s.text(mapx(cx[0]) + 9, mapy(cy[0]) + 4, "you", 11, GREEN, weight=700)
    return s.save("taste_space.svg")


# ─── figure 5 — optimal-transport coupling (Word Mover's Distance) ────────────
def fig_transport():
    rng = np.random.default_rng(5)
    dim = 12
    common = np.zeros(dim); common[0] = 1.0
    theme = rng.normal(size=dim); theme[0] = 0; theme /= np.linalg.norm(theme)

    def cloud(n, shift):
        th = theme + shift * rng.normal(size=dim); th[0] = 0; th /= np.linalg.norm(th)
        return [rng.normal(8, 3) * common + th + 0.1 * rng.normal(size=dim) for _ in range(n)]

    A, B = cloud(7, 0.15), cloud(7, 0.5)
    wp = fit_whitening([*[t.tolist() for t in A], *[t.tolist() for t in B]], remove_top=1)
    wa = [wp.apply(t.tolist()) for t in A]
    wb = [wp.apply(t.tolist()) for t in B]
    a = [1 / len(wa)] * len(wa); b = [1 / len(wb)] * len(wb)
    T = transport_plan(a, b, cosine_cost_matrix(wa, wb), eps=0.05, iters=300)
    Tn = np.array(T); Tn = Tn / (Tn.max() + 1e-12)

    n, m = len(wa), len(wb)
    cell = 34
    W, H = m * cell + 160, n * cell + 110
    ox, oy = 120, 70
    s = Svg(W, H)
    s.text(40, 32, "optimal transport — word mover's distance", 15, INK, weight=700)
    s.text(40, 49, "how one listener's tracks (rows) align onto another's (cols)", 11, MUTED)
    for i in range(n):
        for j in range(m):
            s.rect(ox + j * cell, oy + i * cell, cell - 2, cell - 2, GREEN, 0.06 + 0.9 * Tn[i, j], rx=2)
    s.text(ox - 12, oy + n * cell / 2, "you →", 11, MUTED, "end")
    s.text(ox + m * cell / 2, oy + n * cell + 26, "← sam's tracks", 11, MUTED, "middle")
    return s.save("transport_plan.svg")


def main():
    figs = [fig_anisotropy(), fig_recency(), fig_facets(), fig_taste_space(), fig_transport()]
    for p in figs:
        print(f"  wrote {os.path.relpath(p)}")
    print(f"{len(figs)} figures → {os.path.relpath(FIGDIR)}/")


if __name__ == "__main__":
    main()
