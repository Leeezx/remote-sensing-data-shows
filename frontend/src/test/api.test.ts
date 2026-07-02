import { beforeEach, describe, expect, it, vi } from 'vitest'

const { clientGet } = vi.hoisted(() => ({
  clientGet: vi.fn(),
}))

vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>()

  return {
    ...actual,
    default: {
      ...actual.default,
      create: vi.fn(() => ({
        get: clientGet,
        post: vi.fn(),
        interceptors: {
          request: { use: vi.fn() },
          response: { use: vi.fn() },
        },
      })),
    },
  }
})

import {
  getExportCsvUrl,
  getIrrigationRegions,
  getIrrigationLegend,
  getIrrigationSeries,
  getIrrigationTimes,
  getIrrigationVectorStatus,
  getLayerLegend,
} from '../services/api'
import type { IrrigationSeriesResponse, LayerLegendResponse } from '../types'

beforeEach(() => {
  localStorage.clear()
  clientGet.mockReset()
})

describe('getExportCsvUrl', () => {
  it('includes the layer and time range without a region parameter', () => {
    const url = getExportCsvUrl('ssm', '2025-01', '2025-12')

    expect(url).toBe('/api/export/csv?layerId=ssm&start=2025-01&end=2025-12')
    expect(url).not.toContain('regionId')
  })
})

describe('getLayerLegend', () => {
  it('requests and returns the time-specific legend for a layer', async () => {
    const response = {
      layerId: 'ssm',
      time: '2025-06',
      unit: 'm³/m³',
      legend: [
        { value: 0.15, color: '#f7fbff', label: '≤ 0.15' },
        { value: 0.3, color: '#08306b', label: '> 0.15' },
      ],
    } satisfies LayerLegendResponse
    clientGet.mockResolvedValueOnce({ data: response })

    await expect(getLayerLegend('ssm', '2025-06')).resolves.toEqual(response)
    expect(clientGet).toHaveBeenCalledOnce()
    expect(clientGet).toHaveBeenCalledWith('/layers/ssm/legend', {
      params: { time: '2025-06' },
    })
  })
})

describe('irrigation API helpers', () => {
  it('requests irrigation raster times by resolution', async () => {
    clientGet.mockResolvedValueOnce({ data: ['2021', '2022'] })

    await expect(getIrrigationTimes('annual')).resolves.toEqual(['2021', '2022'])
    expect(clientGet).toHaveBeenCalledWith('/irrigation/times', {
      params: { resolution: 'annual' },
    })
  })

  it('requests irrigation dynamic legend for a raster time', async () => {
    const response = {
      layerId: 'irrigation_water',
      time: '2010-05',
      unit: '万m³',
      legend: [{ value: 3.2, color: '#123456', label: '3.200 万m³' }],
    } satisfies LayerLegendResponse
    clientGet.mockResolvedValueOnce({ data: response })

    await expect(getIrrigationLegend('2010-05')).resolves.toEqual(response)
    expect(clientGet).toHaveBeenCalledWith('/irrigation/legend', {
      params: { time: '2010-05' },
    })
  })

  it('requests irrigation vector status by administrative level', async () => {
    const response = {
      level: 'county',
      available: true,
      url: '/api/irrigation/vectors/county',
      message: '县级行政区矢量可用',
    }
    clientGet.mockResolvedValueOnce({ data: response })

    await expect(getIrrigationVectorStatus('county')).resolves.toEqual(response)
    expect(clientGet).toHaveBeenCalledWith('/irrigation/vectors', {
      params: { level: 'county' },
    })
  })

  it('requests irrigation regions by administrative level', async () => {
    const regions = [
      { id: 'county_a', name: '示范县A', level: 'county' as const, parentId: null },
    ]
    clientGet.mockResolvedValueOnce({ data: regions })

    await expect(getIrrigationRegions('county')).resolves.toEqual(regions)
    expect(clientGet).toHaveBeenCalledWith('/irrigation/regions', {
      params: { level: 'county' },
    })
  })

  it('requests precomputed irrigation series for one region', async () => {
    const response = {
      region: { id: 'county_a', name: '示范县A', level: 'county', parentId: null },
      period: 'monthly',
      unit: '万m³',
      series: [{ time: '2023-01', value: 118.4 }],
      summary: { total: 1532.2, average: 127.7, max: 214.5, min: 101.8 },
    } satisfies IrrigationSeriesResponse
    clientGet.mockResolvedValueOnce({ data: response })

    await expect(
      getIrrigationSeries('county', 'county_a', 'monthly'),
    ).resolves.toEqual(response)
    expect(clientGet).toHaveBeenCalledWith('/irrigation/series', {
      params: { level: 'county', regionId: 'county_a', period: 'monthly' },
    })
  })
})
