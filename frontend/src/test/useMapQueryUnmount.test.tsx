import { act, renderHook } from '@testing-library/react'
import { expect, it, vi } from 'vitest'

const observedRefs = vi.hoisted(() => [] as Array<{ current: unknown }>)

vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react')
  return {
    ...actual,
    useRef: <T,>(initialValue: T) => {
      const ref = actual.useRef(initialValue)
      observedRefs.push(ref)
      return ref
    },
  }
})

vi.mock('../services/api', () => ({
  queryPoint: vi.fn(),
  queryArea: vi.fn(),
}))

import { useMapQuery } from '../hooks/useMapQuery'
import { queryPoint } from '../services/api'
import type { PointQueryResult } from '../types'

it('invalidates the active request generation during unmount cleanup', async () => {
  let resolve!: (value: PointQueryResult) => void
  const request = new Promise<PointQueryResult>((resolvePromise) => {
    resolve = resolvePromise
  })
  vi.mocked(queryPoint).mockReturnValueOnce(request)
  const { result, unmount } = renderHook(() => useMapQuery('ndvi', '2025-06'))

  act(() => {
    void result.current.queryPointAt(39, 116)
  })
  const generationRef = observedRefs.find((ref) => typeof ref.current === 'number')
  expect(generationRef).toBeDefined()
  const generationBeforeUnmount = generationRef!.current as number

  unmount()

  expect(generationRef!.current).toBe(generationBeforeUnmount + 1)
  resolve({
    layerId: 'ndvi',
    time: '2025-06',
    lng: 116,
    lat: 39,
    value: 0.5,
    unit: '指数',
  })
  await request
})
