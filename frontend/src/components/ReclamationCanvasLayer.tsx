import { useCallback, useEffect, useRef } from 'react'
import L from 'leaflet'
import { useMap } from 'react-leaflet'
import {
  buildScreenIndex,
  circleRadiusPixels,
  classifyReclamationValue,
  drawBasePoints,
  drawHoverPoint,
  hitTestScreenIndex,
  isReclaimable,
  scenarioMetrics,
  type ScreenIndex,
  type ScreenPoint,
} from './reclamationCanvas'
import type { ReclamationPoint, ReclamationScenario } from '../types'

interface ReclamationCanvasLayerProps {
  points: ReclamationPoint[]
  scenario: ReclamationScenario
  color: string
  onPointSelect: (point: ReclamationPoint) => void
}

interface PointerPosition {
  x: number
  y: number
}

export default function ReclamationCanvasLayer({
  points,
  scenario,
  color,
  onPointSelect,
}: ReclamationCanvasLayerProps) {
  const map = useMap()
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const baseCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const hoverCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const projectedRef = useRef<ScreenPoint[]>([])
  const screenIndexRef = useRef<ScreenIndex | null>(null)
  const hoveredIndexRef = useRef<number | null>(null)
  const animationFrameRef = useRef<number | null>(null)
  const pointerPositionRef = useRef<PointerPosition | null>(null)
  const previousCursorRef = useRef('')
  const inputsRef = useRef({ points, scenario, color, onPointSelect })
  const redrawRef = useRef<() => void>(() => undefined)

  inputsRef.current = { points, scenario, color, onPointSelect }

  const restoreCursor = useCallback(() => {
    map.getContainer().style.cursor = previousCursorRef.current
  }, [map])

  const redrawHover = useCallback((nextIndex: number | null) => {
    const hoverCanvas = hoverCanvasRef.current
    const { scenario: currentScenario, color: currentColor } = inputsRef.current
    if (!hoverCanvas) return

    const context = hoverCanvas.getContext('2d')
    if (!context) return

    const size = map.getSize()
    drawHoverPoint(
      context,
      nextIndex === null ? null : projectedRef.current[nextIndex] ?? null,
      currentScenario,
      currentColor,
      size.x,
      size.y,
    )
  }, [map])

  const redraw = useCallback(() => {
    const wrapper = wrapperRef.current
    const baseCanvas = baseCanvasRef.current
    const hoverCanvas = hoverCanvasRef.current
    if (!wrapper || !baseCanvas || !hoverCanvas) return

    const { points: currentPoints, scenario: currentScenario, color: currentColor } = inputsRef.current
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

    const projected = currentPoints.map((point, sourceIndex) => {
      const screen = map.latLngToContainerPoint([point.latitude, point.longitude])
      const metrics = scenarioMetrics(point, currentScenario)
      return {
        sourceIndex,
        x: screen.x,
        y: screen.y,
        radius: circleRadiusPixels(point.latitude, map.getZoom()),
        reclaimable: isReclaimable(metrics),
        reclamationValueClass: classifyReclamationValue(metrics),
      }
    })

    projectedRef.current = projected
    screenIndexRef.current = buildScreenIndex(projected)
    hoveredIndexRef.current = null
    restoreCursor()

    const baseContext = baseCanvas.getContext('2d')
    if (baseContext) drawBasePoints(baseContext, projected, currentScenario, currentColor)
    redrawHover(null)
  }, [map, redrawHover, restoreCursor])

  redrawRef.current = redraw

  useEffect(() => {
    const overlayPane = map.getPane('overlayPane')
    if (!overlayPane) return undefined

    const wrapper = document.createElement('div')
    wrapper.dataset.reclamationCanvasLayer = ''
    wrapper.dataset.testid = 'reclamation-canvas-layer'
    Object.assign(wrapper.style, {
      position: 'absolute',
      pointerEvents: 'none',
    })

    const createCanvas = () => {
      const canvas = document.createElement('canvas')
      Object.assign(canvas.style, {
        position: 'absolute',
        inset: '0',
        pointerEvents: 'none',
      })
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

    const updateHover = () => {
      animationFrameRef.current = null
      const position = pointerPositionRef.current
      const index = position && screenIndexRef.current
        ? hitTestScreenIndex(screenIndexRef.current, position.x, position.y)
        : null
      if (index === hoveredIndexRef.current) return

      hoveredIndexRef.current = index
      mapContainer.style.cursor = index === null ? previousCursorRef.current : 'pointer'
      redrawHover(index)
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
        redrawHover(null)
      }
      restoreCursor()
    }

    const onClick = (event: MouseEvent) => {
      const position = pointForEvent(event)
      const index = screenIndexRef.current
        ? hitTestScreenIndex(screenIndexRef.current, position.x, position.y)
        : null
      if (index !== null) inputsRef.current.onPointSelect(inputsRef.current.points[index])
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
      screenIndexRef.current = null
      projectedRef.current = []
    }
  }, [map, redrawHover, restoreCursor])

  useEffect(() => {
    redraw()
  }, [redraw, points, scenario, color])

  return null
}
