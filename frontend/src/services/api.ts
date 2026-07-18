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
