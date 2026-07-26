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
  exportable?: boolean
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
export type IrrigationRegionLevel = 'county' | 'township'
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

export interface IrrigationRegionAverage {
  regionId: string
  name: string
  average: number | null
}

export interface IrrigationRegionAveragesResponse {
  level: IrrigationRegionLevel
  unit: string
  averages: IrrigationRegionAverage[]
  legend: LegendItem[]
}

// ===== Reclamation Potential Assessment =====

export type ReclamationScenario = 'current' | 'future'
export type ReclamationUnit = 'thousand_usd'

export interface ReclamationMetrics {
  reclamationValue: number
  waterConsumption: number
  yieldValue: number
  soilCarbonValue: number
}

export interface ReclamationPoint {
  id: string
  longitude: number
  latitude: number
  current: ReclamationMetrics
  future: ReclamationMetrics
}

export type ReclamationPointTuple = [
  number, number, number, number, number,
  number, number, number, number, number,
]

export interface ReclamationRegionProperties {
  id: string
  name: string
  pointCount: number
  /** Leaflet order: [[south, west], [north, east]]. */
  bounds: [[number, number], [number, number]]
}

export interface ReclamationFeature<P> {
  type: 'Feature'
  properties: P
  geometry: { type: string; coordinates: unknown }
}

export interface ReclamationFeatureCollection<P> {
  type: 'FeatureCollection'
  features: ReclamationFeature<P>[]
}

export interface ReclamationGeometry {
  type: string
  coordinates: unknown
}

export interface ReclamationMetricDefinition {
  field: keyof ReclamationMetrics
  label: string
  unit: ReclamationUnit
}

export interface ReclamationOverviewWireResponse {
  schemaVersion: 1
  unit: ReclamationUnit
  chinaOutline: ReclamationGeometry
  metrics: ReclamationMetricDefinition[]
  regions: ReclamationFeatureCollection<ReclamationRegionProperties>
}

export interface ReclamationPointsWireResponse {
  schemaVersion: 1
  region: Pick<ReclamationRegionProperties, 'id' | 'name'>
  unit: ReclamationUnit
  fields: string[]
  points: ReclamationPointTuple[]
}

export interface ReclamationPointsResponse {
  schemaVersion: 1
  region: Pick<ReclamationRegionProperties, 'id' | 'name'>
  unit: ReclamationUnit
  fields: string[]
  points: ReclamationPoint[]
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
