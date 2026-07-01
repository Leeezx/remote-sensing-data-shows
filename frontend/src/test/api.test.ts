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

import { getExportCsvUrl, getLayerLegend } from '../services/api'

describe('getExportCsvUrl', () => {
  beforeEach(() => {
    localStorage.clear()
    clientGet.mockReset()
  })

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
    }
    clientGet.mockResolvedValueOnce({ data: response })

    await expect(getLayerLegend('ssm', '2025-06')).resolves.toEqual(response)
    expect(clientGet).toHaveBeenCalledOnce()
    expect(clientGet).toHaveBeenCalledWith('/layers/ssm/legend', {
      params: { time: '2025-06' },
    })
  })
})
