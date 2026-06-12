export interface User {
  userId: string
  spotifyId: string
  displayName: string
  email?: string
  visibility: string
}

export interface Profile {
  hasProfile: boolean
  lastUpdated?: number
  lyricStatus?: 'pending' | 'ready' | 'failed'
  lyricTracksAnalyzed?: number
  lastLyricUpdate?: number
  topGenres?: string[]
  topArtistsPreview?: { id: string; name: string }[]
}

// The four honest views of the same graph. 'blend' is the calibrated ensemble; the other
// three are single facets straight off each edge's breakdown — switching lenses re-reads
// data the client already has (no refetch).
export type Lens = 'blend' | 'artist' | 'genre' | 'lyric'
export const LENSES: readonly Lens[] = ['blend', 'artist', 'genre', 'lyric']

export interface GraphNode {
  userId: string
  displayName: string
  spotifyId: string
  isCurrentUser: boolean
  hasProfile: boolean
  lyricStatus?: string | null
  // v2 solo mode: 'archetype' nodes are genre-defined landmark personas (not real people).
  // They render distinctly and are never offered as friends.
  kind?: 'user' | 'archetype'
  description?: string
  // compact taste summary (server-computed): the comparative-imagery panels render off these
  topGenres?: [string, number][]
  topArtists?: string[]
}

export interface GraphEdge {
  source: string
  target: string
  similarity: number
  // v2 engine: the honest breakdown behind the score (present on new responses).
  blended?: number
  facets?: Record<string, number>   // artist | genre | lyric -> [0,1]
  weights?: Record<string, number>  // facet -> blend weight
}

export interface GraphData {
  mode: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  // true once the engine ships a fitted calibrator (similarity = absolute percentile). Until
  // then the ego-graph spreads scores relative to the field shown rather than claiming a %.
  calibrated?: boolean
}

export interface Friend {
  userId: string
  spotifyId: string
  displayName: string
  visibility: string
}

export interface FriendRequest {
  requestId: string
  fromUserId?: string
  fromSpotifyId?: string
  fromDisplayName?: string
  toUserId?: string
  toSpotifyId?: string
  toDisplayName?: string
  createdAt?: number
}

export interface FriendRequests {
  incoming: FriendRequest[]
  outgoing: FriendRequest[]
}
