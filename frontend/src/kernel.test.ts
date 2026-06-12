import { describe, it, expect } from 'vitest'
import { cosine, sinkhorn, wmdSimilarity, mds2D, pca2D, fieldGrid } from './kernel'

const close = (a: number, b: number, eps = 1e-9) => expect(Math.abs(a - b)).toBeLessThan(eps)

describe('kernel parity with the Python/Rust engine', () => {
  it('cosine matches the reference value', () => {
    close(cosine([1, 2, 3], [4, 5, 6]), 0.9746318461970762)
  })
  it('cosine is 0 for a degenerate vector', () => {
    close(cosine([0, 0], [1, 1]), 0)
  })
  it('sinkhorn matches the reference value', () => {
    const cost = [[0.1, 0.7, 0.4], [0.6, 0.2, 0.9]]
    close(sinkhorn([0.5, 0.5], [0.3, 0.3, 0.4], cost, 0.1, 50), 0.35003403797338034)
  })
  it('wmd similarity matches the reference value', () => {
    const a = [[1, 0, 0], [0.9, 0.2, 0], [0.2, 0.8, 0.1]]
    const b = [[0.95, 0.1, 0], [0.1, 0.9, 0.2]]
    close(wmdSimilarity(a, b, [3, 2, 1], [2, 2], 0.1, 50), 0.8724560194975868, 1e-9)
  })
})

describe('layout', () => {
  it('mds2D places dissimilar items farther apart', () => {
    // 3 items: A,B close (dissim 0.1), C far from both (dissim 1.0)
    const dissim = [
      [0, 0.1, 1.0],
      [0.1, 0, 1.0],
      [1.0, 1.0, 0],
    ]
    const c = mds2D(dissim)
    expect(c.length).toBe(3)
    const dist = (i: number, j: number) => Math.hypot(c[i][0] - c[j][0], c[i][1] - c[j][1])
    expect(dist(0, 2)).toBeGreaterThan(dist(0, 1))
  })
  it('mds2D handles tiny inputs', () => {
    expect(mds2D([]).length).toBe(0)
    expect(mds2D([[0]]).length).toBe(1)
  })
  it('pca2D separates two clusters', () => {
    const pts = [[0, 0, 0], [0.1, 0, 0], [10, 10, 10], [10.1, 10, 10]]
    const c = pca2D(pts)
    const within = Math.hypot(c[0][0] - c[1][0], c[0][1] - c[1][1])
    const across = Math.hypot(c[0][0] - c[2][0], c[0][1] - c[2][1])
    expect(across).toBeGreaterThan(within)
  })
  it('mds2D reconstructs euclidean distances (parity fixture with Rust)', () => {
    const s2 = Math.sqrt(2)
    const c = mds2D([
      [0, 1, 1],
      [1, 0, s2],
      [1, s2, 0],
    ])
    const dist = (i: number, j: number) => Math.hypot(c[i][0] - c[j][0], c[i][1] - c[j][1])
    expect(Math.abs(dist(0, 1) - 1)).toBeLessThan(1e-6)
    expect(Math.abs(dist(0, 2) - 1)).toBeLessThan(1e-6)
    expect(Math.abs(dist(1, 2) - s2)).toBeLessThan(1e-6)
  })
})

describe('fieldGrid (parity fixtures with Rust kernel::field_grid)', () => {
  it('peaks at the node and decays to the rim', () => {
    const g = fieldGrid([50], [50], [1], 11, 11, 0, 0, 9.0909, 9.0909, 25, 6)
    expect(g.length).toBe(121)
    expect(g[5 * 11 + 5]).toBe(5)
    expect(g[0]).toBeLessThan(g[5 * 11 + 5])
  })
  it('takes the max, never the sum (crowds cannot fake strength)', () => {
    const one = fieldGrid([50], [50], [0.6], 8, 8, 0, 0, 12.5, 12.5, 30, 6)
    const two = fieldGrid([50, 50], [50, 50], [0.6, 0.6], 8, 8, 0, 0, 12.5, 12.5, 30, 6)
    expect(Array.from(two)).toEqual(Array.from(one))
  })
  it('is silent with no nodes or zero values', () => {
    expect(Array.from(fieldGrid([], [], [], 4, 4, 0, 0, 1, 1, 10, 6)).every((l) => l === 0)).toBe(true)
    expect(Array.from(fieldGrid([1], [1], [0], 4, 4, 0, 0, 1, 1, 10, 6)).every((l) => l === 0)).toBe(true)
  })
})
