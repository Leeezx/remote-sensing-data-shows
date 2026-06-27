import axios, { AxiosError } from 'axios'
import type {
  Layer,
  PointQueryResult,
  AreaQueryRequest,
  AreaQueryResult,
  TimeSeriesPoint,
  LoginResponse,
  Region,
} from '../types'

const client = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Attach JWT token to every request if present
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// On 401, clear stored token
client.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
    }
    return Promise.reject(error)
  },
)

// ===== Layers =====

export async function getLayers(): Promise<Layer[]> {
  const { data } = await client.get('/layers')
  return data
}

export async function getLayerTimes(
  layerId: string,
  resolution: 'month' | '8day' = 'month',
): Promise<string[]> {
  const { data } = await client.get(`/layers/${layerId}/times`, {
    params: { resolution },
  })
  return data
}

// ===== Regions =====

export async function getRegions(): Promise<Region[]> {
  const { data } = await client.get('/regions')
  return data
}

// ===== Spatial Queries =====

export async function queryPoint(
  layerId: string,
  time: string,
  lng: number,
  lat: number,
): Promise<PointQueryResult> {
  const { data } = await client.get('/query/point', {
    params: { layerId, time, lng, lat },
  })
  return data
}

export async function queryArea(
  body: AreaQueryRequest,
): Promise<AreaQueryResult> {
  const { data } = await client.post('/query/area', body)
  return data
}

// ===== Time Series =====

export async function getSeries(
  layerId: string,
  regionId?: string,
  start?: string,
  end?: string,
): Promise<TimeSeriesPoint[]> {
  const { data } = await client.get('/series', {
    params: { layerId, regionId, start, end },
  })
  return data
}

// ===== Export =====

export function getExportCsvUrl(
  layerId: string,
  regionId?: string,
  start?: string,
  end?: string,
): string {
  const params = new URLSearchParams({ layerId })
  if (regionId) params.set('regionId', regionId)
  if (start) params.set('start', start)
  if (end) params.set('end', end)
  // Include token in URL for download links (Authorization header is not sent on
  // <a> clicks / window.open)
  const token = localStorage.getItem('access_token')
  if (token) params.set('token', token)
  return `/api/export/csv?${params.toString()}`
}

// ===== Auth =====

export async function login(
  username: string,
  password: string,
): Promise<LoginResponse> {
  const { data } = await client.post('/auth/login', { username, password })
  return data
}
