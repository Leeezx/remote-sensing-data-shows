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

// ===== Water Demand & Replenishment Assessment =====

export type WaterDemandScenario = 'current' | 'future'
export type WaterDemandUnit = 'mm'

/** Water-replenishment tier carried on every sample point. */
export type WaterDemandClass = 1 | 2 | 3

export interface WaterDemandMetrics {
  ecologicalWaterConsumption: number
  ecologicalWaterDemand: number
  ecologicalWaterReplenishment: number
}

export interface WaterDemandPoint {
  id: string
  longitude: number
  latitude: number
  class: WaterDemandClass
  current: WaterDemandMetrics
  future: WaterDemandMetrics
}

export interface WaterDemandRegionProperties {
  id: string
  name: string
  pointCount: number
  /** Leaflet order: [[south, west], [north, east]]. */
  bounds: [[number, number], [number, number]]
}

export interface WaterDemandFeature<P> {
  type: 'Feature'
  properties: P
  geometry: { type: string; coordinates: unknown }
}

export interface WaterDemandFeatureCollection<P> {
  type: 'FeatureCollection'
  features: WaterDemandFeature<P>[]
}

export interface WaterDemandGeometry {
  type: string
  coordinates: unknown
}

export interface WaterDemandMetricDefinition {
  field: keyof WaterDemandMetrics
  label: string
  unit: WaterDemandUnit
}

export interface WaterDemandLegendEntry {
  value: WaterDemandClass
  color: string
  label: string
}

export interface WaterDemandOverviewResponse {
  schemaVersion: 1
  unit: WaterDemandUnit
  metrics: WaterDemandMetricDefinition[]
  valueFields: string[]
  legend: WaterDemandLegendEntry[]
  chinaOutline: WaterDemandGeometry
  regions: WaterDemandFeatureCollection<WaterDemandRegionProperties>
}

/**
 * Columnar, quantised point transport.
 *
 * `gx`/`gy` index into `lonAxis`/`latAxis`; `values` holds six metric columns in
 * `valueFields` order, laid out as `values[column * pointCount + point]`.
 * Points are sorted by `(gy, gx)` so hit-testing can binary-search latitude rows.
 */
export interface WaterDemandPointGrid {
  pointCount: number
  lonAxis: Float64Array
  latAxis: Float64Array
  gx: Uint16Array
  gy: Uint16Array
  values: Uint16Array
  classes: Uint8Array
  minimums: Float64Array
  maximums: Float64Array
}
