/**
 * field — the ASCII similarity field, the canvas under the graph.
 *
 * Renders the interpolated "match with you" as a dithered glyph raster: every node paints a
 * halo proportional to its *real* similarity-with-you; the field takes the max (never the
 * sum), so brightness is an honest, readable quantity — where the canvas glows, taste like
 * yours lives. The scalar math is `fieldGrid` in the kernel (Rust→WASM when built, TS
 * otherwise); this module only owns the canvas: glyph sprites, DPR scaling, drawing.
 */
import { fieldGrid } from '../../kernel'

/** Glyph ramp, silence → presence. Index = dither level from the kernel. */
export const FIELD_RAMP = [' ', '·', ':', '░', '▒', '▓'] as const

const INK = '#ECE4D2'
// alpha per level — quiet enough to stay a backdrop, stepped so levels read
const LEVEL_ALPHA = [0, 0.05, 0.07, 0.09, 0.12, 0.16] as const

export interface FieldRenderer {
  /** Draw the field for nodes at *screen* coords with values in [0,1]. */
  draw(xs: number[], ys: number[], vals: number[], radius: number): void
  clear(): void
  resize(): void
}

/**
 * Bind a renderer to a canvas. `cell` is the glyph cell size in CSS px — the raster is
 * deliberately chunky; that's the pixel grid, not a perf hack (though it is also that).
 */
export function makeFieldRenderer(canvas: HTMLCanvasElement, cell = 14): FieldRenderer {
  const ctx = canvas.getContext('2d')
  let sprites: HTMLCanvasElement[] = []
  let dpr = 1

  function resize() {
    if (!ctx) return
    dpr = window.devicePixelRatio || 1
    const { width, height } = canvas.getBoundingClientRect()
    canvas.width = Math.max(1, Math.round(width * dpr))
    canvas.height = Math.max(1, Math.round(height * dpr))
    // pre-render one sprite per ramp level: fillText once here, drawImage on the hot path
    sprites = FIELD_RAMP.map((glyph, level) => {
      const s = document.createElement('canvas')
      s.width = Math.ceil(cell * dpr)
      s.height = Math.ceil(cell * dpr)
      const sctx = s.getContext('2d')
      if (sctx && glyph !== ' ' && level > 0) {
        sctx.globalAlpha = LEVEL_ALPHA[level] ?? 0.1
        sctx.fillStyle = INK
        sctx.font = `${Math.round(cell * 0.86 * dpr)}px 'JetBrains Mono', monospace`
        sctx.textAlign = 'center'
        sctx.textBaseline = 'middle'
        sctx.fillText(glyph, (cell * dpr) / 2, (cell * dpr) / 2)
      }
      return s
    })
  }

  function clear() {
    ctx?.clearRect(0, 0, canvas.width, canvas.height)
  }

  function draw(xs: number[], ys: number[], vals: number[], radius: number) {
    if (!ctx) return
    const w = canvas.width / dpr
    const h = canvas.height / dpr
    const cols = Math.ceil(w / cell)
    const rows = Math.ceil(h / cell)
    const grid = fieldGrid(xs, ys, vals, cols, rows, 0, 0, cell, cell, radius, FIELD_RAMP.length)
    clear()
    const px = cell * dpr
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const level = grid[r * cols + c]
        if (level > 0) ctx.drawImage(sprites[level], c * px, r * px)
      }
    }
  }

  resize()
  return { draw, clear, resize }
}
