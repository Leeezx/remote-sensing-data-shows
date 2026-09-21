import { useCallback, useEffect, useRef } from 'react'
import L from 'leaflet'
import { useMap } from 'react-leaflet'
import {
  buildRowStarts,
  buildTierIndex,
  drawBasePoints,
  drawHoverPoint,
  hitTestPoint,
  projectPoints,
  typicalSpacingDegrees,
  type ProjectedPoints,
  type TierIndex,
} from './waterDemandCanvas'
import type { WaterDemandPointGrid } from '../types'

interface WaterDemandCanvasLayerProps {
  grid: WaterDemandPointGrid
  colors: Record<1 | 2 | 3, string>
  selectedIndex: number | null
  onPointSelect: (index: number) => void
}

interface PointerPosition {
  x: number
  y: number
}

export default function WaterDemandCanvasLayer({
  grid,
  colors,
  selectedIndex,
  onPointSelect,
}: WaterDemandCanvasLayerProps) {
  const map = useMap()
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const baseCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const hoverCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const projectedRef = useRef<ProjectedPoints | null>(null)
  const rowStartsRef = useRef<Uint32Array | null>(null)
  const tierRef = useRef<TierIndex | null>(null)
  const hoveredIndexRef = useRef<number | null>(null)
  const animationFrameRef = useRef<number | null>(null)
  const pointerPositionRef = useRef<PointerPosition | null>(null)
  const previousCursorRef = useRef('')
  const redrawRef = useRef<() => void>(() => undefined)
  const inputsRef = useRef({ grid, colors, selectedIndex, onPointSelect })

  inputsRef.current = { grid, colors, selectedIndex, onPointSelect }

  const restoreCursor = useCallback(() => {
    map.getContainer().style.cursor = previousCursorRef.current
  }, [map])

  const highlightAt = useCallback((index: number | null) => {
    if (index === null) return null
    const projected = projectedRef.current
    if (!projected) return null
    return {
      x: projected.positions[index * 2],
      y: projected.positions[index * 2 + 1],
      radius: projected.rowRadius[inputsRef.current.grid.gy[index]],
    }
  }, [])

  const redrawHover = useCallback((index: number | null) => {
    const hoverCanvas = hoverCanvasRef.current
    if (!hoverCanvas) return
    const context = hoverCanvas.getContext('2d')
    if (!context) return

    const grid = inputsRef.current.grid
    const color = inputsRef.current.colors[grid.classes[index ?? 0] as 1 | 2 | 3]
    const size = map.getSize()
    drawHoverPoint(context, highlightAt(index), color, size.x, size.y)
  }, [highlightAt, map])

  const redraw = useCallback(() => {
    const wrapper = wrapperRef.current
    const baseCanvas = baseCanvasRef.current
    const hoverCanvas = hoverCanvasRef.current
    if (!wrapper || !baseCanvas || !hoverCanvas) return

    const { grid: currentGrid, colors: currentColors } = inputsRef.current
    const size = map.getSize()
    const pixelRatio = window.devicePixelRatio || 1

    wrapper.style.width = `${size.x}px`
    wrapper.style.height = `${size.y}px`
    L.DomUtil.setPosition(wrapper, map.containerPointToLayerPoint([0, 0]))

    for (const canvas of [baseCanvas, hoverCanvas]) {
      canvas.width = Math.max(1, Math.round(size.x * pixelRatio))
      canvas.height = Math.max(1, Math.round(size.y * pixelRatio))
      canvas.style.width = `${size.x}px`
      canvas.style.height = `${size.y}px`
      canvas.getContext('2d')?.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
    }

    const projected = projectPoints(
      currentGrid,
      (longitude, latitude) => {
        const point = map.latLngToContainerPoint([latitude, longitude])
        return [point.x, point.y]
      },
      typicalSpacingDegrees(currentGrid.lonAxis),
      map.getZoom(),
    )
    projectedRef.current = projected

    const baseContext = baseCanvas.getContext('2d')
    if (!baseContext) return
    baseContext.clearRect(0, 0, size.x, size.y)
    const tier = tierRef.current
    if (tier) drawBasePoints(baseContext, currentGrid, projected, tier, currentColors, size.x, size.y)

    const selected = inputsRef.current.selectedIndex
    redrawHover(selected !== null ? selected : hoveredIndexRef.current)
  }, [map, redrawHover])

  redrawRef.current = redraw

  // Rebuild the row lookup and tier groups only when the artifact changes.
  useEffect(() => {
    rowStartsRef.current = buildRowStarts(grid.gy, grid.latAxis.length)
    tierRef.current = buildTierIndex(grid.classes)
    redraw()
  }, [grid, redraw])

  useEffect(() => {
    const overlayPane = map.getPane('overlayPane')
    if (!overlayPane) return undefined

    const wrapper = document.createElement('div')
    wrapper.dataset.waterDemandCanvasLayer = ''
    wrapper.dataset.testid = 'water-demand-canvas-layer'
    Object.assign(wrapper.style, { position: 'absolute', pointerEvents: 'none' })

    const createCanvas = () => {
      const canvas = document.createElement('canvas')
      Object.assign(canvas.style, { position: 'absolute', inset: '0', pointerEvents: 'none' })
      wrapper.append(canvas)
      return canvas
    }

    const baseCanvas = createCanvas()
    const hoverCanvas = createCanvas()
    wrapperRef.current = wrapper
    baseCanvasRef.current = baseCanvas
    hoverCanvasRef.current = hoverCanvas
    overlayPane.append(wrapper)

    const mapContainer = map.getContainer()
    previousCursorRef.current = mapContainer.style.cursor

    const pointForEvent = (event: MouseEvent) => {
      const bounds = mapContainer.getBoundingClientRect()
      return { x: event.clientX - bounds.left, y: event.clientY - bounds.top }
    }

    const locate = (position: PointerPosition) => {
      const projected = projectedRef.current
      const rowStarts = rowStartsRef.current
      if (!projected || !rowStarts) return null
      return hitTestPoint({
        grid: inputsRef.current.grid,
        projected,
        rowStarts,
        x: position.x,
        y: position.y,
      })
    }

    const updateHover = () => {
      animationFrameRef.current = null
      const position = pointerPositionRef.current
      const index = position ? locate(position) : null
      if (index === hoveredIndexRef.current) return

      hoveredIndexRef.current = index
      mapContainer.style.cursor = index === null ? previousCursorRef.current : 'pointer'
      if (inputsRef.current.selectedIndex === null) redrawHover(index)
    }

    const onMouseMove = (event: MouseEvent) => {
      pointerPositionRef.current = pointForEvent(event)
      if (animationFrameRef.current !== null) return
      animationFrameRef.current = requestAnimationFrame(updateHover)
    }

    const onMouseLeave = () => {
      pointerPositionRef.current = null
      if (animationFrameRef.current !== null) {
        cancelAnimationFrame(animationFrameRef.current)
        animationFrameRef.current = null
      }
      if (hoveredIndexRef.current !== null) {
        hoveredIndexRef.current = null
        if (inputsRef.current.selectedIndex === null) redrawHover(null)
      }
      restoreCursor()
    }

    const onClick = (event: MouseEvent) => {
      const index = locate(pointForEvent(event))
      if (index !== null) inputsRef.current.onPointSelect(index)
    }

    const onMapChange = () => redrawRef.current()
    mapContainer.addEventListener('mousemove', onMouseMove)
    mapContainer.addEventListener('mouseleave', onMouseLeave)
    mapContainer.addEventListener('click', onClick)
    map.on('moveend', onMapChange)
    map.on('zoomend', onMapChange)
    map.on('resize', onMapChange)

    return () => {
      if (animationFrameRef.current !== null) cancelAnimationFrame(animationFrameRef.current)
      mapContainer.removeEventListener('mousemove', onMouseMove)
      mapContainer.removeEventListener('mouseleave', onMouseLeave)
      mapContainer.removeEventListener('click', onClick)
      map.off('moveend', onMapChange)
      map.off('zoomend', onMapChange)
      map.off('resize', onMapChange)
      restoreCursor()
      wrapper.remove()
      wrapperRef.current = null
      baseCanvasRef.current = null
      hoverCanvasRef.current = null
      projectedRef.current = null
      rowStartsRef.current = null
      tierRef.current = null
    }
  }, [map, redrawHover, restoreCursor])

  useEffect(() => {
    redraw()
  }, [redraw, grid, colors])

  useEffect(() => {
    redrawHover(selectedIndex)
  }, [redrawHover, selectedIndex])

  return null
}
