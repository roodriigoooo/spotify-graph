import { useEffect, useRef, useState, type CSSProperties } from 'react'
import * as d3 from 'd3'
import type { GraphData, GraphNode, GraphEdge } from '../types'
import { mds2D } from '../kernel'
import { Panel, Bar, Readout, pct } from './ascii'

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

type SimNode = d3.SimulationNodeDatum & GraphNode & { mdsx: number; mdsy: number }
type SimLink = d3.SimulationLinkDatum<SimNode> & { similarity: number; edge: GraphEdge }

interface Props {
  data: GraphData | null
  mode: string
}

const nSize = (d: GraphNode) => (d.isCurrentUser ? 14 : 10)

/**
 * Honest layout: position by taste. We build the full pairwise dissimilarity matrix
 * (1 − similarity; unconnected pairs = 1) and run classical MDS so euclidean distance on
 * screen ≈ dissimilarity. Force only de-overlaps; forceX/Y anchor each node to its MDS
 * target, so on a mode switch nodes *glide* to their new honest coordinates.
 */
function layout(nodes: GraphNode[], edges: GraphEdge[], w: number, h: number) {
  const n = nodes.length
  const idx = new Map(nodes.map((nd, i) => [nd.userId, i]))
  const D = Array.from({ length: n }, () => Array(n).fill(1))
  for (let i = 0; i < n; i++) D[i][i] = 0
  for (const e of edges) {
    const i = idx.get(e.source as string)
    const j = idx.get(e.target as string)
    if (i == null || j == null) continue
    const d = 1 - Math.max(0, Math.min(1, e.similarity))
    D[i][j] = d
    D[j][i] = d
  }
  const coords = mds2D(D)
  let maxAbs = 1e-6
  for (const [x, y] of coords) maxAbs = Math.max(maxAbs, Math.abs(x), Math.abs(y))
  const pad = 90
  const scale = (Math.min(w, h) / 2 - pad) / maxAbs
  const cx = w / 2
  const cy = h / 2
  return coords.map(([x, y]) => ({ x: cx + x * scale, y: cy + y * scale }))
}

export default function Graph({ data, mode }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null)
  const [edgeTip, setEdgeTip] = useState<{ x: number; y: number; sim: number } | null>(null)

  // similarity-to-you, for node opacity + the node card
  const simToYou = useRef<Map<string, number>>(new Map())

  useEffect(() => {
    if (!svgRef.current) return
    const svgEl = svgRef.current
    const svg = d3.select(svgEl)
    svg.selectAll('*').remove()
    setSelectedNode(null)
    setSelectedEdge(null)
    setEdgeTip(null)
    if (!data || data.nodes.length === 0) return

    const { width, height } = svgEl.getBoundingClientRect()
    const g = svg.append('g')
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.15, 6])
      .on('zoom', (event) => g.attr('transform', event.transform))
    svg.call(zoom)

    const currentUserId = data.nodes.find((nd) => nd.isCurrentUser)?.userId
    const opMap = new Map<string, number>()
    if (currentUserId) {
      for (const e of data.edges) {
        if (e.source === currentUserId) opMap.set(e.target as string, Math.max(opMap.get(e.target as string) || 0, e.similarity))
        else if (e.target === currentUserId) opMap.set(e.source as string, Math.max(opMap.get(e.source as string) || 0, e.similarity))
      }
    }
    simToYou.current = opMap
    const nodeOpacity = (id: string) => 0.18 + (opMap.get(id) || 0) * 0.82

    // honest positions
    const pos = layout(data.nodes, data.edges, width, height)
    const nodes: SimNode[] = data.nodes.map((nd, i) => ({
      ...nd, x: pos[i].x, y: pos[i].y, mdsx: pos[i].x, mdsy: pos[i].y,
    }))
    const byId = new Map(nodes.map((nd) => [nd.userId, nd]))
    const links: SimLink[] = data.edges
      .filter((e) => byId.has(e.source as string) && byId.has(e.target as string))
      .map((e) => ({ source: e.source, target: e.target, similarity: e.similarity, edge: e }))

    // force: anchor to MDS target + de-overlap. No center/charge — MDS owns the geometry.
    const sim = d3.forceSimulation<SimNode>(nodes)
      .force('x', d3.forceX<SimNode>((d) => d.mdsx).strength(0.55))
      .force('y', d3.forceY<SimNode>((d) => d.mdsy).strength(0.55))
      .force('collide', d3.forceCollide<SimNode>((d) => nSize(d) + 22))
      .alpha(0.9)

    // ── edges ──
    const edgeSel = g.append('g').selectAll<SVGLineElement, SimLink>('line')
      .data(links).enter().append('line')
      .attr('stroke', (d) => edgeColor(d.similarity))
      .attr('stroke-width', (d) => 1 + d.similarity * 2)
      .attr('stroke-opacity', (d) => 0.22 + d.similarity * 0.5)
      .attr('stroke-linecap', 'square')
      .style('cursor', 'pointer')
      .on('mouseenter', function (event: MouseEvent, d) {
        d3.select(this).attr('stroke-opacity', 1).attr('stroke-width', d.similarity * 2 + 2.5)
        const r = svgEl.getBoundingClientRect()
        setEdgeTip({ x: event.clientX - r.left, y: event.clientY - r.top, sim: d.similarity })
      })
      .on('mousemove', function (event: MouseEvent) {
        const r = svgEl.getBoundingClientRect()
        setEdgeTip((p) => (p ? { ...p, x: event.clientX - r.left, y: event.clientY - r.top } : null))
      })
      .on('mouseleave', function (_, d) {
        d3.select(this).attr('stroke-opacity', 0.22 + d.similarity * 0.5).attr('stroke-width', 1 + d.similarity * 2)
        setEdgeTip(null)
      })
      .on('click', (event: MouseEvent, d) => { event.stopPropagation(); setSelectedEdge(d.edge); setSelectedNode(null) })

    // ── nodes ──
    const nodeSel = g.append('g').selectAll<SVGGElement, SimNode>('g')
      .data(nodes).enter().append('g')
      .style('cursor', 'pointer')
      .call(d3.drag<SVGGElement, SimNode>()
        .on('start', (event, d) => { if (!event.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
        .on('end', (event, d) => { if (!event.active) sim.alphaTarget(0); d.fx = null; d.fy = null }))
      .on('click', (event: MouseEvent, d) => { event.stopPropagation(); setSelectedNode(d); setSelectedEdge(null) })

    nodeSel.append('circle').attr('r', (d) => nSize(d) + 6).attr('fill', 'transparent')

    nodeSel.filter((d) => d.lyricStatus === 'ready' && d.isCurrentUser).each(function () {
      const group = d3.select(this)
      LARGE_RING_PIXELS.forEach((p) => group.append('rect')
        .attr('x', p.x).attr('y', p.y).attr('width', p.w).attr('height', p.h)
        .attr('fill', '#00FF41').attr('fill-opacity', 0.3).attr('shape-rendering', 'crispEdges')
        .style('pointer-events', 'none'))
    })

    nodeSel.each(function (d) {
      const group = d3.select<SVGGElement, SimNode>(this as SVGGElement)
      const pixels = d.isCurrentUser ? LARGE_PIXELS : SMALL_PIXELS
      const fill = d.isCurrentUser ? '#00FF41' : `rgba(0,255,65,${nodeOpacity(d.userId)})`
      pixels.forEach((p) => group.append('rect')
        .attr('x', p.x).attr('y', p.y).attr('width', p.w).attr('height', p.h)
        .attr('fill', fill).attr('shape-rendering', 'crispEdges').style('pointer-events', 'none'))
    })

    nodeSel.filter((d) => d.isCurrentUser).append('text')
      .text((d) => initials(d.displayName))
      .attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
      .attr('fill', '#000').attr('font-size', '9').attr('font-weight', '700')
      .attr('font-family', "'JetBrains Mono', monospace").style('pointer-events', 'none').style('user-select', 'none')

    nodeSel.append('text')
      .text((d) => d.displayName.split(' ')[0])
      .attr('text-anchor', 'middle').attr('y', (d) => nSize(d) + 15)
      .attr('fill', 'rgba(201,209,201,0.8)').attr('font-size', '10')
      .attr('font-family', "'JetBrains Mono', monospace").attr('letter-spacing', '0.5')
      .style('pointer-events', 'none').style('user-select', 'none')

    sim.on('tick', () => {
      edgeSel
        .attr('x1', (d) => (d.source as SimNode).x!).attr('y1', (d) => (d.source as SimNode).y!)
        .attr('x2', (d) => (d.target as SimNode).x!).attr('y2', (d) => (d.target as SimNode).y!)
      nodeSel.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })

    return () => { sim.stop() }
  }, [data, mode])

  const solo = !data || data.nodes.length <= 1
  const nameOf = (id: string) => data?.nodes.find((n) => n.userId === id)?.displayName.split(' ')[0] || id.slice(0, 6)

  return (
    <>
      <svg ref={svgRef} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
           onClick={() => { setSelectedEdge(null); setSelectedNode(null) }} />

      {solo && (
        <div className="graph-hint">
          <p>Add friends to see how your<br />music taste connects.</p>
        </div>
      )}

      {edgeTip && (
        <div style={{
          position: 'absolute', left: edgeTip.x, top: edgeTip.y - 34, transform: 'translateX(-50%)',
          background: 'rgba(8,11,8,0.95)', border: '1px solid rgba(0,255,65,0.25)', borderRadius: 2,
          padding: '3px 10px', fontSize: 11, fontFamily: "'JetBrains Mono', monospace", fontWeight: 500,
          color: '#00FF41', pointerEvents: 'none', whiteSpace: 'nowrap', zIndex: 20,
        }}>
          {pct(edgeTip.sim)} match <span style={{ color: '#5a6a5a' }}>· click to explain</span>
        </div>
      )}

      {selectedEdge && (
        <EdgeBreakdown edge={selectedEdge} a={nameOf(selectedEdge.source as string)}
                       b={nameOf(selectedEdge.target as string)} onClose={() => setSelectedEdge(null)} />
      )}

      {selectedNode && (
        <NodeCard node={selectedNode} simToYou={simToYou.current.get(selectedNode.userId)}
                  onClose={() => setSelectedNode(null)} />
      )}
    </>
  )
}

// ── V2: edge breakdown = comparative imagery (the explanation IS the picture) ───
function EdgeBreakdown({ edge, a, b, onClose }: { edge: GraphEdge; a: string; b: string; onClose: () => void }) {
  const facets = edge.facets || {}
  const weights = edge.weights || {}
  const order = ['artist', 'genre', 'lyric'].filter((k) => k in facets)
  const labelMap: Record<string, string> = { artist: 'artists', genre: 'genres', lyric: 'themes' }
  return (
    <div style={{ position: 'absolute', left: 16, bottom: 28, zIndex: 16, width: 320 }}>
      <Panel
        title={`echo · ${a} ✕ ${b}`}
        right={<span style={{ color: '#00FF41' }}>{pct(edge.similarity)}</span>}
      >
        {order.length > 0 ? (
          order.map((k) => (
            <Bar key={k} label={labelMap[k] || k} value={facets[k]} weight={weights[k]} />
          ))
        ) : (
          <div style={{ color: '#5a6a5a', fontSize: 11 }}>no facet breakdown on this edge yet.</div>
        )}
        <div style={{ height: 8 }} />
        {edge.blended != null && <Readout label="blended (raw)" value={edge.blended.toFixed(2)} />}
        <Readout label="match (calibrated)" value={pct(edge.similarity)} />
        <button onClick={onClose} style={closeBtn}>close ▢</button>
      </Panel>
    </div>
  )
}

// ── V3: node card ──────────────────────────────────────────────
function NodeCard({ node, simToYou, onClose }: { node: GraphNode; simToYou?: number; onClose: () => void }) {
  const status = node.lyricStatus === 'ready' ? 'themes ready'
    : node.lyricStatus === 'pending' ? 'computing themes…'
    : node.hasProfile ? 'profile only' : 'no profile yet'
  return (
    <div style={{ position: 'absolute', left: '50%', bottom: 80, transform: 'translateX(-50%)', zIndex: 16, width: 280 }}>
      <Panel title={node.isCurrentUser ? 'node · you' : 'node'}
             right={<span style={{ color: '#5a6a5a' }}>{node.spotifyId || ''}</span>}>
        <div style={{ fontSize: 14, color: '#c9d1c9', marginBottom: 8, letterSpacing: 0.3 }}>{node.displayName}</div>
        {!node.isCurrentUser && simToYou != null && <Readout label="match with you" value={pct(simToYou)} />}
        <Readout label="status" value={status} />
        <button onClick={onClose} style={closeBtn}>close ▢</button>
      </Panel>
    </div>
  )
}

const closeBtn: CSSProperties = {
  marginTop: 12, background: 'transparent', border: '1px solid rgba(0,255,65,0.2)', color: '#5a6a5a',
  fontFamily: "'JetBrains Mono', monospace", fontSize: 10, padding: '4px 10px', cursor: 'pointer',
  letterSpacing: 1, textTransform: 'uppercase',
}

function initials(name: string): string {
  return name.split(/\s+/).map((w) => w[0] ?? '').join('').slice(0, 2).toUpperCase()
}

function edgeColor(sim: number): string {
  if (sim >= 0.75) return '#00FF41'
  if (sim >= 0.55) return '#00CC33'
  if (sim >= 0.35) return '#009922'
  return '#005511'
}
