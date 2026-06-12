const API = 'https://zl83bft0ve.execute-api.us-east-1.amazonaws.com/prod'

// VITE_MOCK=1 (npm run dev:mock) swaps every request for local fixtures — full-UI testing
// with no backend, no Spotify login. Build-time constant, so prod bundles drop the branch.
const MOCK = import.meta.env.VITE_MOCK === '1'

let _onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(fn: () => void) {
  _onUnauthorized = fn
}

function token() {
  return localStorage.getItem('spotify_token')
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (MOCK) return (await import('./mock')).mockReq<T>(path, init)
  const t = token()
  const res = await fetch(API + path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(t ? { 'X-Auth-Token': t } : {}),
      ...(init.headers as Record<string, string> || {}),
    },
  })
  if (res.status === 401) {
    _onUnauthorized?.()
    throw new Error('Unauthorized')
  }
  const json = await res.json()
  if (!res.ok) throw new Error(json.error || 'Request failed')
  return json.data as T
}

export async function getAuthUrl(): Promise<string> {
  const data = await req<{ authUrl: string }>('/auth/spotify')
  return data.authUrl
}

export const getMe = () => req<any>('/me')
export const getProfile = () => req<any>('/me/profile')
export const refreshProfile = () => req<any>('/me/profile/refresh', { method: 'POST' })
// One fetch serves every lens: edges carry the full facet breakdown, so artist/genre/lyric
// views are derived client-side. (The server still accepts ?mode= for older clients.)
export const getGraph = () => req<any>('/graph')
export const getFriends = () => req<any[]>('/friends')
export const getFriendRequests = () => req<any>('/friends/requests')

export const sendFriendRequest = (toSpotifyId: string) =>
  req<any>('/friends/request', { method: 'POST', body: JSON.stringify({ toSpotifyId }) })

export const acceptFriendRequest = (requestId: string) =>
  req<any>('/friends/accept', { method: 'POST', body: JSON.stringify({ requestId }) })

export const deleteFriend = (friendId: string) =>
  req<any>(`/friends/${friendId}`, { method: 'DELETE' })
