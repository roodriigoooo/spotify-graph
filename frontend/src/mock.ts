/**
 * mock — dev-only API fixtures, so the whole UI can be exercised with zero backend.
 *
 *   VITE_MOCK=1 npm run dev      (or: npm run dev:mock)
 *
 * Routes every api.ts request to canned data shaped exactly like the v2 /graph response:
 * facet breakdowns, per-node taste summaries, archetypes, a lyric-less friend (ghosts on
 * the lyric lens) and a profile-less one (ghost everywhere). Statically dead-code-eliminated
 * from production builds (the VITE_MOCK check is a build-time constant).
 */
import type { GraphData } from './types'

const ME = { userId: 'u-me', spotifyId: 'you_local', displayName: 'You Local', visibility: 'public' }

const PROFILE = {
  hasProfile: true,
  lastUpdated: Math.floor(Date.now() / 1000) - 3600,
  lyricStatus: 'ready',
  lyricTracksAnalyzed: 38,
  topGenres: ['indie rock', 'art rock', 'dream pop', 'indietronica', 'folk'],
  topArtistsPreview: [
    { id: 'a1', name: 'Radiohead' }, { id: 'a2', name: 'Big Thief' }, { id: 'a3', name: 'The Smile' },
    { id: 'a4', name: 'Beach House' }, { id: 'a5', name: 'Alvvays' },
  ],
}

const FRIENDS = [
  { userId: 'u-nora', spotifyId: 'nora_m', displayName: 'Nora Marin', visibility: 'public' },
  { userId: 'u-mateo', spotifyId: 'mateo_b', displayName: 'Mateo Bravo', visibility: 'public' },
  { userId: 'u-iris', spotifyId: 'iris_v', displayName: 'Iris Vela', visibility: 'public' },
]

const REQUESTS = {
  incoming: [{ requestId: 'r1', fromUserId: 'u-leo', fromSpotifyId: 'leo_t', fromDisplayName: 'Leo Tan', createdAt: Date.now() - 60000 }],
  outgoing: [],
}

const arch = (slug: string, name: string, description: string, topGenres: [string, number][]) => ({
  userId: `archetype:${slug}`, displayName: name, spotifyId: '', isCurrentUser: false,
  hasProfile: true, lyricStatus: null, kind: 'archetype' as const, description,
  topGenres, topArtists: [],
})

const GRAPH: GraphData = {
  mode: 'taste',
  calibrated: false,
  nodes: [
    {
      userId: 'u-me', displayName: 'You Local', spotifyId: 'you_local', isCurrentUser: true,
      hasProfile: true, lyricStatus: 'ready', kind: 'user', description: '',
      topGenres: [['indie rock', 0.30], ['art rock', 0.20], ['dream pop', 0.15], ['indietronica', 0.10], ['folk', 0.08]],
      topArtists: ['Radiohead', 'Big Thief', 'The Smile', 'Beach House', 'Alvvays'],
    },
    {
      userId: 'u-nora', displayName: 'Nora Marin', spotifyId: 'nora_m', isCurrentUser: false,
      hasProfile: true, lyricStatus: 'ready', kind: 'user', description: '',
      topGenres: [['indie rock', 0.24], ['indie pop', 0.20], ['dream pop', 0.18], ['chamber pop', 0.10], ['folk', 0.06]],
      topArtists: ['Big Thief', 'Phoebe Bridgers', 'Beach House', 'Japanese Breakfast', 'Weyes Blood'],
    },
    {
      userId: 'u-mateo', displayName: 'Mateo Bravo', spotifyId: 'mateo_b', isCurrentUser: false,
      hasProfile: true, lyricStatus: 'pending', kind: 'user', description: '',
      topGenres: [['hip hop', 0.32], ['rap', 0.22], ['trap', 0.16], ['r&b', 0.10], ['neo soul', 0.06]],
      topArtists: ['Kendrick Lamar', 'MF DOOM', 'Freddie Gibbs', 'SZA', 'Anderson .Paak'],
    },
    {
      // no profile at all -> no edges on any lens -> always a ghost outside the rim
      userId: 'u-iris', displayName: 'Iris Vela', spotifyId: 'iris_v', isCurrentUser: false,
      hasProfile: false, lyricStatus: null, kind: 'user', description: '', topGenres: [], topArtists: [],
    },
    arch('indie', 'the indie purist', 'guitars, reverb, and feelings — lives in the 4-to-8k monthly-listener range.',
      [['indie rock', 0.23], ['indie pop', 0.18], ['art rock', 0.14], ['indietronica', 0.11], ['dream pop', 0.09]]),
    arch('pop', 'the pop maximalist', 'hooks first — the charts are a playlist, not a compromise.',
      [['pop', 0.27], ['dance pop', 0.24], ['electropop', 0.16], ['pop rock', 0.13], ['synthpop', 0.13]]),
    arch('hiphop', 'the hip-hop head', 'bars, beats, and producer credits — knows who sampled what.',
      [['hip hop', 0.25], ['rap', 0.22], ['trap', 0.17], ['conscious hip hop', 0.12], ['southern hip hop', 0.12]]),
    arch('metal', 'the heavy one', 'loud, fast, cathartic — the breakdown is the point.',
      [['metal', 0.23], ['alternative metal', 0.21], ['hard rock', 0.18], ['metalcore', 0.15], ['nu metal', 0.13]]),
  ],
  edges: [
    { source: 'u-me', target: 'u-nora', similarity: 0.78, blended: 0.71,
      facets: { artist: 0.42, genre: 0.69, lyric: 0.81 }, weights: { artist: 0.3, genre: 0.3, lyric: 0.4 } },
    { source: 'u-me', target: 'u-mateo', similarity: 0.46, blended: 0.43,
      facets: { artist: 0.12, genre: 0.38 }, weights: { artist: 0.5, genre: 0.5 } },
    { source: 'u-nora', target: 'u-mateo', similarity: 0.39, blended: 0.37,
      facets: { artist: 0.08, genre: 0.31 }, weights: { artist: 0.5, genre: 0.5 } },
    { source: 'u-me', target: 'archetype:indie', similarity: 0.74, blended: 0.74,
      facets: { genre: 0.74 }, weights: { genre: 1 } },
    { source: 'u-me', target: 'archetype:pop', similarity: 0.28, blended: 0.28,
      facets: { genre: 0.28 }, weights: { genre: 1 } },
    { source: 'u-me', target: 'archetype:hiphop', similarity: 0.18, blended: 0.18,
      facets: { genre: 0.18 }, weights: { genre: 1 } },
    { source: 'u-me', target: 'archetype:metal', similarity: 0.12, blended: 0.12,
      facets: { genre: 0.12 }, weights: { genre: 1 } },
    { source: 'u-nora', target: 'archetype:indie', similarity: 0.68, blended: 0.68,
      facets: { genre: 0.68 }, weights: { genre: 1 } },
    { source: 'u-mateo', target: 'archetype:hiphop', similarity: 0.81, blended: 0.81,
      facets: { genre: 0.81 }, weights: { genre: 1 } },
    { source: 'archetype:indie', target: 'archetype:pop', similarity: 0.33, blended: 0.33,
      facets: { genre: 0.33 }, weights: { genre: 1 } },
    { source: 'archetype:pop', target: 'archetype:hiphop', similarity: 0.29, blended: 0.29,
      facets: { genre: 0.29 }, weights: { genre: 1 } },
    { source: 'archetype:hiphop', target: 'archetype:metal', similarity: 0.21, blended: 0.21,
      facets: { genre: 0.21 }, weights: { genre: 1 } },
    { source: 'archetype:indie', target: 'archetype:metal', similarity: 0.26, blended: 0.26,
      facets: { genre: 0.26 }, weights: { genre: 1 } },
  ],
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

export async function mockReq<T>(path: string, init: RequestInit = {}): Promise<T> {
  await wait(120 + Math.random() * 180)   // a believable network
  const method = (init.method || 'GET').toUpperCase()
  const route = path.split('?')[0]

  if (route === '/auth/spotify') return { authUrl: '/?token=mock-token' } as T
  if (route === '/me') return ME as T
  if (route === '/me/profile' && method === 'GET') return PROFILE as T
  if (route === '/me/profile/refresh') return PROFILE as T
  if (route === '/graph') return GRAPH as T
  if (route === '/friends' && method === 'GET') return FRIENDS as T
  if (route === '/friends/requests') return REQUESTS as T
  if (route.startsWith('/friends') || route.startsWith('/me/')) return {} as T
  throw new Error(`mock: unhandled route ${method} ${path}`)
}
