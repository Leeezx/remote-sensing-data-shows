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
  getReclamationOverview,
  getReclamationPoints,
  getIrrigationRegions,
  getIrrigationLegend,
  getIrrigationSeries,
  getIrrigationTimes,
  getIrrigationRegionAverages,
  getIrrigationVectorGeoJSON,
  getIrrigationVectorStatus,
  getLayerLegend,
  getWaterDemandOverview,
  getWaterDemandPoints,
  parseWaterDemandPointGrid,
} from '../services/api'
import type {
  IrrigationSeriesResponse,
  LayerLegendResponse,
  ReclamationOverviewWireResponse,
} from '../types'

beforeEach(() => {
  localStorage.clear()
  clientGet.mockReset()
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

  it('requires and sends a county id for a township vector chunk', async () => {
    const response = { type: 'FeatureCollection', features: [] }
    clientGet.mockResolvedValueOnce({ data: response })

    await expect(
      getIrrigationVectorGeoJSON('township', '156511011'),
    ).resolves.toEqual(response)
    expect(clientGet).toHaveBeenCalledWith('/irrigation/vectors/township', {
      params: { countyId: '156511011' },
    })
    await expect(getIrrigationVectorGeoJSON('township')).rejects.toThrow(
      'countyId is required',
    )
  })

  it('requests only one county of township averages', async () => {
    const response = { level: 'township', unit: '万m³', averages: [], legend: [] }
    clientGet.mockResolvedValueOnce({ data: response })

    await expect(
      getIrrigationRegionAverages('township', '156511011'),
    ).resolves.toEqual(response)
    expect(clientGet).toHaveBeenCalledWith('/irrigation/regions/averages', {
      params: { level: 'township', countyId: '156511011' },
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

describe('reclamation API helpers', () => {
  it('requests the overview with an abort signal', async () => {
    const response = {
      schemaVersion: 1,
      unit: 'thousand_usd',
      chinaOutline: { type: 'Polygon', coordinates: [] },
      regions: { type: 'FeatureCollection', features: [] },
      metrics: [],
    } satisfies ReclamationOverviewWireResponse
    clientGet.mockResolvedValueOnce({ data: response })
    const controller = new AbortController()

    await expect(getReclamationOverview(controller.signal)).resolves.toEqual(response)
    expect(clientGet).toHaveBeenCalledWith('/reclamation/regions', {
      signal: controller.signal,
    })
  })

  it('maps the compact point tuple into named current and future metrics', async () => {
    clientGet.mockResolvedValueOnce({
      data: {
        schemaVersion: 1,
        region: { id: 'A', name: '区域A' },
        unit: 'thousand_usd',
        fields: [],
        points: [[101, 31, 1, 2, 3, 4, 5, 6, 7, 8]],
      },
    })
    const controller = new AbortController()

    const result = await getReclamationPoints('A', controller.signal)

    expect(clientGet).toHaveBeenCalledWith('/reclamation/points/A', {
      signal: controller.signal,
    })
    expect(result.points[0]).toEqual({
      id: 'A:0',
      longitude: 101,
      latitude: 31,
      current: {
        reclamationValue: 1,
        waterConsumption: 2,
        yieldValue: 3,
        soilCarbonValue: 4,
      },
      future: {
        reclamationValue: 5,
        waterConsumption: 6,
        yieldValue: 7,
        soilCarbonValue: 8,
      },
    })
  })

  it('rejects malformed tuples before page state sees them', async () => {
    clientGet.mockResolvedValueOnce({
      data: {
        schemaVersion: 1,
        region: { id: 'A', name: '区域A' },
        unit: 'thousand_usd',
        fields: [],
        points: [[101, 31, 1]],
      },
    })

    await expect(getReclamationPoints('A')).rejects.toThrow('10 numeric values')
  })

  it('rejects scenarios that mix sentinel and finite metrics', async () => {
    clientGet.mockResolvedValueOnce({
      data: {
        schemaVersion: 1,
        region: { id: 'A', name: '区域A' },
        unit: 'thousand_usd',
        fields: [],
        points: [[101, 31, -999, 2, 3, 4, 5, 6, 7, 8]],
      },
    })

    await expect(getReclamationPoints('A')).rejects.toThrow('mixed -999 and finite values')
  })
})


describe('water-demand API helpers', () => {
  const METRICS = 6

  /** Encode a transport exactly like the Python builder does. */
  function encodeGrid({
    pointCount,
    lonAxis,
    latAxis,
    gx,
    gy,
    values,
    classes,
    minimums,
    maximums,
  }: {
    pointCount: number
    lonAxis: number[]
    latAxis: number[]
    gx: number[]
    gy: number[]
    values: number[]
    classes: number[]
    minimums: number[]
    maximums: number[]
  }): ArrayBuffer {
    const bytes = 120
      + 8 * (lonAxis.length + latAxis.length)
      + 4 * pointCount
      + 2 * pointCount * METRICS
      + pointCount
    const buffer = new ArrayBuffer(bytes)
    const view = new DataView(buffer)
    view.setUint8(0, 0x57) // W
    view.setUint8(1, 0x44) // D
    view.setUint8(2, 0x50) // P
    view.setUint8(3, 0x54) // T
    view.setUint16(4, 1, true)
    view.setUint32(8, pointCount, true)
    view.setUint32(12, lonAxis.length, true)
    view.setUint32(16, latAxis.length, true)
    view.setUint32(20, METRICS, true)
    minimums.forEach((value, index) => view.setFloat64(24 + index * 8, value, true))
    maximums.forEach((value, index) => view.setFloat64(72 + index * 8, value, true))

    let offset = 120
    lonAxis.forEach((value) => { view.setFloat64(offset, value, true); offset += 8 })
    latAxis.forEach((value) => { view.setFloat64(offset, value, true); offset += 8 })
    gx.forEach((value) => { view.setUint16(offset, value, true); offset += 2 })
    gy.forEach((value) => { view.setUint16(offset, value, true); offset += 2 })
    values.forEach((value) => { view.setUint16(offset, value, true); offset += 2 })
    classes.forEach((value) => { view.setUint8(offset, value); offset += 1 })
    return buffer
  }

  // `values` is column major: values[column * pointCount + point].
  const sampleBuffer = () => encodeGrid({
    pointCount: 2,
    lonAxis: [100, 100.01],
    latAxis: [30, 30.01],
    gx: [0, 1],
    gy: [0, 0],
    values: [
      0, 65535, // column 0 (current consumption)
      0, 0,
      0, 0,
      0, 32768, // column 3 (future consumption)
      0, 0,
      0, 0,
    ],
    classes: [1, 2],
    minimums: [0, 0, 0, 0, 0, 0],
    maximums: [1000, 1000, 1000, 1000, 1000, 1000],
  })

  it('requests the overview with an abort signal', async () => {
    const payload = { schemaVersion: 1, unit: 'mm', regions: { type: 'FeatureCollection', features: [] } }
    clientGet.mockResolvedValueOnce({ data: payload })
    const controller = new AbortController()

    await expect(getWaterDemandOverview(controller.signal)).resolves.toEqual(payload)
    expect(clientGet).toHaveBeenCalledWith('/water-demand/overview', { signal: controller.signal })
  })

  it('requests the binary transport as an array buffer and decodes it', async () => {
    clientGet.mockResolvedValueOnce({ data: sampleBuffer() })

    const grid = await getWaterDemandPoints()

    expect(clientGet).toHaveBeenCalledWith('/water-demand/points', {
      signal: undefined,
      responseType: 'arraybuffer',
    })
    expect(grid.pointCount).toBe(2)
    expect(Array.from(grid.lonAxis)).toEqual([100, 100.01])
    expect(Array.from(grid.latAxis)).toEqual([30, 30.01])
    expect(Array.from(grid.gx)).toEqual([0, 1])
    expect(Array.from(grid.gy)).toEqual([0, 0])
    expect(Array.from(grid.classes)).toEqual([1, 2])
    expect(grid.values[1]).toBe(65535) // column 0, point 1
    expect(grid.values[3 * grid.pointCount + 1]).toBe(32768)
  })

  it('rejects a transport with the wrong magic value', () => {
    const buffer = sampleBuffer()
    new DataView(buffer).setUint8(0, 0x00)

    expect(() => parseWaterDemandPointGrid(buffer)).toThrow('unexpected magic')
  })

  it('rejects an unsupported transport version', () => {
    const buffer = sampleBuffer()
    new DataView(buffer).setUint16(4, 99, true)

    expect(() => parseWaterDemandPointGrid(buffer)).toThrow('Unsupported water-demand transport version 99')
  })

  it('rejects a transport whose header and length disagree', () => {
    const full = sampleBuffer()
    const truncated = full.slice(0, full.byteLength - 4)
    // Header magic and declared counts survive; only the byte length is short.
    expect(new DataView(truncated).getUint32(8, true)).toBe(2)

    expect(() => parseWaterDemandPointGrid(truncated)).toThrow('length does not match')
  })

  it('rejects a transport shorter than its header', () => {
    expect(() => parseWaterDemandPointGrid(new ArrayBuffer(8))).toThrow('shorter than its header')
  })

  it('rejects a transport that declares the wrong metric column count', () => {
    const buffer = sampleBuffer()
    new DataView(buffer).setUint32(20, 5, true)

    expect(() => parseWaterDemandPointGrid(buffer)).toThrow('Expected 6 metric columns, found 5')
  })
})
