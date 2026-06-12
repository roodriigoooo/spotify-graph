import React, { useState, useEffect, useRef } from 'react'
import * as api from './api'
import { LENSES, type Lens, type User, type Profile, type GraphData, type Friend, type FriendRequests } from './types'
import { loadWasmKernel, kernelBackend } from './kernel'
import Graph from './components/Graph'
import ProfilePanel from './components/ProfilePanel'
import FriendsPanel from './components/FriendsPanel'
import LoadingScreen from './components/LoadingScreen'

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('spotify_token'))
  const [user, setUser] = useState<User | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [friends, setFriends] = useState<Friend[]>([])
  const [friendRequests, setFriendRequests] = useState<FriendRequests>({ incoming: [], outgoing: [] })
  // one graph fetch serves all lenses; switching is a client-side re-read of edge facets
  const [lens, setLens] = useState<Lens>('blend')
  const [kernel, setKernel] = useState(kernelBackend())
  const [initialLoad, setInitialLoad] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [leftOpen, setLeftOpen] = useState(false)
  const [rightOpen, setRightOpen] = useState(false)
  const [authLoading, setAuthLoading] = useState(false)
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // boot the Rust→WASM kernel; everything falls back to the TS port until (unless) it lands
  useEffect(() => {
    loadWasmKernel().then(() => setKernel(kernelBackend()))
  }, [])

  useEffect(() => {
    api.setUnauthorizedHandler(() => {
      localStorage.removeItem('spotify_token')
      setToken(null)
      setUser(null)
      setProfile(null)
      setGraphData(null)
      setFriends([])
      setFriendRequests({ incoming: [], outgoing: [] })
    })
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const t = params.get('token')
    if (t) {
      localStorage.setItem('spotify_token', t)
      setToken(t)
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

  useEffect(() => {
    if (!token) return
    api.getMe().then(setUser).catch(() => { })
    api.getProfile().then(setProfile).catch(() => { })
    api.getFriends().then(setFriends).catch(() => { })
    api.getFriendRequests().then(setFriendRequests).catch(() => { })
  }, [token])

  useEffect(() => {
    if (!token) return
    setGraphData(null)
    api.getGraph().then(d => {
      setGraphData(d)
      setInitialLoad(false)
    }).catch(() => { setInitialLoad(false) })
  }, [token])

  useEffect(() => {
    if (profile?.lyricStatus !== 'pending') return
    pollRef.current = setTimeout(() => {
      api.getProfile().then(p => {
        setProfile(p)
        if (p.lyricStatus === 'ready') {
          api.getGraph().then(setGraphData).catch(() => { })
        }
      }).catch(() => { })
    }, 5000)
    return () => { if (pollRef.current) clearTimeout(pollRef.current) }
  }, [profile?.lyricStatus])

  // friend-request poll: 45s, and only while the tab is actually visible — a parked tab
  // shouldn't bill Lambda invocations. A refresh fires immediately on tab return.
  useEffect(() => {
    if (!token) return
    const poll = () => api.getFriendRequests().then(setFriendRequests).catch(() => { })
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') poll()
    }, 45000)
    const onVisible = () => { if (document.visibilityState === 'visible') poll() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { clearInterval(interval); document.removeEventListener('visibilitychange', onVisible) }
  }, [token])

  const handleLogin = async () => {
    setAuthLoading(true)
    try {
      const url = await api.getAuthUrl()
      window.location.href = url
    } catch {
      setAuthLoading(false)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('spotify_token')
    setToken(null)
    setUser(null)
    setProfile(null)
    setGraphData(null)
    setFriends([])
    setFriendRequests({ incoming: [], outgoing: [] })
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      const p = await api.refreshProfile()
      setProfile(p)
      api.getGraph().then(setGraphData).catch(() => { })
    } catch { }
    setRefreshing(false)
  }

  const handleFriendUpdate = () => {
    api.getFriends().then(setFriends).catch(() => { })
    api.getFriendRequests().then(setFriendRequests).catch(() => { })
    api.getGraph().then(setGraphData).catch(() => { })
  }

  if (!token) {
    return (
      <div className="landing">
        <BackgroundGraph />
        <div className="landing-content">
          <h1 className="landing-title">overlapping<br />echoes</h1>
          <p className="landing-sub">map your music · find your people</p>
          <button className="btn-spotify" onClick={handleLogin} disabled={authLoading}>
            <SpotifyIcon />
            {authLoading ? 'Redirecting…' : 'Continue with Spotify'}
          </button>
          <p className="landing-lyric">"I get by with a little help from my friends"</p>
        </div>
      </div>
    )
  }

  if (token && (!user || initialLoad)) {
    return <LoadingScreen text="Loading taste graph..." />
  }

  const incomingCount = friendRequests.incoming.length

  return (
    <div className="app">
      <div className="canvas">
        <Graph data={graphData} lens={lens} leftPanelOpen={leftOpen} />

        {/* ── Left panel toggle (profile) ── */}
        <button
          className="panel-toggle panel-toggle-left"
          onClick={() => setLeftOpen(o => !o)}
          aria-label="Toggle profile panel"
        >
          <ProfilePixelIcon />
        </button>

        <div className={`panel panel-left${leftOpen ? '' : ' collapsed-left'}`}>
          <ProfilePanel
            user={user}
            profile={profile}
            refreshing={refreshing}
            onRefresh={handleRefresh}
            onLogout={handleLogout}
          />
        </div>

        {/* ── Right panel toggle (friends) ── */}
        <button
          className="panel-toggle panel-toggle-right"
          onClick={() => setRightOpen(o => !o)}
          aria-label="Toggle friends panel"
        >
          {!rightOpen && incomingCount > 0 && (
            <span className="toggle-badge">{incomingCount}</span>
          )}
          <FriendsPixelIcon />
        </button>

        <div className={`panel panel-right${rightOpen ? '' : ' collapsed-right'}`}>
          <FriendsPanel
            friends={friends}
            requests={friendRequests}
            onUpdate={handleFriendUpdate}
          />
        </div>

        {/* ── Lens tabs (bottom centre): four honest views of the same data, no refetch ── */}
        <div className="hud-bottom">
          <div className="lens-tabs">
            <span className="lens-bracket">[</span>
            {LENSES.map(l => (
              <button
                key={l}
                className={`lens-btn${lens === l ? ' active' : ''}`}
                onClick={() => setLens(l)}
              >
                {l}
              </button>
            ))}
            <span className="lens-bracket">]</span>
          </div>
        </div>

        {/* ── Kernel badge (bottom right): which engine computes the geometry ── */}
        <div className="kernel-badge" title="the engine computing layout + field">
          kernel · {kernel}
        </div>
      </div>
    </div>
  )
}

// ─── Pixel circle geometry (mirrors Graph.tsx) ───────────────────────────────
const BG_LARGE = [
  { x: -6,  y: -14, w: 12, h: 4 },
  { x: -10, y: -10, w: 20, h: 4 },
  { x: -14, y: -6,  w: 28, h: 4 },
  { x: -14, y: -2,  w: 28, h: 4 },
  { x: -14, y:  2,  w: 28, h: 4 },
  { x: -10, y:  6,  w: 20, h: 4 },
  { x:  -6, y: 10,  w: 12, h: 4 },
] as const

const BG_SMALL = [
  { x: -6,  y: -10, w: 12, h: 4 },
  { x: -10, y: -6,  w: 20, h: 4 },
  { x: -10, y: -2,  w: 20, h: 4 },
  { x: -10, y:  2,  w: 20, h: 4 },
  { x:  -6, y:  6,  w: 12, h: 4 },
] as const

const BG_NODES = [
  { id: 0, x: 720, y: 390, big: true  },
  { id: 1, x: 460, y: 195 },
  { id: 2, x: 230, y: 370 },
  { id: 3, x: 345, y: 625 },
  { id: 4, x: 595, y: 755 },
  { id: 5, x: 875, y: 675 },
  { id: 6, x: 1065, y: 480 },
  { id: 7, x: 965, y: 225 },
  { id: 8, x: 755, y: 105 },
  { id: 9, x: 130, y: 570 },
  { id: 10, x: 1215, y: 340 },
  { id: 11, x: 1310, y: 590 },
]

const BG_EDGES: [number, number, number][] = [
  [0, 1, 0.82], [0, 7, 0.75], [0, 5, 0.60], [0, 4, 0.40],
  [1, 8, 0.65], [1, 2, 0.48], [7, 8, 0.70], [7, 10, 0.55],
  [5, 6, 0.72], [5, 4, 0.58], [3, 4, 0.80], [2, 3, 0.50],
  [2, 9, 0.62], [6, 10, 0.60], [6, 11, 0.50], [0, 6, 0.44],
]

function BackgroundGraph() {
  const nodeMap = new Map(BG_NODES.map(n => [n.id, n]))
  return (
    <svg
      className="landing-bg"
      viewBox="0 0 1440 900"
      preserveAspectRatio="xMidYMid slice"
    >
      {BG_EDGES.map(([a, b, sim]) => {
        const na = nodeMap.get(a), nb = nodeMap.get(b)
        if (!na || !nb) return null
        const color = sim >= 0.7 ? '#C9C0AC' : sim >= 0.5 ? '#8A8270' : '#5C564B'
        return (
          <line key={`${a}-${b}`}
            x1={na.x} y1={na.y} x2={nb.x} y2={nb.y}
            stroke={color}
            strokeWidth={0.8 + sim * 1.8}
            strokeOpacity={0.25 + sim * 0.5}
            strokeLinecap="square"
          />
        )
      })}
      {BG_NODES.map(n => {
        const pixels = n.big ? BG_LARGE : BG_SMALL
        const fill = n.big ? '#ECE4D2' : `rgba(212,205,188,${0.35 + (n.id % 5) * 0.12})`
        return (
          <g key={n.id} transform={`translate(${n.x},${n.y})`}>
            {pixels.map((p, i) => (
              <rect key={i} x={p.x} y={p.y} width={p.w} height={p.h}
                fill={fill} shapeRendering="crispEdges" />
            ))}
          </g>
        )
      })}
    </svg>
  )
}

function SpotifyIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z" />
    </svg>
  )
}

// Pixel-art person icon — 7×9 grid, 2px pixels
function ProfilePixelIcon() {
  return (
    <svg width="14" height="18" viewBox="0 0 7 9" fill="#C9C0AC" shapeRendering="crispEdges">
      {/* head */}
      <rect x="2" y="0" width="3" height="3" />
      {/* shoulders */}
      <rect x="1" y="3" width="5" height="1" />
      {/* body */}
      <rect x="1" y="4" width="5" height="2" />
      {/* legs */}
      <rect x="1" y="6" width="2" height="3" />
      <rect x="4" y="6" width="2" height="3" />
    </svg>
  )
}

// Pixel-art two-people icon — friends
function FriendsPixelIcon() {
  return (
    <svg width="22" height="16" viewBox="0 0 11 8" fill="#C9C0AC" shapeRendering="crispEdges">
      {/* person left */}
      <rect x="0" y="0" width="2" height="2" />
      <rect x="0" y="3" width="4" height="3" />
      {/* person right */}
      <rect x="9" y="0" width="2" height="2" />
      <rect x="7" y="3" width="4" height="3" />
      {/* link */}
      <rect x="4" y="1" width="3" height="1" />
    </svg>
  )
}
