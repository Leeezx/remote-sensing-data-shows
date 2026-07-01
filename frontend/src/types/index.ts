// ===== Layer & Metadata =====

export interface Layer {
  id: string
  name: string
  description: string
  type: string
  unit: string
  range: { min: number; max: number }
  timeRange: { start: string; end: string; step: string }
  tileTemplate: string
  legend: LegendItem[]
}

export interface LegendItem {
  value: number
  color: string
  label: string
}

// ===== Query Results =====

export interface PointQueryResult {
  layerId: string
  time: string
  lng: number
  lat: number
  value: number
  unit: string
}

export interface AreaQueryRequest {
  layerId: string
  time: string
  geometry: {
    type: 'Polygon'
    coordinates: number[][][]
  }
}

export interface AreaQueryResult {
  mean: number
  max: number
  min: number
  count: number
}

export type MapQueryState =
  | { status: 'idle' }
  | { status: 'loading'; kind: 'point' | 'area' }
  | { status: 'error'; kind: 'point' | 'area'; message: string }
  | { status: 'point'; result: PointQueryResult }
  | { status: 'area'; result: AreaQueryResult }

// ===== Auth =====

export interface User {
  username: string
  role: 'viewer' | 'researcher'
}

export interface LoginResponse {
  access_token: string
  user: User
}
