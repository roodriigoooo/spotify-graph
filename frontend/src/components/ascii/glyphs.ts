/**
 * glyphs — pure string helpers for the ASCII/pixel design language.
 *
 * No React, no DOM: just deterministic text, so they're trivially unit-tested and reusable
 * by any component. This is where the "claude-code terminal, with soul" texture comes from.
 */

export const FILLED = '█'
export const HALF = '▓'
export const LIGHT = '░'
export const HEAD = '▓'

/** Spinner frame sets — pick one per loader for variety/personality. */
export const SPINNERS = {
  braille: ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'],
  blocks: ['▖', '▘', '▝', '▗'],
  bar: ['▁', '▃', '▄', '▅', '▆', '▇', '▆', '▅', '▄', '▃'],
  dots: ['·  ', '·· ', '···', ' ··', '  ·', '   '],
  pulse: ['◍', '◌', '◍', '●'],
} as const

const SPARK = '▁▂▃▄▅▆▇█'

/** Clamp helper. */
export function clamp01(x: number): number {
  return x < 0 ? 0 : x > 1 ? 1 : x
}

/**
 * A horizontal ASCII meter for a value in [0,1]:  ████████▓░░░░░░░  (head char marks the
 * leading edge, pixel-style). `width` is total cells.
 */
export function asciiBar(value: number, width = 16): string {
  const v = clamp01(value)
  const fill = Math.round(v * width)
  if (fill <= 0) return LIGHT.repeat(width)
  if (fill >= width) return FILLED.repeat(width)
  return FILLED.repeat(fill - 1) + HEAD + LIGHT.repeat(width - fill)
}

/** A unicode sparkline from a series (each value scaled to the series max). */
export function sparkline(values: number[]): string {
  if (values.length === 0) return ''
  const max = Math.max(...values, 0)
  if (max <= 0) return SPARK[0].repeat(values.length)
  return values
    .map((v) => SPARK[Math.min(SPARK.length - 1, Math.round(clamp01(v / max) * (SPARK.length - 1)))])
    .join('')
}

/**
 * A dotted-leader row:  "genre ·············· 0.62"  — fixed total `width`, value right-aligned.
 */
export function leader(label: string, value: string, width = 28): string {
  const room = Math.max(1, width - label.length - value.length - 2)
  return `${label} ${'·'.repeat(room)} ${value}`
}

/** Format a [0,1] score as a 2-decimal string ("0.62"). */
export function fmt(value: number, dp = 2): string {
  return clamp01(value).toFixed(dp)
}

/** Format a [0,1] score as an integer percent ("62%"). */
export function pct(value: number): string {
  return `${Math.round(clamp01(value) * 100)}%`
}
