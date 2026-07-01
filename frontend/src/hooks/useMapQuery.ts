import { useCallback, useEffect, useRef, useState } from 'react'
import { queryArea, queryPoint } from '../services/api'
import type { MapQueryState } from '../types'

type AreaCorners = [[number, number], [number, number]]

function isNotFound(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'response' in error &&
    typeof error.response === 'object' &&
    error.response !== null &&
    'status' in error.response &&
    error.response.status === 404
  )
}

export function useMapQuery(activeLayerId: string | null, currentTime: string) {
  const [state, setState] = useState<MapQueryState>({ status: 'idle' })
  const requestIdRef = useRef(0)

  const reset = useCallback(() => {
    requestIdRef.current += 1
    setState({ status: 'idle' })
  }, [])

  useEffect(() => {
    reset()
  }, [activeLayerId, currentTime, reset])

  useEffect(() => () => {
    requestIdRef.current += 1
  }, [])

  const queryPointAt = useCallback(async (lat: number, lng: number) => {
    if (!activeLayerId || !currentTime) return

    const requestId = ++requestIdRef.current
    const roundedLat = Number(lat.toFixed(4))
    const roundedLng = Number(lng.toFixed(4))
    setState({ status: 'loading', kind: 'point' })

    try {
      const result = await queryPoint(
        activeLayerId,
        currentTime,
        roundedLng,
        roundedLat,
      )
      if (requestId === requestIdRef.current) setState({ status: 'point', result })
    } catch (error) {
      if (requestId !== requestIdRef.current) return
      setState({
        status: 'error',
        kind: 'point',
        message: isNotFound(error) ? '该位置无有效数据' : '点查询失败，请重试',
      })
    }
  }, [activeLayerId, currentTime])

  const queryAreaBounds = useCallback(async (coords: AreaCorners) => {
    if (!activeLayerId || !currentTime) return

    const requestId = ++requestIdRef.current
    const [[lat1, lng1], [lat2, lng2]] = coords
    const south = Math.min(lat1, lat2)
    const north = Math.max(lat1, lat2)
    const west = Math.min(lng1, lng2)
    const east = Math.max(lng1, lng2)
    setState({ status: 'loading', kind: 'area' })

    try {
      const result = await queryArea({
        layerId: activeLayerId,
        time: currentTime,
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south],
          ]],
        },
      })
      if (requestId === requestIdRef.current) setState({ status: 'area', result })
    } catch (error) {
      if (requestId !== requestIdRef.current) return
      setState({
        status: 'error',
        kind: 'area',
        message: isNotFound(error) ? '该区域无有效数据' : '区域查询失败，请重试',
      })
    }
  }, [activeLayerId, currentTime])

  return { state, queryPointAt, queryAreaBounds, reset }
}
