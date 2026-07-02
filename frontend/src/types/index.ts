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

export interface LayerLegendResponse {
  layerId: string
  time: string
  unit: string
  legend: LegendItem[]
}

export type LegendStatus = 'ready' | 'loading' | 'error'

// ===== Irrigation Water =====

export type IrrigationRasterResolution = 'annual' | 'month'
export type IrrigationRegionLevel = 'county' | 'village'
export type IrrigationSeriesPeriod = 'annual' | 'monthly'

export interface IrrigationRegion {
  id: string
  name: string
  level: IrrigationRegionLevel
  parentId: string | null
}

export interface IrrigationSeriesPoint {
  time: string
  value: number
}

export interface IrrigationSeriesResponse {
  region: IrrigationRegion
  period: IrrigationSeriesPeriod
  unit: string
  series: IrrigationSeriesPoint[]
  summary: {
    total: number
    average: number
    max: number
    min: number
  }
}

export interface IrrigationVectorStatus {
  level: IrrigationRegionLevel
  available: boolean
  url: string | null
  message: string
}

export interface IrrigationVectorFeature {
  type: 'Feature'
  properties: {
    id?: string
    name?: string
    [key: string]: unknown
  }
  geometry: {
    type: string
    coordinates: unknown
  }
}

export interface IrrigationVectorGeoJSON {
  type: 'FeatureCollection'
  features: IrrigationVectorFeature[]
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
