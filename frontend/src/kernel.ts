/**
 * kernel — the taste math, client-side.
 *
 * A TypeScript port of the same kernel that lives in Rust (`rust/src/lib.rs`) and Python
 * (`common/taste/`): cosine, Word Mover's Distance, and a deterministic 2D projection. The
 * graph computes its honest geometry in the browser from this.
 *
 * If the Rust→WASM build is present (run `rust/build-wasm.sh`), `loadWasmKernel()` swaps in
 * the native implementation; otherwise this pure-TS version is used. Same math either way.
 *
 * Note the app receives pairwise *similarities* from /graph, not raw vectors — so the layout
 * uses classical MDS (`mds2D`) over the dissimilarity matrix (distance ≈ 1 − similarity),
 * which is the honest encoding the design contract asks for.
 */

export function cosine(a: number[], b: number[]): number {
  let dot = 0, na = 0, nb = 0
  const n = Math.min(a.length, b.length)
  for (let i = 0; i < n; i++) dot += a[i] * b[i]
  for (const x of a) na += x * x
  for (const x of b) nb += x * x
  na = Math.sqrt(na); nb = Math.sqrt(nb)
  return na === 0 || nb === 0 ? 0 : dot / (na * nb)
}

const clamp = (x: number, lo = 0, hi = 1) => (x < lo ? lo : x > hi ? hi : x)

function normalizeMass(w: number[] | null, n: number): number[] {
  if (!w || w.length === 0) return Array(n).fill(1 / n)
  const total = w.reduce((s, x) => s + x, 0)
  if (total <= 0) return Array(n).fill(1 / n)
  return w.map((x) => x / total)
}

function cosineCostMatrix(a: number[][], b: number[][]): number[][] {
  return a.map((ai) => b.map((bj) => 1 - cosine(ai, bj)))
}

/** Entropic OT cost ⟨T,C⟩ — mirrors `setmetric.sinkhorn`. */
export function sinkhorn(a: number[], b: number[], cost: number[][], eps = 0.1, iters = 50): number {
  const n = a.length, m = b.length
  if (n === 0 || m === 0) return 0
  const K = a.map((_, i) => b.map((_, j) => Math.exp(-cost[i][j] / eps)))
  const u = Array(n).fill(1), v = Array(m).fill(1)
  for (let t = 0; t < iters; t++) {
    for (let i = 0; i < n; i++) {
      let s = 0; for (let j = 0; j < m; j++) s += K[i][j] * v[j]
      u[i] = s > 1e-300 ? a[i] / s : 0
    }
    for (let j = 0; j < m; j++) {
      let s = 0; for (let i = 0; i < n; i++) s += K[i][j] * u[i]
      v[j] = s > 1e-300 ? b[j] / s : 0
    }
  }
  let total = 0
  for (let i = 0; i < n; i++) for (let j = 0; j < m; j++) total += u[i] * K[i][j] * v[j] * cost[i][j]
  return total
}

/** WMD similarity in [0,1] between two embedding sets — mirrors `setmetric.wmd_similarity`. */
export function wmdSimilarity(
  a: number[][], b: number[][], wa: number[] | null = null, wb: number[] | null = null,
  eps = 0.1, iters = 50,
): number {
  if (a.length === 0 || b.length === 0) return 0
  const d = sinkhorn(normalizeMass(wa, a.length), normalizeMass(wb, b.length), cosineCostMatrix(a, b), eps, iters)
  return clamp(1 - 0.5 * d)
}

// ── 2D layout ───────────────────────────────────────────────────────────────
function matVec(m: number[][], v: number[]): number[] {
  return m.map((row) => row.reduce((s, x, i) => s + x * v[i], 0))
}
function unit(v: number[]): number[] {
  const n = Math.sqrt(v.reduce((s, x) => s + x * x, 0))
  return n === 0 ? v : v.map((x) => x / n)
}
function topEigen(m: number[][], iters = 128): { vec: number[]; val: number } {
  const d = m.length
  let v = Array(d).fill(0); if (d) v[0] = 1
  for (let t = 0; t < iters; t++) v = unit(matVec(m, v))
  const mv = matVec(m, v)
  const val = v.reduce((s, x, i) => s + x * mv[i], 0)
  return { vec: v, val }
}

/**
 * Classical MDS: embed n items in 2D from an n×n dissimilarity matrix so that euclidean
 * distance ≈ the given dissimilarity. Deterministic (power-iteration eigvecs). This is the
 * semantic canvas layout — position is taste, distance is dissimilarity.
 *
 * Delegates to the Rust→WASM kernel when it's loaded (same math, native speed); the TS
 * body below is the always-available fallback.
 */
export function mds2D(dissim: number[][]): Array<[number, number]> {
  if (_native) {
    try {
      return _native.mds_2d(dissim) as Array<[number, number]>
    } catch { /* fall through to TS */ }
  }
  return mds2DTs(dissim)
}

export function mds2DTs(dissim: number[][]): Array<[number, number]> {
  const n = dissim.length
  if (n === 0) return []
  if (n === 1) return [[0, 0]]
  // double-centering of squared distances -> Gram matrix B
  const d2 = dissim.map((row) => row.map((x) => x * x))
  const rowMean = d2.map((row) => row.reduce((s, x) => s + x, 0) / n)
  const grand = rowMean.reduce((s, x) => s + x, 0) / n
  const B = d2.map((row, i) => row.map((x, j) => -0.5 * (x - rowMean[i] - rowMean[j] + grand)))
  const e1 = topEigen(B)
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) B[i][j] -= e1.val * e1.vec[i] * e1.vec[j]
  const e2 = topEigen(B)
  const s1 = Math.sqrt(Math.max(0, e1.val))
  const s2 = Math.sqrt(Math.max(0, e2.val))
  return e1.vec.map((_, i) => [e1.vec[i] * s1, e2.vec[i] * s2] as [number, number])
}

// ── glyph field ─────────────────────────────────────────────────────────────
// 4×4 Bayer matrix — ordered dithering turns quantization error into a stable
// pixel-honest pattern instead of noise. Mirrors `kernel::field_grid` in Rust.
const BAYER4 = [
  [0, 8, 2, 10],
  [12, 4, 14, 6],
  [3, 11, 1, 9],
  [15, 7, 13, 5],
] as const

/**
 * Rasterize the match-with-you field onto a cols×rows glyph grid (row-major levels in
 * [0, levels)). A cell's intensity is the **max** over nodes of val·exp(−d²/2r²) — the
 * strongest presence wins; values never sum, so a crowd of weak matches cannot fake a
 * strong one. Runs per animation frame, so it prefers the Rust→WASM kernel when loaded.
 */
export function fieldGrid(
  xs: number[], ys: number[], vals: number[],
  cols: number, rows: number,
  x0: number, y0: number, cellW: number, cellH: number,
  radius: number, levels: number,
): Uint8Array {
  if (_native) {
    try {
      return _native.field_grid(
        Float64Array.from(xs), Float64Array.from(ys), Float64Array.from(vals),
        cols, rows, x0, y0, cellW, cellH, radius, levels,
      )
    } catch { /* fall through to TS */ }
  }
  return fieldGridTs(xs, ys, vals, cols, rows, x0, y0, cellW, cellH, radius, levels)
}

export function fieldGridTs(
  xs: number[], ys: number[], vals: number[],
  cols: number, rows: number,
  x0: number, y0: number, cellW: number, cellH: number,
  radius: number, levels: number,
): Uint8Array {
  const out = new Uint8Array(cols * rows)
  if (levels < 2 || radius <= 0 || xs.length === 0) return out
  const n = Math.min(xs.length, ys.length, vals.length)
  const inv2r2 = 1 / (2 * radius * radius)
  const maxLevel = levels - 1
  for (let r = 0; r < rows; r++) {
    const py = y0 + (r + 0.5) * cellH
    for (let c = 0; c < cols; c++) {
      const px = x0 + (c + 0.5) * cellW
      let intensity = 0
      for (let i = 0; i < n; i++) {
        if (vals[i] <= 0) continue
        const dx = px - xs[i]
        const dy = py - ys[i]
        const w = vals[i] * Math.exp(-(dx * dx + dy * dy) * inv2r2)
        if (w > intensity) intensity = w
      }
      const q = clamp(intensity) * maxLevel
      const t = (BAYER4[r % 4][c % 4] + 0.5) / 16
      out[r * cols + c] = Math.min(maxLevel, Math.floor(q + t))
    }
  }
  return out
}

/** PCA projection of a vector cloud to 2D (mirrors the kernel's `pca_project_2d`). */
export function pca2D(points: number[][]): Array<[number, number]> {
  const n = points.length
  if (n === 0) return []
  const d = points[0].length
  if (d === 0) return points.map(() => [0, 0])
  const mean = Array(d).fill(0)
  for (const p of points) for (let i = 0; i < d; i++) mean[i] += p[i]
  for (let i = 0; i < d; i++) mean[i] /= n
  const centered = points.map((p) => p.map((x, i) => x - mean[i]))
  const cov = Array.from({ length: d }, () => Array(d).fill(0))
  for (const p of centered) for (let i = 0; i < d; i++) for (let j = 0; j < d; j++) cov[i][j] += p[i] * p[j]
  const denom = Math.max(1, n - 1)
  for (let i = 0; i < d; i++) for (let j = 0; j < d; j++) cov[i][j] /= denom
  const e1 = topEigen(cov)
  for (let i = 0; i < d; i++) for (let j = 0; j < d; j++) cov[i][j] -= e1.val * e1.vec[i] * e1.vec[j]
  const e2 = topEigen(cov)
  return centered.map((p) => [
    p.reduce((s, x, i) => s + x * e1.vec[i], 0),
    p.reduce((s, x, i) => s + x * e2.vec[i], 0),
  ] as [number, number])
}

// ── optional native (WASM) kernel ─────────────────────────────────────────────
export interface NativeKernel {
  cosine(a: number[], b: number[]): number
  wmd_similarity(a: number[][], b: number[][], wa: number[] | null, wb: number[] | null, eps: number, iters: number): number
  project_2d(points: number[][]): Array<[number, number]>
  mds_2d(dissim: number[][]): Array<[number, number]>
  field_grid(
    xs: Float64Array, ys: Float64Array, vals: Float64Array,
    cols: number, rows: number,
    x0: number, y0: number, cellW: number, cellH: number,
    radius: number, levels: number,
  ): Uint8Array
}

let _native: NativeKernel | null = null

/** Which implementation is live — surfaced in the UI so the kernel is honest about itself. */
export function kernelBackend(): 'rust·wasm' | 'ts' {
  return _native ? 'rust·wasm' : 'ts'
}

/**
 * Try to load the Rust→WASM kernel (built by rust/build-wasm.sh into public/kernel/, which
 * vite ships verbatim as the /kernel/ static dir). Returns null if it isn't built —
 * `mds2D`/`fieldGrid` fall back to the pure-TS bodies. Safe to call once at startup; once
 * resolved, every subsequent kernel call goes native.
 */
export async function loadWasmKernel(): Promise<NativeKernel | null> {
  if (_native) return _native
  try {
    // A full runtime URL, deliberately opaque to the bundler: the kernel is an optional
    // static asset, not a build-time dependency, so the app builds with or without it.
    // (A bare '/kernel/...' path won't do — vite's dev-server import analysis rejects
    // source imports of public-dir files; an absolute http URL is treated as external and
    // the browser imports it natively, in dev and prod alike.)
    const url = new URL('/kernel/echoes_kernel.js', window.location.href).href
    const mod: any = await import(/* @vite-ignore */ url)
    if (mod.default) await mod.default()  // init: fetches echoes_kernel_bg.wasm next to the JS
    _native = mod as NativeKernel
    return _native
  } catch {
    return null
  }
}
