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

export interface GraphNode {
  userId: string
  displayName: string
  spotifyId: string
  isCurrentUser: boolean
  hasProfile: boolean
  lyricStatus?: string | null
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
