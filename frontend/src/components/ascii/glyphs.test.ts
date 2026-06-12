import { describe, it, expect } from 'vitest'
import { asciiBar, sparkline, leader, fmt, pct, clamp01, FILLED, LIGHT } from './glyphs'

describe('asciiBar', () => {
  it('is all-light at 0 and all-filled at 1', () => {
    expect(asciiBar(0, 10)).toBe(LIGHT.repeat(10))
    expect(asciiBar(1, 10)).toBe(FILLED.repeat(10))
  })
  it('always returns exactly `width` cells', () => {
    for (const v of [0, 0.1, 0.37, 0.5, 0.99, 1]) {
      expect([...asciiBar(v, 16)].length).toBe(16)
    }
  })
  it('grows monotonically with value', () => {
    const fillCount = (s: string) => [...s].filter((c) => c !== LIGHT).length
    expect(fillCount(asciiBar(0.25, 20))).toBeLessThan(fillCount(asciiBar(0.75, 20)))
  })
  it('clamps out-of-range input', () => {
    expect(asciiBar(-1, 8)).toBe(LIGHT.repeat(8))
    expect(asciiBar(2, 8)).toBe(FILLED.repeat(8))
  })
})

describe('sparkline', () => {
  it('matches series length', () => {
    expect(sparkline([1, 2, 3, 4]).length).toBe(4)
  })
  it('peaks at the max value', () => {
    const s = sparkline([1, 5, 2])
    expect(s[1]).toBe('█')
  })
  it('handles empty + all-zero', () => {
    expect(sparkline([])).toBe('')
    expect(sparkline([0, 0, 0]).length).toBe(3)
  })
})

describe('leader / fmt / pct / clamp01', () => {
  it('leader pads to a stable width with dots', () => {
    const s = leader('genre', '0.62', 28)
    expect(s.startsWith('genre ')).toBe(true)
    expect(s.endsWith(' 0.62')).toBe(true)
    expect(s).toContain('·')
  })
  it('fmt + pct format scores', () => {
    expect(fmt(0.617)).toBe('0.62')
    expect(pct(0.617)).toBe('62%')
  })
  it('clamp01 bounds', () => {
    expect(clamp01(-3)).toBe(0)
    expect(clamp01(9)).toBe(1)
    expect(clamp01(0.4)).toBe(0.4)
  })
})
