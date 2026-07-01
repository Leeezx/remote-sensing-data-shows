import { beforeEach, describe, expect, it } from 'vitest'
import { getExportCsvUrl } from '../services/api'

describe('getExportCsvUrl', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('includes the layer and time range without a region parameter', () => {
    const url = getExportCsvUrl('ssm', '2025-01', '2025-12')

    expect(url).toBe('/api/export/csv?layerId=ssm&start=2025-01&end=2025-12')
    expect(url).not.toContain('regionId')
  })
})
