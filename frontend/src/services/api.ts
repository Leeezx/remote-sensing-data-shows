import axios from 'axios'
import type {
  Layer,
  PointQueryResult,
  AreaQueryRequest,
  AreaQueryResult,
  LayerLegendResponse,
  IrrigationRasterResolution,
  IrrigationRegion,
  IrrigationRegionLevel,
  IrrigationSeriesPeriod,
  IrrigationSeriesResponse,
  IrrigationVectorGeoJSON,
  IrrigationVectorStatus,
  IrrigationRegionAveragesResponse,
  ReclamationMetrics,
  ReclamationOverviewWireResponse,
  ReclamationPoint,
  ReclamationPointsResponse,
  ReclamationPointsWireResponse,
  WaterDemandOverviewResponse,
  WaterDemandPointGrid,
} from '../types'

const client = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

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

export async function getLayerLegend(
  layerId: string,
  time: string,
): Promise<LayerLegendResponse> {
  const { data } = await client.get<LayerLegendResponse>(
    `/layers/${layerId}/legend`,
    { params: { time } },
  )
  return data
}

// ===== Irrigation Water =====

export async function getIrrigationLayer(): Promise<Layer> {
  const { data } = await client.get('/irrigation/layer')
  return data
}

export async function getIrrigationTimes(
  resolution: IrrigationRasterResolution,
): Promise<string[]> {
  const { data } = await client.get('/irrigation/times', {
    params: { resolution },
  })
  return data
}

export async function getIrrigationLegend(
  time: string,
): Promise<LayerLegendResponse> {
  const { data } = await client.get<LayerLegendResponse>('/irrigation/legend', {
    params: { time },
  })
  return data
}

export async function getIrrigationRegions(
  level: IrrigationRegionLevel,
): Promise<IrrigationRegion[]> {
  const { data } = await client.get('/irrigation/regions', {
    params: { level },
  })
  return data
}

export async function getIrrigationSeries(
  level: IrrigationRegionLevel,
  regionId: string,
  period: IrrigationSeriesPeriod,
): Promise<IrrigationSeriesResponse> {
  const { data } = await client.get('/irrigation/series', {
    params: { level, regionId, period },
  })
  return data
}

export async function getIrrigationVectorStatus(
  level: IrrigationRegionLevel,
): Promise<IrrigationVectorStatus> {
  const { data } = await client.get('/irrigation/vectors', {
    params: { level },
  })
  return data
}

export async function getIrrigationVectorGeoJSON(
  level: IrrigationRegionLevel,
  countyId?: string,
): Promise<IrrigationVectorGeoJSON> {
  if (level === 'township' && !countyId) {
    throw new Error('countyId is required for township vectors')
  }
  const { data } = await client.get(`/irrigation/vectors/${level}`, {
    params: countyId ? { countyId } : undefined,
  })
  return data
}

export async function getIrrigationRegionAverages(
  level: IrrigationRegionLevel,
  countyId?: string,
): Promise<IrrigationRegionAveragesResponse> {
  if (level === 'township' && !countyId) {
    throw new Error('countyId is required for township averages')
  }
  const { data } = await client.get<IrrigationRegionAveragesResponse>(
    '/irrigation/regions/averages',
    { params: { level, ...(countyId ? { countyId } : {}) } },
  )
  return data
}

// ===== Reclamation Potential Assessment =====

export async function getReclamationOverview(
  signal?: AbortSignal,
): Promise<ReclamationOverviewWireResponse> {
  const { data } = await client.get<ReclamationOverviewWireResponse>(
    '/reclamation/regions',
    { signal },
  )
  return data
}

function parseScenarioMetrics(values: number[]): ReclamationMetrics {
  const sentinelCount = values.filter((value) => value === -999).length
  if (sentinelCount > 0 && sentinelCount < values.length) {
    throw new Error('Reclamation point scenario has mixed -999 and finite values')
  }

  return {
    reclamationValue: values[0],
    waterConsumption: values[1],
    yieldValue: values[2],
    soilCarbonValue: values[3],
  }
}

export function parseReclamationPointTuple(
  tuple: unknown,
): Omit<ReclamationPoint, 'id'> {
  if (
    !Array.isArray(tuple) ||
    tuple.length !== 10 ||
    !tuple.every((value) => typeof value === 'number' && Number.isFinite(value))
  ) {
    throw new Error('Reclamation point tuples must contain exactly 10 numeric values')
  }

  return {
    longitude: tuple[0],
    latitude: tuple[1],
    current: parseScenarioMetrics(tuple.slice(2, 6)),
    future: parseScenarioMetrics(tuple.slice(6, 10)),
  }
}

export async function getReclamationPoints(
  regionId: string,
  signal?: AbortSignal,
): Promise<ReclamationPointsResponse> {
  const { data } = await client.get<ReclamationPointsWireResponse>(
    `/reclamation/points/${encodeURIComponent(regionId)}`,
    { signal },
  )

  return {
    ...data,
    points: data.points.map((tuple, index) => ({
      id: `${regionId}:${index}`,
      ...parseReclamationPointTuple(tuple),
    })),
  }
}

// ===== Water Demand & Replenishment Assessment =====

const WATER_DEMAND_MAGIC = 'WDPT'
const WATER_DEMAND_VERSION = 1
const WATER_DEMAND_HEADER_BYTES = 120
const WATER_DEMAND_METRIC_COUNT = 6

export async function getWaterDemandOverview(
  signal?: AbortSignal,
): Promise<WaterDemandOverviewResponse> {
  const { data } = await client.get<WaterDemandOverviewResponse>(
    '/water-demand/overview',
    { signal },
  )
  return data
}

/**
 * Decode the columnar binary point transport.
 *
 * Layout (little endian): 120-byte header, longitude axis (float64),
 * latitude axis (float64), longitude indices (uint16), latitude indices
 * (uint16), six metric columns (uint16, column major), tier codes (uint8).
 */
export function parseWaterDemandPointGrid(buffer: ArrayBuffer): WaterDemandPointGrid {
  if (buffer.byteLength < WATER_DEMAND_HEADER_BYTES) {
    throw new Error('Water-demand transport is shorter than its header')
  }

  const view = new DataView(buffer)
  const magic = String.fromCharCode(
    view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3),
  )
  if (magic !== WATER_DEMAND_MAGIC) {
    throw new Error('Water-demand transport has an unexpected magic value')
  }
  const version = view.getUint16(4, true)
  if (version !== WATER_DEMAND_VERSION) {
    throw new Error(`Unsupported water-demand transport version ${version}`)
  }

  const pointCount = view.getUint32(8, true)
  const lonCount = view.getUint32(12, true)
  const latCount = view.getUint32(16, true)
  const columnCount = view.getUint32(20, true)
  if (columnCount !== WATER_DEMAND_METRIC_COUNT) {
    throw new Error(`Expected ${WATER_DEMAND_METRIC_COUNT} metric columns, found ${columnCount}`)
  }

  const expectedBytes = WATER_DEMAND_HEADER_BYTES
    + 8 * (lonCount + latCount)
    + 4 * pointCount
    + 2 * pointCount * columnCount
    + pointCount
  if (buffer.byteLength !== expectedBytes) {
    throw new Error('Water-demand transport length does not match its header')
  }

  const minimums = new Float64Array(buffer, 24, WATER_DEMAND_METRIC_COUNT).slice()
  const maximums = new Float64Array(buffer, 72, WATER_DEMAND_METRIC_COUNT).slice()
  let offset = WATER_DEMAND_HEADER_BYTES
  const lonAxis = new Float64Array(buffer, offset, lonCount).slice()
  offset += 8 * lonCount
  const latAxis = new Float64Array(buffer, offset, latCount).slice()
  offset += 8 * latCount
  const gx = new Uint16Array(buffer, offset, pointCount).slice()
  offset += 2 * pointCount
  const gy = new Uint16Array(buffer, offset, pointCount).slice()
  offset += 2 * pointCount
  const values = new Uint16Array(buffer, offset, pointCount * columnCount).slice()
  offset += 2 * pointCount * columnCount
  const classes = new Uint8Array(buffer, offset, pointCount).slice()

  return { pointCount, lonAxis, latAxis, gx, gy, values, classes, minimums, maximums }
}

export async function getWaterDemandPoints(
  signal?: AbortSignal,
): Promise<WaterDemandPointGrid> {
  const { data } = await client.get<ArrayBuffer>('/water-demand/points', {
    signal,
    responseType: 'arraybuffer',
  })
  return parseWaterDemandPointGrid(data)
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
