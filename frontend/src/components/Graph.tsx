import { useEffect, useRef, useState, type CSSProperties } from 'react'
import * as d3 from 'd3'
import type { GraphData, GraphNode, GraphEdge, Lens } from '../types'
import { mds2D } from '../kernel'
import { makeFieldRenderer, type FieldRenderer } from './ascii/field'
import { Panel, Bar, Readout, pct } from './ascii'
import { FILLED, LIGHT } from './ascii/glyphs'

// Pixel-circle geometry — the node body stays pixel-art (identity continuity).
// Large (current user): spans [-14,+14]
const LARGE_PIXELS = [
  { x: -6, y: -14, w: 12, h: 4 }, { x: -10, y: -10, w: 20, h: 4 },
  { x: -14, y: -6, w: 28, h: 4 }, { x: -14, y: -2, w: 28, h: 4 },
  { x: -14, y: 2, w: 28, h: 4 }, { x: -10, y: 6, w: 20, h: 4 },
  { x: -6, y: 10, w: 12, h: 4 },
] as const
// Small (friends): spans [-10,+10]
const SMALL_PIXELS = [
  { x: -6, y: -10, w: 12, h: 4 }, { x: -10, y: -6, w: 20, h: 4 },
  { x: -10, y: -2, w: 20, h: 4 }, { x: -10, y: 2, w: 20, h: 4 },
  { x: -6, y: 6, w: 12, h: 4 },
] as const
const LARGE_RING_PIXELS = [
  { x: -6, y: -18, w: 12, h: 4 }, { x: -14, y: -14, w: 8, h: 4 }, { x: 6, y: -14, w: 8, h: 4 },
  { x: -18, y: -10, w: 4, h: 24 }, { x: 14, y: -10, w: 4, h: 24 },
  { x: -14, y: 10, w: 8, h: 4 }, { x: 6, y: 10, w: 8, h: 4 }, { x: -6, y: 14, w: 12, h: 4 },
] as const

type SimNode = d3.SimulationNodeDatum & GraphNode & { tx: number; ty: number; ghost: boolean }
type SimLink = {
  source: SimNode; target: SimNode; edge: GraphEdge; archArch: boolean
  // the value the current lens reads off this edge; null = the lens has no data here
  sim: number | null
}

interface Props {
  data: GraphData | null
  lens: Lens
  leftPanelOpen?: boolean
}

const nSize = (d: GraphNode) => (d.isCurrentUser ? 14 : 10)

// Palette: a restrained two-tone system on warm near-black. People are rendered in bone
// (you = bright, friends = bone dimmed by similarity); archetype landmarks are a muted gold
// and a hollow-diamond shape so they read as fixtures, not friends. No neon.
const BONE = '#ECE4D2'          // you / primary ink
const BONE_RGB = '212,205,188'  // friends (used as rgba with similarity opacity)
const ARCHETYPE_COLOR = '#C9A24B'
const INK_DIM = '#7E7A6E'
const isArchetype = (d: GraphNode) => d.kind === 'archetype'
const diamondPath = (r: number) => `M0,${-r}L${r},0L0,${r}L${-r},0Z`

const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x)

/** The value the lens reads off an edge: the calibrated blend, or one raw facet. */
function lensSim(e: GraphEdge, lens: Lens): number | null {
  if (lens === 'blend') return e.similarity
  const v = e.facets?.[lens]
  return v == null ? null : v
}

const LENS_LABEL: Record<Lens, string> = {
  blend: 'match', artist: 'artists', genre: 'genres', lyric: 'themes',
}

// the lens-relevant subset of the scene, rebuilt on every lens switch
interface Scene {
  sim: d3.Simulation<SimNode, undefined>
  nodes: SimNode[]
  links: SimLink[]
  edgeSel: d3.Selection<SVGLineElement, SimLink, SVGGElement, unknown>
  nodeSel: d3.Selection<SVGGElement, SimNode, SVGGElement, unknown>
  ringLabels: d3.Selection<SVGTextElement, { frac: number }, SVGGElement, unknown>
  cx: number
  cy: number
  rMax: number
  transform: d3.ZoomTransform
  field: FieldRenderer | null
  closeness: Map<string, number>
}

// base resting opacity for an edge (used on paint and on mouseleave)
const edgeBaseOp = (d: SimLink) => {
  const s = d.sim ?? 0
  return d.archArch ? 0.05 + s * 0.12 : 0.22 + s * 0.5
}
const edgeWidth = (d: SimLink) => 1 + (d.sim ?? 0) * 2

export default function Graph({ data, lens, leftPanelOpen = false }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sceneRef = useRef<Scene | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null)
  const [edgeTip, setEdgeTip] = useState<{ x: number; y: number; sim: number } | null>(null)
  // lens-similarity-to-you, for node opacity + the node card (state so panels re-render on lens switch)
  const [simToYou, setSimToYou] = useState<Map<string, number>>(new Map())

  // ── effect A: build the scene (DOM, forces, zoom, field) — runs only when data changes ──
  useEffect(() => {
    if (!svgRef.current) return
    const svgEl = svgRef.current
    const svg = d3.select(svgEl)
    svg.selectAll('*').remove()
    sceneRef.current?.field?.clear()
    sceneRef.current = null
    setSelectedNode(null)
    setSelectedEdge(null)
    setEdgeTip(null)
    if (!data || data.nodes.length === 0) return

    const { width, height } = svgEl.getBoundingClientRect()
    const g = svg.append('g')

    const cx = width / 2, cy = height / 2
    const pad = 64
    const rMax = Math.min(width, height) / 2 - pad

    // camera: bounded. translateExtent stops the map leaving the frame; scaleExtent's floor stops
    // zooming out into the void. Zoom redraws the field so the glyph raster tracks the camera.
    const margin = 56
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.8, 4])
      .translateExtent([[cx - rMax - margin, cy - rMax - margin], [cx + rMax + margin, cy + rMax + margin]])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
        if (sceneRef.current) {
          sceneRef.current.transform = event.transform
          drawField()
        }
      })
    svg.call(zoom)

    // ego rings: the legend made geometry — concentric guides under the map. Drawn once;
    // labels are retitled per lens (absolute % when calibrated, near→far otherwise).
    const ringG = g.append('g').attr('class', 'ego-rings').style('pointer-events', 'none')
    const ringSpecs = [{ frac: 1 }, { frac: 0.75 }, { frac: 0.5 }, { frac: 0.25 }]
    let ringLabels: Scene['ringLabels'] = ringG.selectAll('text')
    if (data.nodes.length > 1) {
      ringSpecs.forEach((s, i) => {
        ringG.append('circle').attr('cx', cx).attr('cy', cy).attr('r', s.frac * rMax)
          .attr('fill', 'none').attr('stroke', INK_DIM)
          .attr('stroke-opacity', i === 0 ? 0.22 : 0.13)
          .attr('stroke-dasharray', i === 0 ? 'none' : '2,6')
      })
      ringLabels = ringG.selectAll<SVGTextElement, { frac: number }>('text')
        .data(ringSpecs).enter().append('text')
        .attr('x', cx).attr('y', (s) => cy - s.frac * rMax - 5)
        .attr('text-anchor', 'middle').attr('fill', INK_DIM).attr('fill-opacity', 0.55)
        .attr('font-size', '9').attr('font-family', "'JetBrains Mono', monospace")
        .attr('letter-spacing', '0.5')
    }

    const nodes: SimNode[] = data.nodes.map((nd) => ({
      ...nd, x: cx, y: cy, tx: cx, ty: cy, ghost: false,
    }))
    const you = nodes.find((nd) => nd.isCurrentUser)
    if (you) { you.fx = cx; you.fy = cy }   // pin the origin so the rings stay honest
    const byId = new Map(nodes.map((nd) => [nd.userId, nd]))
    const links: SimLink[] = data.edges
      .filter((e) => byId.has(e.source as string) && byId.has(e.target as string))
      .map((e) => ({
        source: byId.get(e.source as string)!, target: byId.get(e.target as string)!,
        edge: e, sim: e.similarity,
        // archetype↔archetype edges anchor the MDS map but aren't the point — draw them faint.
        archArch: isArchetype(byId.get(e.source as string)!) && isArchetype(byId.get(e.target as string)!),
      }))

    // force: anchor to MDS target + de-overlap. No center/charge — MDS owns the geometry.
    // On a lens switch only tx/ty change and alpha is re-warmed, so nodes *glide* — you can
    // track who moved and how far. Motion is the diff between two honest layouts.
    const sim = d3.forceSimulation<SimNode>(nodes)
      .force('x', d3.forceX<SimNode>((d) => d.tx).strength(0.55))
      .force('y', d3.forceY<SimNode>((d) => d.ty).strength(0.55))
      .force('collide', d3.forceCollide<SimNode>((d) => nSize(d) + 22))
      .alpha(0)

    // ── edges ──
    const edgeSel = g.append('g').selectAll<SVGLineElement, SimLink>('line')
      .data(links).enter().append('line')
      .attr('stroke-linecap', 'square')
      .style('cursor', 'pointer')
      .on('mouseenter', function (event: MouseEvent, d) {
        if (d.sim == null) return
        d3.select(this).attr('stroke-opacity', 1).attr('stroke-width', d.sim * 2 + 2.5)
        const r = svgEl.getBoundingClientRect()
        setEdgeTip({ x: event.clientX - r.left, y: event.clientY - r.top, sim: d.sim })
      })
      .on('mousemove', function (event: MouseEvent) {
        const r = svgEl.getBoundingClientRect()
        setEdgeTip((p) => (p ? { ...p, x: event.clientX - r.left, y: event.clientY - r.top } : null))
      })
      .on('mouseleave', function (_, d) {
        d3.select(this).attr('stroke-opacity', edgeBaseOp(d)).attr('stroke-width', edgeWidth(d))
        setEdgeTip(null)
      })
      .on('click', (event: MouseEvent, d) => { event.stopPropagation(); setSelectedEdge(d.edge); setSelectedNode(null) })

    // ── nodes ──
    const nodeSel = g.append('g').selectAll<SVGGElement, SimNode>('g')
      .data(nodes).enter().append('g')
      .style('cursor', 'pointer')
      .call(d3.drag<SVGGElement, SimNode>()
        // you stay pinned at the origin — dragging the center would break the ring readout
        .on('start', (event, d) => { if (d.isCurrentUser) return; if (!event.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
        .on('drag', (event, d) => { if (d.isCurrentUser) return; d.fx = event.x; d.fy = event.y })
        .on('end', (event, d) => { if (d.isCurrentUser) return; if (!event.active) sim.alphaTarget(0); d.fx = null; d.fy = null }))
      .on('click', (event: MouseEvent, d) => { event.stopPropagation(); setSelectedNode(d); setSelectedEdge(null) })

    nodeSel.append('circle').attr('r', (d) => nSize(d) + 6).attr('fill', 'transparent')

    nodeSel.filter((d) => d.lyricStatus === 'ready' && d.isCurrentUser).each(function () {
      const group = d3.select(this)
      LARGE_RING_PIXELS.forEach((p) => group.append('rect')
        .attr('x', p.x).attr('y', p.y).attr('width', p.w).attr('height', p.h)
        .attr('fill', BONE).attr('fill-opacity', 0.22).attr('shape-rendering', 'crispEdges')
        .style('pointer-events', 'none'))
    })

    nodeSel.each(function (d) {
      const group = d3.select<SVGGElement, SimNode>(this as SVGGElement)
      if (isArchetype(d)) {
        // hollow gold diamond + a small core pip; brightness tracks match-with-you (set per lens)
        group.append('path').attr('class', 'arch-body').attr('d', diamondPath(12))
          .attr('fill', 'rgba(201,162,75,0.05)').attr('stroke', ARCHETYPE_COLOR)
          .attr('stroke-width', 1.5)
          .attr('shape-rendering', 'geometricPrecision').style('pointer-events', 'none')
        group.append('rect').attr('class', 'arch-pip').attr('x', -2).attr('y', -2).attr('width', 4).attr('height', 4)
          .attr('fill', ARCHETYPE_COLOR)
          .attr('shape-rendering', 'crispEdges').style('pointer-events', 'none')
        return
      }
      const pixels = d.isCurrentUser ? LARGE_PIXELS : SMALL_PIXELS
      pixels.forEach((p) => group.append('rect').attr('class', 'px')
        .attr('x', p.x).attr('y', p.y).attr('width', p.w).attr('height', p.h)
        .attr('fill', d.isCurrentUser ? BONE : `rgba(${BONE_RGB},1)`)
        .attr('shape-rendering', 'crispEdges').style('pointer-events', 'none'))
    })

    nodeSel.filter((d) => d.isCurrentUser).append('text')
      .text((d) => initials(d.displayName))
      .attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
      .attr('fill', '#14130F').attr('font-size', '9').attr('font-weight', '700')
      .attr('font-family', "'JetBrains Mono', monospace").style('pointer-events', 'none').style('user-select', 'none')

    nodeSel.append('text')
      .text((d) => (isArchetype(d) ? d.displayName : d.displayName.split(' ')[0]))
      .attr('text-anchor', 'middle').attr('y', (d) => nSize(d) + 15)
      .attr('fill', (d) => (isArchetype(d) ? 'rgba(201,162,75,0.78)' : 'rgba(236,228,210,0.74)'))
      .attr('font-size', (d) => (isArchetype(d) ? '9' : '10'))
      .attr('font-family', "'JetBrains Mono', monospace").attr('letter-spacing', '0.5')
      .style('pointer-events', 'none').style('user-select', 'none')

    const field = canvasRef.current ? makeFieldRenderer(canvasRef.current) : null

    sim.on('tick', () => {
      edgeSel
        .attr('x1', (d) => d.source.x!).attr('y1', (d) => d.source.y!)
        .attr('x2', (d) => d.target.x!).attr('y2', (d) => d.target.y!)
      nodeSel.attr('transform', (d) => `translate(${d.x},${d.y})`)
      drawField()
    })

    sceneRef.current = {
      sim, nodes, links, edgeSel, nodeSel, ringLabels,
      cx, cy, rMax, transform: d3.zoomIdentity, field, closeness: new Map(),
    }

    return () => { sim.stop(); sceneRef.current = null }
  }, [data])

  // the ASCII similarity field: every node paints a halo ∝ its real closeness-with-you; the
  // kernel takes the max per cell so crowding can't fake strength. Redrawn on tick + zoom.
  function drawField() {
    const s = sceneRef.current
    if (!s || !s.field) return
    const xs: number[] = [], ys: number[] = [], vals: number[] = []
    for (const nd of s.nodes) {
      if (nd.ghost) continue
      const v = nd.isCurrentUser ? 1 : (s.closeness.get(nd.userId) ?? 0)
      if (v <= 0) continue
      xs.push(s.transform.applyX(nd.x ?? s.cx))
      ys.push(s.transform.applyY(nd.y ?? s.cy))
      vals.push(v)
    }
    s.field.draw(xs, ys, vals, s.rMax * 0.35 * s.transform.k)
  }

  // ── effect B: apply the lens — retarget the layout and glide. No DOM teardown. ──
  useEffect(() => {
    const s = sceneRef.current
    if (!s || !data) return
    const { nodes, links, cx, cy, rMax } = s

    for (const l of links) l.sim = lensSim(l.edge, lens)

    const you = nodes.find((nd) => nd.isCurrentUser)
    const opMap = new Map<string, number>()
    if (you) {
      for (const l of links) {
        if (l.sim == null) continue
        if (l.source.userId === you.userId) opMap.set(l.target.userId, Math.max(opMap.get(l.target.userId) || 0, l.sim))
        else if (l.target.userId === you.userId) opMap.set(l.source.userId, Math.max(opMap.get(l.source.userId) || 0, l.sim))
      }
    }
    setSimToYou(opMap)

    // a node is a ghost on this lens when *no* edge carries the facet for it — “no data”,
    // which is different from “0% match”, so it parks outside the boundary ring instead.
    for (const nd of nodes) {
      nd.ghost = !nd.isCurrentUser &&
        !links.some((l) => l.sim != null && (l.source === nd || l.target === nd))
    }
    const active = nodes.filter((nd) => !nd.ghost)

    // closeness ∈ [0,1] drives the radius (1 = center). Blend lens + calibrated → absolute
    // match. Otherwise spread the scores present across the radius so the *ranking* is
    // legible — relative to the field, not an absolute %. Panels always show the raw number.
    const calibrated = !!data.calibrated && lens === 'blend'
    const others = active.filter((nd) => !nd.isCurrentUser)
    const closeness = new Map<string, number>()
    if (calibrated) {
      for (const nd of others) closeness.set(nd.userId, opMap.get(nd.userId) || 0)
    } else {
      let lo = Infinity, hi = -Infinity
      for (const nd of others) { const m = opMap.get(nd.userId) || 0; lo = Math.min(lo, m); hi = Math.max(hi, m) }
      const span = hi - lo
      for (const nd of others) {
        const t = span > 1e-6 ? ((opMap.get(nd.userId) || 0) - lo) / span : 0.5
        closeness.set(nd.userId, 0.1 + t * 0.82)   // band keeps the best off-center and the worst off the rim
      }
    }
    s.closeness = closeness

    // ego-centric layout: YOU are the origin; radius = (1 − closeness)·rMax ("how unlike me"),
    // angle = MDS bearing around the active cloud's centroid (genre families still cluster).
    const idx = new Map(active.map((nd, i) => [nd.userId, i]))
    const n = active.length
    const D = Array.from({ length: n }, () => Array(n).fill(1))
    for (let i = 0; i < n; i++) D[i][i] = 0
    for (const l of links) {
      if (l.sim == null) continue
      const i = idx.get(l.source.userId)
      const j = idx.get(l.target.userId)
      if (i == null || j == null) continue
      const d = 1 - clamp01(l.sim)
      D[i][j] = d
      D[j][i] = d
    }
    const coords = mds2D(D)
    let mx = 0, my = 0
    for (const [x, y] of coords) { mx += x; my += y }
    mx /= n || 1; my /= n || 1

    active.forEach((nd, i) => {
      if (nd.isCurrentUser) { nd.tx = cx; nd.ty = cy; return }
      const r = (1 - clamp01(closeness.get(nd.userId) ?? 0)) * rMax
      const ang = Math.atan2(coords[i][1] - my, coords[i][0] - mx)
      nd.tx = cx + r * Math.cos(ang)
      nd.ty = cy + r * Math.sin(ang)
    })
    // ghosts park just past the boundary ring, keeping their bearing so they don't teleport
    nodes.forEach((nd, i) => {
      if (!nd.ghost) return
      const dx = (nd.x ?? cx) - cx, dy = (nd.y ?? cy) - cy
      const ang = dx * dx + dy * dy > 1 ? Math.atan2(dy, dx) : i * 2.39996  // golden-angle fan for fresh scenes
      nd.tx = cx + (rMax + 30) * Math.cos(ang)
      nd.ty = cy + (rMax + 30) * Math.sin(ang)
    })

    // restyle edges/nodes for the lens
    s.edgeSel
      .style('display', (d) => (d.sim == null ? 'none' : null))
      .attr('stroke', (d) => (d.archArch ? ARCHETYPE_COLOR : edgeColor(d.sim ?? 0)))
      .attr('stroke-width', edgeWidth)
      .attr('stroke-opacity', edgeBaseOp)
      .attr('stroke-dasharray', (d) => (d.archArch ? '2,4' : 'none'))

    const nodeOpacity = (id: string) => 0.18 + (opMap.get(id) || 0) * 0.82
    s.nodeSel
      .style('opacity', (d) => (d.ghost ? 0.3 : 1))
      .each(function (d) {
        const group = d3.select(this)
        if (isArchetype(d)) {
          const op = d.ghost ? 0.3 : 0.35 + (opMap.get(d.userId) || 0) * 0.65
          group.select('.arch-body').attr('stroke-opacity', op)
          group.select('.arch-pip').attr('fill-opacity', op)
          return
        }
        if (!d.isCurrentUser) {
          group.selectAll('.px').attr('fill', `rgba(${BONE_RGB},${d.ghost ? 0.45 : nodeOpacity(d.userId)})`)
        }
      })

    // ring labels: absolute % only when the numbers really are calibrated percentiles
    const labels = calibrated ? ['0%', '25%', '50%', '75%'] : ['far', '', '', 'near']
    s.ringLabels.text((_, i) => labels[i] ?? '')

    s.sim.alpha(0.9).restart()
  }, [data, lens])

  const nodes = data?.nodes ?? []
  const friendCount = nodes.filter((n) => !n.isCurrentUser && !isArchetype(n)).length
  const hasArchetypes = nodes.some((n) => isArchetype(n))
  const solo = nodes.length <= 1
  const calibrated = !!data?.calibrated && lens === 'blend'
  const youNode = nodes.find((n) => n.isCurrentUser) ?? null
  const nodeOf = (id: string) => data?.nodes.find((nd) => nd.userId === id) ?? null
  const nameOf = (id: string) => {
    const n = nodeOf(id)
    if (!n) return id.slice(0, 6)
    return isArchetype(n) ? n.displayName : n.displayName.split(' ')[0]
  }
  // a lens with zero scored edges (e.g. themes before anyone's lyrics are in) — say so
  const lensEmpty = !solo && lens !== 'blend' &&
    !(data?.edges ?? []).some((e) => e.facets && lens in e.facets)

  return (
    <>
      <canvas ref={canvasRef}
              style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }} />
      <svg ref={svgRef} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
           onClick={() => { setSelectedEdge(null); setSelectedNode(null) }} />

      {solo && (
        <div className="graph-hint">
          <p>Add friends to see how your<br />music taste connects.</p>
        </div>
      )}

      {!solo && friendCount === 0 && hasArchetypes && <EphemeralNote />}

      {lensEmpty && (
        <div className="graph-hint">
          <p>no {LENS_LABEL[lens]} data on this lens yet —<br />nodes without it wait outside the rim.</p>
        </div>
      )}

      {!solo && (
        <div style={{
          // slides clear of the profile panel (x: 16→284) when it opens, instead of hiding under it
          position: 'absolute', top: 18, left: leftPanelOpen ? 300 : 18, zIndex: 14,
          fontFamily: "'JetBrains Mono', monospace", fontSize: 10, lineHeight: 1.8,
          color: INK_DIM, letterSpacing: 0.4, pointerEvents: 'none',
          transition: 'left 0.28s cubic-bezier(0.4, 0, 0.2, 1)',
        }}>
          <div><span style={{ color: BONE }}>■</span> you · the center</div>
          <div><span style={{ color: BONE, opacity: 0.5 }}>■</span> friends</div>
          {hasArchetypes && <div><span style={{ color: ARCHETYPE_COLOR }}>◇</span> taste archetypes</div>}
          <div style={{ marginTop: 6, opacity: 0.85 }}>
            <span style={{ letterSpacing: 0 }}>◯</span> {calibrated ? 'rings · % match with you' : 'rings · closeness (relative)'}
          </div>
          {lens !== 'blend' && (
            <div style={{ opacity: 0.85 }}>
              <span style={{ letterSpacing: 0 }}>◌</span> outside the rim · no {LENS_LABEL[lens]} data
            </div>
          )}
          <div style={{ opacity: 0.85 }}>
            <span style={{ letterSpacing: 0 }}>░</span> field · glow = closeness
          </div>
        </div>
      )}

      {edgeTip && (
        <div style={{
          position: 'absolute', left: edgeTip.x, top: edgeTip.y - 34, transform: 'translateX(-50%)',
          background: 'rgba(13,12,11,0.95)', border: '1px solid rgba(201,162,75,0.3)', borderRadius: 2,
          padding: '3px 10px', fontSize: 11, fontFamily: "'JetBrains Mono', monospace", fontWeight: 500,
          color: '#E4DCCB', pointerEvents: 'none', whiteSpace: 'nowrap', zIndex: 20,
        }}>
          {LENS_LABEL[lens]} {pct(edgeTip.sim)} <span style={{ color: INK_DIM }}>· click to explain</span>
        </div>
      )}

      {selectedEdge && (
        <EdgeBreakdown edge={selectedEdge}
                       a={nodeOf(selectedEdge.source as string)} b={nodeOf(selectedEdge.target as string)}
                       aName={nameOf(selectedEdge.source as string)} bName={nameOf(selectedEdge.target as string)}
                       onClose={() => setSelectedEdge(null)} />
      )}

      {selectedNode && (
        <NodeCard node={selectedNode} you={youNode} simToYou={simToYou.get(selectedNode.userId)}
                  lens={lens} onClose={() => setSelectedNode(null)} />
      )}
    </>
  )
}

// ── intro note: types itself in, holds, then unwrites — once per session, for a clean canvas ──
let notePlayed = false
const NOTE = "No friends yet — you're plotted against taste archetypes (◇). Add friends to compare with real people."

function EphemeralNote() {
  const [n, setN] = useState(0)
  const [phase, setPhase] = useState<'typing' | 'holding' | 'erasing' | 'done'>(
    () => (notePlayed ? 'done' : 'typing'),
  )

  // timers are keyed on `phase` and use functional updates, so React 18 StrictMode's
  // setup→cleanup→setup double-invoke just restarts cleanly instead of freezing.
  useEffect(() => {                                   // type in (~45ms/char)
    if (phase !== 'typing') return
    const t = setInterval(() => setN((x) => Math.min(x + 1, NOTE.length)), 45)
    return () => clearInterval(t)
  }, [phase])

  useEffect(() => {                                   // unwrite (~25ms/char)
    if (phase !== 'erasing') return
    const e = setInterval(() => setN((x) => Math.max(x - 1, 0)), 25)
    return () => clearInterval(e)
  }, [phase])

  useEffect(() => {                                   // hold once fully typed (~3.5s), then erase
    if (phase !== 'holding') return
    const h = setTimeout(() => setPhase('erasing'), 3500)
    return () => clearTimeout(h)
  }, [phase])

  // phase transitions driven by progress (total visible ≈ 10s, then gone for good this session)
  useEffect(() => {
    if (phase === 'typing' && n >= NOTE.length) setPhase('holding')
    if (phase === 'erasing' && n <= 0) { setPhase('done'); notePlayed = true }
  }, [phase, n])

  if (phase === 'done') return null
  const active = phase === 'typing' || phase === 'erasing'
  // top-center band, clear of the origin node and the rings — mono to match the canvas.
  return (
    <div style={{
      position: 'absolute', top: 26, left: '50%', transform: 'translateX(-50%)', zIndex: 14,
      maxWidth: 440, textAlign: 'center', pointerEvents: 'none',
      fontFamily: "'JetBrains Mono', monospace", fontSize: 11, lineHeight: 1.7,
      letterSpacing: 0.3, color: 'rgba(236,228,210,0.62)',
    }}>
      <span className={active ? 'ascii-cursor' : ''}>{NOTE.slice(0, n)}</span>
    </div>
  )
}

// ── comparative imagery: mirrored you◄►them genre histogram (the picture IS the explanation) ──
const MIRROR_CELLS = 7

function MirrorBars({ a, b, aName, bName }: { a: GraphNode; b: GraphNode; aName: string; bName: string }) {
  const la = a.topGenres ?? []
  const lb = b.topGenres ?? []
  if (la.length === 0 && lb.length === 0) return null
  const wa = new Map(la), wb = new Map(lb)
  const genres = [...new Set([...wa.keys(), ...wb.keys()])]
    .sort((g, h) => ((wa.get(h) ?? 0) + (wb.get(h) ?? 0)) - ((wa.get(g) ?? 0) + (wb.get(g) ?? 0)))
    .slice(0, 6)
  const max = Math.max(...genres.map((g) => Math.max(wa.get(g) ?? 0, wb.get(g) ?? 0)), 1e-9)
  const cellsOf = (w?: number) => (w == null ? 0 : Math.max(w > 0 ? 1 : 0, Math.round((w / max) * MIRROR_CELLS)))
  const row: CSSProperties = {
    display: 'grid', gridTemplateColumns: `${MIRROR_CELLS}ch 1fr ${MIRROR_CELLS}ch`, gap: 8,
    fontSize: 11, lineHeight: 1.9, whiteSpace: 'pre', alignItems: 'center',
  }
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ ...row, color: INK_DIM, fontSize: 9, letterSpacing: 1, textTransform: 'uppercase' }}>
        <span style={{ textAlign: 'right', color: BONE }}>{aName}</span>
        <span style={{ textAlign: 'center' }}>genres</span>
        <span style={{ color: ARCHETYPE_COLOR }}>{bName}</span>
      </div>
      {genres.map((gname) => {
        const lc = cellsOf(wa.get(gname))
        const rc = cellsOf(wb.get(gname))
        return (
          <div key={gname} style={row}>
            <span style={{ textAlign: 'right' }}>
              <span style={{ color: 'rgba(236,228,210,0.16)' }}>{LIGHT.repeat(MIRROR_CELLS - lc)}</span>
              <span style={{ color: BONE }}>{FILLED.repeat(lc)}</span>
            </span>
            <span style={{ textAlign: 'center', color: INK_DIM, overflow: 'hidden', textOverflow: 'ellipsis' }}>{gname}</span>
            <span>
              <span style={{ color: ARCHETYPE_COLOR }}>{FILLED.repeat(rc)}</span>
              <span style={{ color: 'rgba(236,228,210,0.16)' }}>{LIGHT.repeat(MIRROR_CELLS - rc)}</span>
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ── V2: edge breakdown = comparative imagery (the explanation IS the picture) ───
function EdgeBreakdown({ edge, a, b, aName, bName, onClose }: {
  edge: GraphEdge; a: GraphNode | null; b: GraphNode | null; aName: string; bName: string; onClose: () => void
}) {
  const facets = edge.facets || {}
  const weights = edge.weights || {}
  const order = ['artist', 'genre', 'lyric'].filter((k) => k in facets)
  const labelMap: Record<string, string> = { artist: 'artists', genre: 'genres', lyric: 'themes' }
  const sharedArtists = a?.topArtists && b?.topArtists
    ? a.topArtists.filter((x) => b.topArtists!.includes(x)).slice(0, 4)
    : []
  return (
    <div style={{ position: 'absolute', left: 16, bottom: 28, zIndex: 16, width: 340 }}>
      <Panel
        title={`echo · ${aName} ✕ ${bName}`}
        right={<span style={{ color: ARCHETYPE_COLOR }}>{pct(edge.similarity)}</span>}
      >
        {order.length > 0 ? (
          order.map((k) => (
            <Bar key={k} label={labelMap[k] || k} value={facets[k]} weight={weights[k]} />
          ))
        ) : (
          <div style={{ color: INK_DIM, fontSize: 11 }}>no facet breakdown on this edge yet.</div>
        )}
        {a && b && <MirrorBars a={a} b={b} aName={aName} bName={bName} />}
        {sharedArtists.length > 0 && (
          <div style={{ marginTop: 8, fontSize: 11, color: INK_DIM }}>
            shared artists · <span style={{ color: BONE }}>{sharedArtists.join(', ')}</span>
          </div>
        )}
        <div style={{ height: 8 }} />
        {edge.blended != null && <Readout label="blended (raw)" value={edge.blended.toFixed(2)} />}
        <Readout label="match (calibrated)" value={pct(edge.similarity)} />
        <button onClick={onClose} style={closeBtn}>close ▢</button>
      </Panel>
    </div>
  )
}

// ── V3: node card — taste summary + what you share ─────────────
function NodeCard({ node, you, simToYou, lens, onClose }: {
  node: GraphNode; you: GraphNode | null; simToYou?: number; lens: Lens; onClose: () => void
}) {
  const arch = node.kind === 'archetype'
  const status = arch ? 'taste archetype · genre-defined'
    : node.lyricStatus === 'ready' ? 'themes ready'
    : node.lyricStatus === 'pending' ? 'computing themes…'
    : node.hasProfile ? 'profile only' : 'no profile yet'
  const title = arch ? 'landmark · archetype' : node.isCurrentUser ? 'node · you' : 'node'
  const accent = arch ? ARCHETYPE_COLOR : BONE
  const genres = (node.topGenres ?? []).slice(0, 5)
  const gMax = Math.max(...genres.map(([, w]) => w), 1e-9)
  const isOther = !node.isCurrentUser && you != null
  const sharedGenres = isOther && node.topGenres && you.topGenres
    ? node.topGenres.filter(([g]) => you.topGenres!.some(([h]) => h === g)).map(([g]) => g).slice(0, 4)
    : []
  const sharedArtists = isOther && node.topArtists && you.topArtists
    ? node.topArtists.filter((x) => you.topArtists!.includes(x)).slice(0, 4)
    : []
  return (
    <div style={{ position: 'absolute', left: '50%', bottom: 80, transform: 'translateX(-50%)', zIndex: 16, width: 300 }}>
      <Panel title={title}
             right={<span style={{ color: INK_DIM }}>{node.spotifyId || ''}</span>}>
        <div style={{ fontSize: 14, color: accent, marginBottom: 8, letterSpacing: 0.3 }}>{node.displayName}</div>
        {arch && node.description && (
          <div style={{ fontSize: 11, color: '#9A9486', marginBottom: 10, lineHeight: 1.5 }}>{node.description}</div>
        )}
        {genres.length > 0 && (
          <div style={{ marginBottom: 8 }}>
            {genres.map(([g, w]) => (
              <Bar key={g} label={g} value={w / gMax} width={12} />
            ))}
          </div>
        )}
        {(node.topArtists?.length ?? 0) > 0 && (
          <div style={{ fontSize: 11, color: INK_DIM, marginBottom: 8 }}>
            plays · <span style={{ color: BONE }}>{node.topArtists!.join(', ')}</span>
          </div>
        )}
        {!node.isCurrentUser && simToYou != null && (
          <Readout label={`${LENS_LABEL[lens]} with you`} value={pct(simToYou)} />
        )}
        {sharedGenres.length > 0 && <Readout label="shared genres" value={sharedGenres.join(', ')} width={34} />}
        {sharedArtists.length > 0 && <Readout label="shared artists" value={sharedArtists.join(', ')} width={34} />}
        <Readout label="status" value={status} />
        <button onClick={onClose} style={closeBtn}>close ▢</button>
      </Panel>
    </div>
  )
}

const closeBtn: CSSProperties = {
  marginTop: 12, background: 'transparent', border: '1px solid rgba(236,228,210,0.18)', color: '#7E7A6E',
  fontFamily: "'JetBrains Mono', monospace", fontSize: 10, padding: '4px 10px', cursor: 'pointer',
  letterSpacing: 1, textTransform: 'uppercase',
}

function initials(name: string): string {
  return name.split(/\s+/).map((w) => w[0] ?? '').join('').slice(0, 2).toUpperCase()
}

function edgeColor(sim: number): string {
  // warm grey -> bone as the match strengthens (luminance carries it, not hue)
  if (sim >= 0.75) return '#C9C0AC'
  if (sim >= 0.55) return '#8A8270'
  if (sim >= 0.35) return '#5C564B'
  return '#383229'
}
