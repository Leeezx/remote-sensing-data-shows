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
