import type { ReactNode } from 'react'
import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MapView from '../components/MapView'
import { queryArea, queryPoint } from '../services/api'
import type { Layer } from '../types'

interface MapEventHandlers {
  click?: (event: { latlng: { lat: number; lng: number } }) => void
  mousedown?: (event: {
    originalEvent: { shiftKey: boolean }
    latlng: { lat: number; lng: number }
  }) => void
  mousemove?: (event: { latlng: { lat: number; lng: number } }) => void
  mouseup?: () => void
}

interface RectangleProps {
  bounds: [[number, number], [number, number]]
}

const mapMocks = vi.hoisted(() => {
  const dragging = {
    disable: vi.fn(),
    enable: vi.fn(),
  }
  return {
    handlers: null as MapEventHandlers | null,
    rectangleProps: null as RectangleProps | null,
    dragging,
    map: {
      dragging,
      removeLayer: vi.fn(),
    },
  }
})

const leafletMocks = vi.hoisted(() => {
  const tileLayerInstance = {
    addTo: vi.fn(),
    setOpacity: vi.fn(),
  }
  return {
    tileLayerInstance,
    tileLayer: vi.fn((_url: string) => tileLayerInstance),
  }
})

vi.mock('leaflet', () => ({
  default: {
    tileLayer: leafletMocks.tileLayer,
    latLng: (lat: number, lng: number) => ({ lat, lng }),
  },
}))

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TileLayer: () => null,
  Rectangle: (props: RectangleProps) => {
    mapMocks.rectangleProps = props
    return null
  },
  Marker: () => null,
  useMap: () => mapMocks.map,
  useMapEvents: (handlers: MapEventHandlers) => {
    mapMocks.handlers = handlers
  },
}))

vi.mock('../services/api', () => ({
  queryPoint: vi.fn(),
  queryArea: vi.fn(),
}))

const mockedQueryPoint = vi.mocked(queryPoint)
const mockedQueryArea = vi.mocked(queryArea)
const baseProps = {
  layers: [],
  activeLayerId: 'ndvi',
  opacity: 1,
  currentTime: '2025-06',
}

describe('MapView interactions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mapMocks.handlers = null
    mapMocks.rectangleProps = null
    mockedQueryArea.mockReturnValue(new Promise(() => undefined))
  })

  it('finishes a Shift selection released outside the map exactly once', () => {
    render(<MapView {...baseProps} />)

    act(() => {
      mapMocks.handlers!.mousedown?.({
        originalEvent: { shiftKey: true },
        latlng: { lat: 40, lng: 117 },
      })
      mapMocks.handlers!.mousemove?.({ latlng: { lat: 39, lng: 116 } })
      document.dispatchEvent(new MouseEvent('mouseup'))
    })

    expect(mapMocks.dragging.disable).toHaveBeenCalledOnce()
    expect(mapMocks.dragging.enable).toHaveBeenCalledOnce()
    expect(mockedQueryArea).toHaveBeenCalledOnce()
    expect(mockedQueryArea).toHaveBeenCalledWith({
      layerId: 'ndvi',
      time: '2025-06',
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [116, 39],
          [117, 39],
          [117, 40],
          [116, 40],
          [116, 39],
        ]],
      },
    })
    expect(mapMocks.rectangleProps?.bounds).toEqual([
      [40, 117],
      [39, 116],
    ])

    act(() => {
      mapMocks.handlers!.mouseup?.()
      document.dispatchEvent(new MouseEvent('mouseup'))
    })

    expect(mapMocks.dragging.enable).toHaveBeenCalledOnce()
    expect(mockedQueryArea).toHaveBeenCalledOnce()
  })

  it('locks dragging only during Shift selection and queries the selected area', () => {
    render(<MapView {...baseProps} />)

    act(() => {
      mapMocks.handlers!.mousedown?.({
        originalEvent: { shiftKey: false },
        latlng: { lat: 39, lng: 116 },
      })
    })
    expect(mapMocks.dragging.disable).not.toHaveBeenCalled()

    act(() => {
      mapMocks.handlers!.mousedown?.({
        originalEvent: { shiftKey: true },
        latlng: { lat: 39, lng: 116 },
      })
      mapMocks.handlers!.mousemove?.({ latlng: { lat: 40, lng: 117 } })
      mapMocks.handlers!.mouseup?.()
    })

    expect(mapMocks.dragging.disable).toHaveBeenCalledOnce()
    expect(mapMocks.dragging.enable).toHaveBeenCalledOnce()
    expect(mockedQueryArea).toHaveBeenCalledWith({
      layerId: 'ndvi',
      time: '2025-06',
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [116, 39],
          [117, 39],
          [117, 40],
          [116, 40],
          [116, 39],
        ]],
      },
    })
  })

  it('restores dragging on unmount when selection is in progress', () => {
    const { unmount } = render(<MapView {...baseProps} />)

    act(() => {
      mapMocks.handlers!.mousedown?.({
        originalEvent: { shiftKey: true },
        latlng: { lat: 39, lng: 116 },
      })
    })
    unmount()

    expect(mapMocks.dragging.disable).toHaveBeenCalledOnce()
    expect(mapMocks.dragging.enable).toHaveBeenCalledOnce()
  })

  it('shows each successful point result in the map query card', async () => {
    const pointResult = {
      layerId: 'ndvi',
      time: '2025-06',
      lng: 116,
      lat: 39,
      value: 0.5,
      unit: '指数',
    }
    mockedQueryPoint.mockResolvedValueOnce(pointResult)
    render(<MapView {...baseProps} />)

    act(() => {
      mapMocks.handlers!.click?.({ latlng: { lat: 39, lng: 116 } })
    })
    expect(await screen.findByRole('heading', { name: '点查询结果' })).toBeInTheDocument()
    expect(screen.getByText('0.5000 指数')).toBeInTheDocument()
  })

  it('lets the backend own SSM palette parameters in the tile URL', () => {
    const ssmLayer: Layer = {
      id: 'ssm',
      name: '土壤湿度',
      description: '土壤湿度',
      type: 'raster',
      unit: '%',
      range: { min: 0, max: 100 },
      timeRange: { start: '2025-01', end: '2025-12', step: 'month' },
      tileTemplate: '',
      legend: [],
    }

    render(<MapView {...baseProps} layers={[ssmLayer]} activeLayerId="ssm" />)

    expect(leafletMocks.tileLayer).toHaveBeenCalledOnce()
    const url = leafletMocks.tileLayer.mock.calls[0][0]
    expect(url).toContain('/data/ssm-tiles/WebMercatorQuad/{z}/{x}/{y}.png?')
    expect(url).toContain('time=2025-06')
    expect(url).not.toContain('colormap_name')
    expect(url).not.toContain('rescale')
    expect(url).not.toContain('rdylgn')
  })
})
