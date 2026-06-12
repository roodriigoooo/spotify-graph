/**
 * ascii — the pixel/terminal component kit.
 *
 * Small, composable, dependency-free React pieces that carry the design language: box-draw
 * panels, animated ASCII meters, dotted-leader readouts, ASCII spinners, a typewriter, and a
 * pixel marker. Pure-string logic lives in ./glyphs (unit-tested); this file is the React skin.
 */
import React, { useEffect, useRef, useState } from 'react'
import { FILLED, LIGHT, SPINNERS, clamp01, fmt, pct } from './glyphs'
import './ascii.css'

export { asciiBar, sparkline, leader, fmt, pct, SPINNERS } from './glyphs'

// ── Panel ──────────────────────────────────────────────────────
export function Panel({
  title, right, children, className = '', style,
}: {
  title: React.ReactNode
  right?: React.ReactNode
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <div className={`ascii-panel ascii-anim-in ${className}`} style={style}>
      <div className="ascii-panel__bar">
        <span className="ascii-panel__title">
          <span className="ascii-panel__dot">◆</span>
          {title}
        </span>
        {right != null && <span>{right}</span>}
      </div>
      <div className="ascii-panel__body">{children}</div>
    </div>
  )
}

// ── Bar (animated ASCII meter) ─────────────────────────────────
export function Bar({
  label, value, weight, width = 18,
}: {
  label: string
  value: number
  weight?: number
  width?: number
}) {
  const v = clamp01(value)
  return (
    <div className="ascii-bar" title={weight != null ? `weight ${fmt(weight)}` : undefined}>
      <span className="ascii-bar__label">{label}</span>
      <span className="ascii-bar__track">
        {LIGHT.repeat(width)}
        <span className="ascii-bar__fill" style={{ width: `${v * 100}%` }}>
          {FILLED.repeat(width)}
        </span>
      </span>
      <span className="ascii-bar__val">
        {fmt(v)}
        {weight != null && <span className="ascii-bar__weight"> ·{fmt(weight, 1)}</span>}
      </span>
    </div>
  )
}

// ── Readout (dotted leader) ────────────────────────────────────
export function Readout({ label, value, width = 30 }: { label: string; value: string; width?: number }) {
  const room = Math.max(1, width - label.length - value.length - 2)
  return (
    <div className="ascii-readout">
      {label} {'·'.repeat(room)} <b>{value}</b>
    </div>
  )
}

// ── Spinner (cycling ASCII frames) ─────────────────────────────
export function Spinner({
  frames = SPINNERS.braille, label, intervalMs = 90,
}: {
  frames?: readonly string[]
  label?: string
  intervalMs?: number
}) {
  const [i, setI] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setI((x) => (x + 1) % frames.length), intervalMs)
    return () => clearInterval(id)
  }, [frames, intervalMs])
  return (
    <span className="ascii-spinner" role="status" aria-live="polite">
      {frames[i]}
      {label && <span className="ascii-spinner__label">{label}</span>}
    </span>
  )
}

// ── Typewriter (char-by-char reveal) ───────────────────────────
export function Typewriter({
  text, speedMs = 28, cursor = true, className = '',
}: {
  text: string
  speedMs?: number
  cursor?: boolean
  className?: string
}) {
  const [n, setN] = useState(0)
  const ref = useRef(text)
  useEffect(() => {
    ref.current = text
    setN(0)
    const id = setInterval(() => {
      setN((x) => {
        if (x >= ref.current.length) { clearInterval(id); return x }
        return x + 1
      })
    }, speedMs)
    return () => clearInterval(id)
  }, [text, speedMs])
  return <span className={`${className} ${cursor && n < text.length ? 'ascii-cursor' : ''}`}>{text.slice(0, n)}</span>
}

// ── Marker (pixel node glyph for legends / cards) ──────────────
const PIXELS = [
  [-1, -2], [0, -2],
  [-2, -1], [1, -1],
  [-2, 0], [1, 0],
  [-1, 1], [0, 1],
]
export function Marker({ size = 4, intensity = 1, current = false }: { size?: number; intensity?: number; current?: boolean }) {
  const op = current ? 1 : 0.25 + clamp01(intensity) * 0.75
  const span = 6 * size
  return (
    <svg width={span} height={span} viewBox={`${-span / 2} ${-span / 2} ${span} ${span}`} shapeRendering="crispEdges" aria-hidden>
      {PIXELS.map(([x, y], k) => (
        <rect key={k} x={x * size} y={y * size} width={size} height={size} fill="#E4DCCB" fillOpacity={op} />
      ))}
      {current && <rect x={-size / 2} y={-size / 2} width={size} height={size} fill="#14130F" />}
    </svg>
  )
}
