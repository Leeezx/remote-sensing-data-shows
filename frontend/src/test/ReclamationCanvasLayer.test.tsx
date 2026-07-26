import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ReclamationCanvasLayer from '../components/ReclamationCanvasLayer'
import type { ReclamationPoint } from '../types'

const overlayPane = document.createElement('div')
const mapContainer = document.createElement('div')
document.body.append(overlayPane, mapContainer)

const mapMocks = vi.hoisted(() => ({
  on: vi.fn(),
  off: vi.fn(),
  getPane: vi.fn(),
  getContainer: vi.fn(),
  getSize: vi.fn(),
  getZoom: vi.fn(),
  latLngToContainerPoint: vi.fn(),
  containerPointToLayerPoint: vi.fn(),
}))

vi.mock('react-leaflet', () => ({
  useMap: () => mapMocks,
}))

const pointFixture: ReclamationPoint[] = [
  {
    id: 'reclaimable',
    longitude: 100,
    latitude: 40,
    current: {
      reclamationValue: 8,
      waterConsumption: 2,
      yieldValue: 3,
      soilCarbonValue: 4,
    },
    future: {
      reclamationValue: 12,
      waterConsumption: 2,
      yieldValue: 3,
      soilCarbonValue: 4,
    },
  },
  {
    id: 'nodata',
    longitude: 101,
    latitude: 40,
    current: {
      reclamationValue: -999,
      waterConsumption: -999,
      yieldValue: -999,
      soilCarbonValue: -999,
    },
    future: {
      reclamationValue: -999,
      waterConsumption: -999,
      yieldValue: -999,
      soilCarbonValue: -999,
    },
  },
]

function fakeCanvasContext(): CanvasRenderingContext2D {
  return {
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    clearRect: vi.fn(),
    setTransform: vi.fn(),
  } as unknown as CanvasRenderingContext2D
}

function mouseEventAt(type: string, clientX: number, clientY: number): MouseEvent {
  return new MouseEvent(type, { bubbles: true, clientX, clientY })
}

describe('ReclamationCanvasLayer', () => {
  let onPointSelect = vi.fn<(point: ReclamationPoint) => void>()
  let getContext: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    overlayPane.replaceChildren()
    mapContainer.replaceChildren()
    mapContainer.style.cursor = 'crosshair'
    vi.clearAllMocks()
    onPointSelect = vi.fn<(point: ReclamationPoint) => void>()
    mapMocks.getPane.mockReturnValue(overlayPane)
    mapMocks.getContainer.mockReturnValue(mapContainer)
    mapMocks.getSize.mockReturnValue({ x: 320, y: 180 })
    mapMocks.getZoom.mockReturnValue(10)
    mapMocks.latLngToContainerPoint.mockImplementation((latLng: [number, number]) => (
      latLng[1] === 100 ? { x: 100, y: 80 } : { x: 200, y: 80 }
    ))
    mapMocks.containerPointToLayerPoint.mockReturnValue({ x: 0, y: 0 })
    getContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext')
      .mockImplementation(() => fakeCanvasContext())
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    Object.defineProperty(window, 'devicePixelRatio', {
      configurable: true,
      value: 1,
    })
  })

  afterEach(() => {
    getContext.mockRestore()
    vi.unstubAllGlobals()
  })

  function renderCanvasLayer() {
    return render(
      <ReclamationCanvasLayer
        points={pointFixture}
        scenario="current"
        color="#16A34A"
        onPointSelect={onPointSelect}
      />,
    )
  }

  it('mounts exactly one overlay wrapper with base and highlight canvases', () => {
    const { unmount } = renderCanvasLayer()

    expect(overlayPane.querySelectorAll('[data-reclamation-canvas-layer]')).toHaveLength(1)
    expect(overlayPane.querySelectorAll('canvas')).toHaveLength(2)
    expect(overlayPane.querySelectorAll('svg')).toHaveLength(0)

    unmount()

    expect(overlayPane.querySelectorAll('canvas')).toHaveLength(0)
  })

  it('highlights and selects only reclaimable points', () => {
    renderCanvasLayer()

    act(() => {
      mapContainer.dispatchEvent(mouseEventAt('mousemove', 100, 80))
      mapContainer.dispatchEvent(mouseEventAt('click', 100, 80))
    })
    expect(onPointSelect).toHaveBeenCalledWith(pointFixture[0])
    expect(mapContainer.style.cursor).toBe('pointer')

    act(() => {
      mapContainer.dispatchEvent(mouseEventAt('click', 200, 80))
    })
    expect(onPointSelect).toHaveBeenCalledTimes(1)
  })

  it('removes map handlers and redraws a scenario switch without adding canvases', () => {
    const { rerender, unmount } = renderCanvasLayer()

    rerender(
      <ReclamationCanvasLayer
        points={pointFixture}
        scenario="future"
        color="#2563EB"
        onPointSelect={onPointSelect}
      />,
    )

    expect(overlayPane.querySelectorAll('[data-reclamation-canvas-layer]')).toHaveLength(1)
    expect(overlayPane.querySelectorAll('canvas')).toHaveLength(2)

    unmount()

    expect(mapMocks.off).toHaveBeenCalledWith('moveend', expect.any(Function))
    expect(mapMocks.off).toHaveBeenCalledWith('zoomend', expect.any(Function))
    expect(mapMocks.off).toHaveBeenCalledWith('resize', expect.any(Function))
    expect(mapContainer.style.cursor).toBe('crosshair')
  })
})
