//! overlapping echoes — taste-similarity kernel.
//!
//! A faithful port of the pure-Python request-path engine (`common/taste/`): whitened
//! cosine, Word Mover's Distance via Sinkhorn-EMD, and a power-iteration PCA projection to
//! 2D. The point of compiling this to WASM is to push the pairwise scoring *and* the layout
//! into the browser, so the graph computes its honest geometry client-side.
//!
//! The `kernel` module is dependency-free and exercised by the native parity tests
//! (`tests/parity.rs`) against reference values produced by the Python engine. The WASM
//! bindings (behind the `wasm` feature) are thin wrappers over it.

pub mod kernel {
    /// Cosine similarity in [-1, 1]; 0.0 if either vector is degenerate. Mirrors
    /// `linalg.cosine`.
    pub fn cosine(a: &[f64], b: &[f64]) -> f64 {
        let mut dot = 0.0;
        let mut na = 0.0;
        let mut nb = 0.0;
        for i in 0..a.len().min(b.len()) {
            dot += a[i] * b[i];
        }
        for &x in a {
            na += x * x;
        }
        for &x in b {
            nb += x * x;
        }
        let na = na.sqrt();
        let nb = nb.sqrt();
        if na == 0.0 || nb == 0.0 {
            0.0
        } else {
            dot / (na * nb)
        }
    }

    /// Clamp to [lo, hi]. Mirrors `linalg.clamp`.
    pub fn clamp(x: f64, lo: f64, hi: f64) -> f64 {
        if x < lo {
            lo
        } else if x > hi {
            hi
        } else {
            x
        }
    }

    /// Apply a fitted whitening transform: `W · (x - mean)`. Identity (pass-through) when
    /// `components` or `mean` is empty. Mirrors `whitening.WhiteningParams.apply`.
    pub fn whiten(components: &[Vec<f64>], mean: &[f64], x: &[f64]) -> Vec<f64> {
        if components.is_empty() || mean.is_empty() {
            return x.to_vec();
        }
        let centered: Vec<f64> = x.iter().zip(mean).map(|(xi, mi)| xi - mi).collect();
        components
            .iter()
            .map(|row| row.iter().zip(&centered).map(|(r, c)| r * c).sum())
            .collect()
    }

    /// Pairwise cosine *distance* (1 - cos) in [0, 2]; rows index `a`, cols index `b`.
    pub fn cosine_cost_matrix(a: &[Vec<f64>], b: &[Vec<f64>]) -> Vec<Vec<f64>> {
        a.iter()
            .map(|ai| b.iter().map(|bj| 1.0 - cosine(ai, bj)).collect())
            .collect()
    }

    fn normalize_mass(weights: Option<&[f64]>, n: usize) -> Vec<f64> {
        match weights {
            Some(w) if !w.is_empty() => {
                let total: f64 = w.iter().sum();
                if total <= 0.0 {
                    vec![1.0 / n as f64; n]
                } else {
                    w.iter().map(|x| x / total).collect()
                }
            }
            _ => vec![1.0 / n as f64; n],
        }
    }

    /// Entropic optimal-transport cost ⟨T, C⟩ between distributions `a` and `b`. Mirrors
    /// `setmetric.sinkhorn` iteration-for-iteration.
    pub fn sinkhorn(a: &[f64], b: &[f64], cost: &[Vec<f64>], eps: f64, iters: usize) -> f64 {
        let n = a.len();
        let m = b.len();
        if n == 0 || m == 0 {
            return 0.0;
        }
        let k: Vec<Vec<f64>> = (0..n)
            .map(|i| (0..m).map(|j| (-cost[i][j] / eps).exp()).collect())
            .collect();
        let mut u = vec![1.0; n];
        let mut v = vec![1.0; m];
        for _ in 0..iters {
            for i in 0..n {
                let s: f64 = (0..m).map(|j| k[i][j] * v[j]).sum();
                u[i] = if s > 1e-300 { a[i] / s } else { 0.0 };
            }
            for j in 0..m {
                let s: f64 = (0..n).map(|i| k[i][j] * u[i]).sum();
                v[j] = if s > 1e-300 { b[j] / s } else { 0.0 };
            }
        }
        let mut total = 0.0;
        for i in 0..n {
            for j in 0..m {
                total += u[i] * k[i][j] * v[j] * cost[i][j];
            }
        }
        total
    }

    /// The converged coupling matrix T (for visualizing what aligned with what).
    pub fn transport_plan(
        a: &[f64],
        b: &[f64],
        cost: &[Vec<f64>],
        eps: f64,
        iters: usize,
    ) -> Vec<Vec<f64>> {
        let n = a.len();
        let m = b.len();
        let k: Vec<Vec<f64>> = (0..n)
            .map(|i| (0..m).map(|j| (-cost[i][j] / eps).exp()).collect())
            .collect();
        let mut u = vec![1.0; n];
        let mut v = vec![1.0; m];
        for _ in 0..iters {
            for i in 0..n {
                let s: f64 = (0..m).map(|j| k[i][j] * v[j]).sum();
                u[i] = if s > 1e-300 { a[i] / s } else { 0.0 };
            }
            for j in 0..m {
                let s: f64 = (0..n).map(|i| k[i][j] * u[i]).sum();
                v[j] = if s > 1e-300 { b[j] / s } else { 0.0 };
            }
        }
        (0..n)
            .map(|i| (0..m).map(|j| u[i] * k[i][j] * v[j]).collect())
            .collect()
    }

    /// Word Mover's Distance between two embedding sets (cosine ground cost).
    pub fn wmd_distance(
        a: &[Vec<f64>],
        b: &[Vec<f64>],
        wa: Option<&[f64]>,
        wb: Option<&[f64]>,
        eps: f64,
        iters: usize,
    ) -> f64 {
        if a.is_empty() || b.is_empty() {
            return 1.0;
        }
        let am = normalize_mass(wa, a.len());
        let bm = normalize_mass(wb, b.len());
        let c = cosine_cost_matrix(a, b);
        sinkhorn(&am, &bm, &c, eps, iters)
    }

    /// BERTScore-style soft set similarity in [0, 1] (F1 of precision/recall of best
    /// matches). Cheap fallback for large sets. Mirrors `setmetric.mean_max_alignment`.
    pub fn mean_max_alignment(a: &[Vec<f64>], b: &[Vec<f64>]) -> f64 {
        if a.is_empty() || b.is_empty() {
            return 0.0;
        }
        let prec: f64 = a
            .iter()
            .map(|ai| clamp(b.iter().map(|bj| cosine(ai, bj)).fold(f64::MIN, f64::max), 0.0, 1.0))
            .sum::<f64>()
            / a.len() as f64;
        let rec: f64 = b
            .iter()
            .map(|bj| clamp(a.iter().map(|ai| cosine(ai, bj)).fold(f64::MIN, f64::max), 0.0, 1.0))
            .sum::<f64>()
            / b.len() as f64;
        if prec + rec == 0.0 {
            0.0
        } else {
            2.0 * prec * rec / (prec + rec)
        }
    }

    /// Similarity in [0, 1] from WMD. Mirrors `setmetric.wmd_similarity`.
    pub fn wmd_similarity(
        a: &[Vec<f64>],
        b: &[Vec<f64>],
        wa: Option<&[f64]>,
        wb: Option<&[f64]>,
        max_set: usize,
        eps: f64,
        iters: usize,
    ) -> f64 {
        if a.is_empty() || b.is_empty() {
            return 0.0;
        }
        if a.len() > max_set || b.len() > max_set {
            return mean_max_alignment(a, b);
        }
        let d = wmd_distance(a, b, wa, wb, eps, iters);
        clamp(1.0 - 0.5 * d, 0.0, 1.0)
    }

    // ── projection ────────────────────────────────────────────────────────────
    fn mat_vec(m: &[Vec<f64>], v: &[f64]) -> Vec<f64> {
        m.iter().map(|row| row.iter().zip(v).map(|(r, x)| r * x).sum()).collect()
    }

    fn normalize(v: &[f64]) -> Vec<f64> {
        let n: f64 = v.iter().map(|x| x * x).sum::<f64>().sqrt();
        if n == 0.0 {
            v.to_vec()
        } else {
            v.iter().map(|x| x / n).collect()
        }
    }

    fn top_eigenvector(cov: &[Vec<f64>], iters: usize) -> (Vec<f64>, f64) {
        let d = cov.len();
        let mut v = vec![0.0; d];
        if d > 0 {
            v[0] = 1.0;
        }
        for _ in 0..iters {
            v = normalize(&mat_vec(cov, &v));
        }
        let av = mat_vec(cov, &v);
        let lambda: f64 = v.iter().zip(&av).map(|(a, b)| a * b).sum();
        (v, lambda)
    }

    /// Project a cloud of points to 2D via power-iteration PCA (top-2 principal axes).
    /// Returns one `[x, y]` per input point. Used for the honest semantic-canvas layout.
    pub fn pca_project_2d(points: &[Vec<f64>]) -> Vec<[f64; 2]> {
        let n = points.len();
        if n == 0 {
            return vec![];
        }
        let d = points[0].len();
        if d == 0 {
            return vec![[0.0, 0.0]; n];
        }
        // center
        let mut mean = vec![0.0; d];
        for p in points {
            for i in 0..d {
                mean[i] += p[i];
            }
        }
        for m in &mut mean {
            *m /= n as f64;
        }
        let centered: Vec<Vec<f64>> = points
            .iter()
            .map(|p| p.iter().zip(&mean).map(|(x, m)| x - m).collect())
            .collect();
        // covariance (d x d)
        let mut cov = vec![vec![0.0; d]; d];
        for p in &centered {
            for i in 0..d {
                for j in 0..d {
                    cov[i][j] += p[i] * p[j];
                }
            }
        }
        let denom = (n.max(2) - 1) as f64;
        for row in &mut cov {
            for c in row {
                *c /= denom;
            }
        }
        // top-2 eigenvectors via power iteration + deflation
        let (v1, l1) = top_eigenvector(&cov, 100);
        for i in 0..d {
            for j in 0..d {
                cov[i][j] -= l1 * v1[i] * v1[j];
            }
        }
        let (v2, _l2) = top_eigenvector(&cov, 100);
        centered
            .iter()
            .map(|p| {
                let x = p.iter().zip(&v1).map(|(a, b)| a * b).sum();
                let y = p.iter().zip(&v2).map(|(a, b)| a * b).sum();
                [x, y]
            })
            .collect()
    }

    /// Classical MDS: embed n items in 2D from an n×n dissimilarity matrix so euclidean
    /// distance ≈ the given dissimilarity. Mirrors the TS `mds2D` step-for-step (double
    /// centering of squared distances → top-2 eigenpairs by power iteration + deflation).
    /// This is the semantic-canvas layout: position is taste, distance is dissimilarity.
    pub fn mds_2d(dissim: &[Vec<f64>]) -> Vec<[f64; 2]> {
        let n = dissim.len();
        if n == 0 {
            return vec![];
        }
        if n == 1 {
            return vec![[0.0, 0.0]];
        }
        // double-centering of squared distances -> Gram matrix B
        let d2: Vec<Vec<f64>> = dissim
            .iter()
            .map(|row| row.iter().map(|x| x * x).collect())
            .collect();
        let row_mean: Vec<f64> = d2.iter().map(|row| row.iter().sum::<f64>() / n as f64).collect();
        let grand: f64 = row_mean.iter().sum::<f64>() / n as f64;
        let mut b: Vec<Vec<f64>> = d2
            .iter()
            .enumerate()
            .map(|(i, row)| {
                row.iter()
                    .enumerate()
                    .map(|(j, x)| -0.5 * (x - row_mean[i] - row_mean[j] + grand))
                    .collect()
            })
            .collect();
        let (v1, l1) = top_eigenvector(&b, 128);
        for i in 0..n {
            for j in 0..n {
                b[i][j] -= l1 * v1[i] * v1[j];
            }
        }
        let (v2, l2) = top_eigenvector(&b, 128);
        let s1 = l1.max(0.0).sqrt();
        let s2 = l2.max(0.0).sqrt();
        (0..n).map(|i| [v1[i] * s1, v2[i] * s2]).collect()
    }

    // ── glyph field ───────────────────────────────────────────────────────────
    // 4×4 Bayer matrix for ordered dithering — the pixel-honest way to shade a glyph
    // raster: quantization error becomes a stable spatial pattern, not random noise.
    const BAYER4: [[f64; 4]; 4] = [
        [0.0, 8.0, 2.0, 10.0],
        [12.0, 4.0, 14.0, 6.0],
        [3.0, 11.0, 1.0, 9.0],
        [15.0, 7.0, 13.0, 5.0],
    ];

    /// Rasterize a similarity field onto a `cols`×`rows` glyph grid (row-major levels in
    /// `0..levels`). Each node i at (xs[i], ys[i]) carries a value in [0,1] (its real
    /// match-with-you); a cell's intensity is the **max** over nodes of
    /// `val · exp(-d²/(2·radius²))` — the strongest presence wins, values never sum, so a
    /// crowd of weak matches cannot fake a strong one. Cell (r,c) is sampled at its center:
    /// `(x0 + (c+0.5)·cell_w, y0 + (r+0.5)·cell_h)`. Intensity is quantized to `levels`
    /// glyphs with Bayer ordered dithering. This is the honest backdrop: glyph brightness
    /// = interpolated match-with-you, dissolving to silence where there is no data.
    pub fn field_grid(
        xs: &[f64],
        ys: &[f64],
        vals: &[f64],
        cols: usize,
        rows: usize,
        x0: f64,
        y0: f64,
        cell_w: f64,
        cell_h: f64,
        radius: f64,
        levels: usize,
    ) -> Vec<u8> {
        let mut out = vec![0u8; cols * rows];
        if levels < 2 || radius <= 0.0 || xs.is_empty() {
            return out;
        }
        let n = xs.len().min(ys.len()).min(vals.len());
        let inv_2r2 = 1.0 / (2.0 * radius * radius);
        let max_level = (levels - 1) as f64;
        for r in 0..rows {
            let py = y0 + (r as f64 + 0.5) * cell_h;
            for c in 0..cols {
                let px = x0 + (c as f64 + 0.5) * cell_w;
                let mut intensity: f64 = 0.0;
                for i in 0..n {
                    if vals[i] <= 0.0 {
                        continue;
                    }
                    let dx = px - xs[i];
                    let dy = py - ys[i];
                    let w = vals[i] * (-(dx * dx + dy * dy) * inv_2r2).exp();
                    if w > intensity {
                        intensity = w;
                    }
                }
                let q = clamp(intensity, 0.0, 1.0) * max_level;
                let t = (BAYER4[r % 4][c % 4] + 0.5) / 16.0;
                let level = (q + t).floor().min(max_level).max(0.0);
                out[r * cols + c] = level as u8;
            }
        }
        out
    }
}

// ── WASM bindings (feature = "wasm") ────────────────────────────────────────────
#[cfg(feature = "wasm")]
mod wasm_api {
    use super::kernel;
    use wasm_bindgen::prelude::*;

    fn from_js<T: serde::de::DeserializeOwned>(v: JsValue) -> Result<T, JsValue> {
        serde_wasm_bindgen::from_value(v).map_err(|e| JsValue::from_str(&e.to_string()))
    }

    /// Cosine similarity over two JS number arrays.
    #[wasm_bindgen]
    pub fn cosine(a: JsValue, b: JsValue) -> Result<f64, JsValue> {
        let a: Vec<f64> = from_js(a)?;
        let b: Vec<f64> = from_js(b)?;
        Ok(kernel::cosine(&a, &b))
    }

    /// WMD similarity in [0,1] between two sets of embeddings (arrays of arrays), with
    /// optional per-track weights (pass `null` for uniform).
    #[wasm_bindgen]
    pub fn wmd_similarity(
        a: JsValue,
        b: JsValue,
        wa: JsValue,
        wb: JsValue,
        eps: f64,
        iters: usize,
    ) -> Result<f64, JsValue> {
        let a: Vec<Vec<f64>> = from_js(a)?;
        let b: Vec<Vec<f64>> = from_js(b)?;
        let wa: Option<Vec<f64>> = from_js(wa).ok();
        let wb: Option<Vec<f64>> = from_js(wb).ok();
        Ok(kernel::wmd_similarity(
            &a,
            &b,
            wa.as_deref(),
            wb.as_deref(),
            40,
            eps,
            iters,
        ))
    }

    /// The Sinkhorn coupling matrix (for the transport-plan visualization).
    #[wasm_bindgen]
    pub fn transport_plan(
        a: JsValue,
        b: JsValue,
        cost: JsValue,
        eps: f64,
        iters: usize,
    ) -> Result<JsValue, JsValue> {
        let a: Vec<f64> = from_js(a)?;
        let b: Vec<f64> = from_js(b)?;
        let cost: Vec<Vec<f64>> = from_js(cost)?;
        let t = kernel::transport_plan(&a, &b, &cost, eps, iters);
        serde_wasm_bindgen::to_value(&t).map_err(|e| JsValue::from_str(&e.to_string()))
    }

    /// Project a cloud of vectors to 2D (top-2 PCA). Input/Output are arrays of arrays.
    #[wasm_bindgen]
    pub fn project_2d(points: JsValue) -> Result<JsValue, JsValue> {
        let points: Vec<Vec<f64>> = from_js(points)?;
        let coords = kernel::pca_project_2d(&points);
        serde_wasm_bindgen::to_value(&coords).map_err(|e| JsValue::from_str(&e.to_string()))
    }

    /// Classical MDS from an n×n dissimilarity matrix to 2D — the semantic-canvas layout.
    #[wasm_bindgen]
    pub fn mds_2d(dissim: JsValue) -> Result<JsValue, JsValue> {
        let dissim: Vec<Vec<f64>> = from_js(dissim)?;
        let coords = kernel::mds_2d(&dissim);
        serde_wasm_bindgen::to_value(&coords).map_err(|e| JsValue::from_str(&e.to_string()))
    }

    /// Rasterize the match-with-you field onto a glyph grid (row-major dither levels).
    /// Plain numeric slices in, bytes out — no serde on the hot path; this runs every
    /// animation frame while the layout glides.
    #[wasm_bindgen]
    pub fn field_grid(
        xs: Vec<f64>,
        ys: Vec<f64>,
        vals: Vec<f64>,
        cols: usize,
        rows: usize,
        x0: f64,
        y0: f64,
        cell_w: f64,
        cell_h: f64,
        radius: f64,
        levels: usize,
    ) -> Vec<u8> {
        kernel::field_grid(&xs, &ys, &vals, cols, rows, x0, y0, cell_w, cell_h, radius, levels)
    }
}
