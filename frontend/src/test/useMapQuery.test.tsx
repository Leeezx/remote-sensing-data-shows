import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useMapQuery } from '../hooks/useMapQuery'
import { queryArea, queryPoint } from '../services/api'
import type { AreaQueryResult, PointQueryResult } from '../types'

vi.mock('../services/api', () => ({
  queryPoint: vi.fn(),
  queryArea: vi.fn(),
}))

const mockedQueryPoint = vi.mocked(queryPoint)
const mockedQueryArea = vi.mocked(queryArea)

const pointResult: PointQueryResult = {
  layerId: 'ndvi',
  time: '2025-06',
  lng: 116.3913,
  lat: 39.9075,
  value: 0.68,
  unit: '指数',
}

const areaResult: AreaQueryResult = { mean: 0.5, max: 0.9, min: 0.1, count: 25 }
const areaCornerPermutations: Array<[[number, number], [number, number]]> = [
  [[40, 117], [39, 116]],
  [[39, 117], [40, 116]],
  [[40, 116], [39, 117]],
]

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('useMapQuery', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it.each([
    [null, '2025-06'],
    ['ndvi', ''],
  ] as const)('does not query without both an active layer and time', async (layerId, time) => {
    const { result } = renderHook(() => useMapQuery(layerId, time))

    await act(async () => {
      await result.current.queryPointAt(39, 116)
      await result.current.queryAreaBounds([[39, 116], [40, 117]])
    })

    expect(mockedQueryPoint).not.toHaveBeenCalled()
    expect(mockedQueryArea).not.toHaveBeenCalled()
    expect(result.current.state).toEqual({ status: 'idle' })
  })

  it('loads and returns a point result using coordinates rounded to four decimals', async () => {
    const request = deferred<PointQueryResult>()
    mockedQueryPoint.mockReturnValueOnce(request.promise)
    const { result } = renderHook(() => useMapQuery('ndvi', '2025-06'))

    act(() => {
      void result.current.queryPointAt(39.907543, 116.391267)
    })

    expect(result.current.state).toEqual({ status: 'loading', kind: 'point' })
    expect(mockedQueryPoint).toHaveBeenCalledWith('ndvi', '2025-06', 116.3913, 39.9075)

    await act(async () => request.resolve(pointResult))

    expect(result.current.state).toEqual({ status: 'point', result: pointResult })
  })

  it('builds a closed lng-lat polygon and immediately returns area statistics', async () => {
    const request = deferred<AreaQueryResult>()
    mockedQueryArea.mockReturnValueOnce(request.promise)
    const { result } = renderHook(() => useMapQuery('ndvi', '2025-06'))

    act(() => {
      void result.current.queryAreaBounds([[39, 116], [40, 117]])
    })

    expect(result.current.state).toEqual({ status: 'loading', kind: 'area' })
    expect(mockedQueryArea).toHaveBeenCalledWith({
      layerId: 'ndvi',
      time: '2025-06',
      geometry: {
        type: 'Polygon',
        coordinates: [[[116, 39], [117, 39], [117, 40], [116, 40], [116, 39]]],
      },
    })

    await act(async () => request.resolve(areaResult))

    expect(result.current.state).toEqual({ status: 'area', result: areaResult })
  })

  it.each(areaCornerPermutations)('normalizes area corners into the same canonical polygon for %#', async (first, second) => {
    mockedQueryArea.mockResolvedValueOnce(areaResult)
    const { result } = renderHook(() => useMapQuery('ndvi', '2025-06'))

    await act(async () => {
      await result.current.queryAreaBounds([first, second])
    })

    expect(mockedQueryArea).toHaveBeenCalledWith({
      layerId: 'ndvi',
      time: '2025-06',
      geometry: {
        type: 'Polygon',
        coordinates: [[[116, 39], [117, 39], [117, 40], [116, 40], [116, 39]]],
      },
    })
  })

  it.each([
    ['point', '该位置无有效数据'],
    ['area', '该区域无有效数据'],
  ] as const)('shows a localized %s message for 404 responses', async (kind, message) => {
    const notFound = { response: { status: 404 } }
    mockedQueryPoint.mockRejectedValueOnce(notFound)
    mockedQueryArea.mockRejectedValueOnce(notFound)
    const { result } = renderHook(() => useMapQuery('ndvi', '2025-06'))

    await act(async () => {
      if (kind === 'point') await result.current.queryPointAt(39, 116)
      else await result.current.queryAreaBounds([[39, 116], [40, 117]])
    })

    expect(result.current.state).toEqual({ status: 'error', kind, message })
  })

  it.each([
    ['point', '点查询失败，请重试'],
    ['area', '区域查询失败，请重试'],
  ] as const)('shows a retryable %s message for generic failures', async (kind, message) => {
    mockedQueryPoint.mockRejectedValueOnce(new Error('offline'))
    mockedQueryArea.mockRejectedValueOnce(new Error('offline'))
    const { result } = renderHook(() => useMapQuery('ndvi', '2025-06'))

    await act(async () => {
      if (kind === 'point') await result.current.queryPointAt(39, 116)
      else await result.current.queryAreaBounds([[39, 116], [40, 117]])
    })

    expect(result.current.state).toEqual({ status: 'error', kind, message })
  })

  it('reset returns to idle and ignores a deferred stale response', async () => {
    const request = deferred<PointQueryResult>()
    mockedQueryPoint.mockReturnValueOnce(request.promise)
    const { result } = renderHook(() => useMapQuery('ndvi', '2025-06'))

    act(() => {
      void result.current.queryPointAt(39, 116)
      result.current.reset()
    })
    expect(result.current.state).toEqual({ status: 'idle' })

    await act(async () => request.resolve(pointResult))

    expect(result.current.state).toEqual({ status: 'idle' })
  })

  it('keeps the newer query result when an older request resolves last', async () => {
    const older = deferred<PointQueryResult>()
    const newer = deferred<PointQueryResult>()
    const newerResult = { ...pointResult, lng: 120, lat: 30, value: 0.9 }
    mockedQueryPoint.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise)
    const { result } = renderHook(() => useMapQuery('ndvi', '2025-06'))

    act(() => {
      void result.current.queryPointAt(39, 116)
      void result.current.queryPointAt(30, 120)
    })
    await act(async () => newer.resolve(newerResult))
    expect(result.current.state).toEqual({ status: 'point', result: newerResult })

    await act(async () => older.resolve(pointResult))
    expect(result.current.state).toEqual({ status: 'point', result: newerResult })
  })

  it('resets and invalidates in-flight work when only the layer changes', async () => {
    const request = deferred<PointQueryResult>()
    mockedQueryPoint.mockReturnValueOnce(request.promise)
    const { result, rerender } = renderHook(
      ({ layerId, time }) => useMapQuery(layerId, time),
      { initialProps: { layerId: 'ndvi' as string | null, time: '2025-06' } },
    )

    act(() => {
      void result.current.queryPointAt(39, 116)
    })
    rerender({ layerId: 'lst', time: '2025-06' })
    await waitFor(() => expect(result.current.state).toEqual({ status: 'idle' }))

    await act(async () => request.resolve(pointResult))
    expect(result.current.state).toEqual({ status: 'idle' })
  })

  it('resets and invalidates in-flight work when only the time changes', async () => {
    const request = deferred<PointQueryResult>()
    mockedQueryPoint.mockReturnValueOnce(request.promise)
    const { result, rerender } = renderHook(
      ({ layerId, time }) => useMapQuery(layerId, time),
      { initialProps: { layerId: 'ndvi' as string | null, time: '2025-06' } },
    )

    act(() => {
      void result.current.queryPointAt(39, 116)
    })
    rerender({ layerId: 'ndvi', time: '2025-07' })
    await waitFor(() => expect(result.current.state).toEqual({ status: 'idle' }))

    await act(async () => request.resolve(pointResult))
    expect(result.current.state).toEqual({ status: 'idle' })
  })
})
