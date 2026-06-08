import { describe, it, expect } from 'vitest'
import { cosine, sinkhorn, wmdSimilarity, mds2D, pca2D } from './kernel'

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
})
