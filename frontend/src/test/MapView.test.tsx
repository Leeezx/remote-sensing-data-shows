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

interface VectorFeature {
  type: 'Feature'
  properties: { id: string; name: string }
  geometry: { type: 'Polygon'; coordinates: number[][][] }
}

interface FeatureLayerMocks {
  id: string
  pane: string | undefined
  handlers: Record<string, (event?: { originalEvent?: Event }) => void>
  setStyle: ReturnType<typeof vi.fn>
  bringToFront: ReturnType<typeof vi.fn>
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
      getZoom: vi.fn(() => 10),
      on: vi.fn(),
      off: vi.fn(),
      fitBounds: vi.fn(),
    },
    geoJsonFeatureIds: [] as string[][],
    featureLayers: [] as FeatureLayerMocks[],
    panes: [] as Array<{ name: string; zIndex: number | string | undefined }>,
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
    bounds: {
      extend: vi.fn(),
      isValid: vi.fn(() => true),
    },
  }
})

vi.mock('leaflet', () => ({
  default: {
    tileLayer: leafletMocks.tileLayer,
    latLng: (lat: number, lng: number) => ({ lat, lng }),
    latLngBounds: () => leafletMocks.bounds,
    DomEvent: { stopPropagation: vi.fn() },
  },

}))

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Pane: ({ name, style, children }: {
    name: string
    style?: { zIndex?: number | string }
    children: ReactNode
  }) => {
    mapMocks.panes.push({ name, zIndex: style?.zIndex })
    return <>{children}</>
  },
  TileLayer: () => null,
  Rectangle: (props: RectangleProps) => {
    mapMocks.rectangleProps = props
    return null
  },
  Marker: () => null,
  GeoJSON: ({
    data,
    onEachFeature,
    pane,
  }: {
    data: { features: VectorFeature[] }
    pane?: string
    onEachFeature: (feature: VectorFeature, layer: {
      on: (handlers: Record<string, (event?: { originalEvent?: Event }) => void>) => void
      setStyle: ReturnType<typeof vi.fn>
      bringToFront: ReturnType<typeof vi.fn>
      unbindTooltip: ReturnType<typeof vi.fn>
    }) => void
  }) => {
    const ids = data.features.map((feature) => feature.properties.id)
    if (!mapMocks.geoJsonFeatureIds.some((existing) => (
      existing.length === ids.length && existing.every((id, index) => id === ids[index])
    ))) {
      mapMocks.geoJsonFeatureIds.push(ids)
    }
    for (const feature of data.features) {
      const handlers: Record<string, (event?: { originalEvent?: Event }) => void> = {}
      const setStyle = vi.fn()
      const bringToFront = vi.fn()
      onEachFeature(feature, {
        on: (next) => Object.assign(handlers, next),
        setStyle,
        bringToFront,
        unbindTooltip: vi.fn(),
      })
      mapMocks.featureLayers.push({
        id: feature.properties.id,
        pane,
        handlers,
        setStyle,
        bringToFront,
      })
    }
    return (
      <div
        data-testid="region-geojson"
        data-first-feature-id={ids[0] ?? ''}
        data-feature-count={data.features.length}
      />
    )
  },
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

const vectorFixture = (id: string, name: string) => ({
  type: 'FeatureCollection' as const,
  features: [{
    type: 'Feature' as const,
    properties: { id, name },
    geometry: {
      type: 'Polygon' as const,
      coordinates: [[[100, 30], [101, 30], [101, 31], [100, 30]]],
    },
  }],
})

describe('MapView interactions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mapMocks.handlers = null
    mapMocks.rectangleProps = null
    mapMocks.geoJsonFeatureIds = []
    mapMocks.featureLayers = []
    mapMocks.panes = []
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

  it('mounts the largest real county feature count well within one second', () => {
    const features: VectorFeature[] = Array.from({ length: 81 }, (_, index) => ({
      type: 'Feature',
      properties: { id: `township_${index}`, name: `乡镇${index}` },
      geometry: {
        type: 'Polygon',
        coordinates: [[[100, 30], [101, 30], [101, 31], [100, 30]]],
      },
    }))
    const started = performance.now()

    render(
      <MapView
        {...baseProps}
        regionVector={{ type: 'FeatureCollection', features }}
        regionLevel="township"
        onRegionSelect={vi.fn()}
      />,
    )

    expect(performance.now() - started).toBeLessThan(1000)
    expect(screen.getByTestId('region-geojson')).toHaveAttribute('data-feature-count', '81')
    expect(mapMocks.geoJsonFeatureIds).toEqual([features.map((feature) => feature.properties.id)])
    expect(mapMocks.map.fitBounds).toHaveBeenCalledOnce()
  })

  it('refuses to mount a township payload above the 499-layer guard', () => {
    const features: VectorFeature[] = Array.from({ length: 500 }, (_, index) => ({
      type: 'Feature',
      properties: { id: `township_${index}`, name: `乡镇${index}` },
      geometry: {
        type: 'Polygon',
        coordinates: [[[100, 30], [101, 30], [101, 31], [100, 30]]],
      },
    }))

    render(
      <MapView
        {...baseProps}
        regionVector={{ type: 'FeatureCollection', features }}
        regionLevel="township"
        onRegionSelect={vi.fn()}
      />,
    )

    expect(screen.queryByTestId('region-geojson')).not.toBeInTheDocument()
    expect(mapMocks.geoJsonFeatureIds).toEqual([])
  })

  it('keeps the county overlay while mounting the township detail overlay above it', () => {
    const county = {
      type: 'FeatureCollection' as const,
      features: [{
        type: 'Feature' as const,
        properties: { id: 'county_a', name: '示范县A' },
        geometry: { type: 'Polygon' as const, coordinates: [[[100, 30], [101, 30], [100, 30]]] },
      }],
    }
    const township = {
      type: 'FeatureCollection' as const,
      features: [{
        type: 'Feature' as const,
        properties: { id: 'township_a1', name: '示范镇A1' },
        geometry: { type: 'Polygon' as const, coordinates: [[[100, 30], [100.5, 30], [100, 30]]] },
      }],
    }

    render(
      <MapView
        {...baseProps}
        regionVector={county}
        regionLevel="county"
        onRegionSelect={vi.fn()}
        detailRegionVector={township}

        detailRegionLevel="township"
        onDetailRegionSelect={vi.fn()}
      />,
    )

    expect(mapMocks.geoJsonFeatureIds).toEqual([['county_a'], ['township_a1']])
    expect(screen.getAllByTestId('region-geojson')).toHaveLength(2)
    expect(mapMocks.map.fitBounds).toHaveBeenCalledOnce()
  })

  it('restores county color after hover without moving the layer to front', () => {
    const countyColorMap = new Map([['county_a', '#2563eb']])
    render(<MapView
      {...baseProps}
      regionVector={vectorFixture('county_a', '示范县A')}
      regionLevel="county"
      regionColorMap={countyColorMap}
      onRegionSelect={vi.fn()}
    />)

    const layer = mapMocks.featureLayers.find((item) => item.id === 'county_a')!
    act(() => layer.handlers.mouseover?.())
    expect(layer.setStyle).toHaveBeenLastCalledWith(expect.objectContaining({ fillColor: '#14b8a6' }))

    act(() => layer.handlers.mouseout?.())
    expect(layer.setStyle).toHaveBeenLastCalledWith(expect.objectContaining({ fillColor: '#2563eb' }))
    expect(layer.bringToFront).not.toHaveBeenCalled()
  })

  it('renders township features in a higher fixed pane and forwards their click', () => {
    const onTownshipSelect = vi.fn()
    render(<MapView
      {...baseProps}
      regionVector={vectorFixture('county_a', '示范县A')}
      regionLevel="county"
      onRegionSelect={vi.fn()}
      detailRegionVector={vectorFixture('township_a1', '示范镇A1')}
      detailRegionLevel="township"
      onDetailRegionSelect={onTownshipSelect}
    />)

    const countyPane = mapMocks.panes.find((item) => item.name === 'county-regions')!
    const townshipPane = mapMocks.panes.find((item) => item.name === 'township-regions')!
    expect(Number(townshipPane.zIndex)).toBeGreaterThan(Number(countyPane.zIndex))

    const township = mapMocks.featureLayers.find((item) => item.id === 'township_a1')!
    expect(township.pane).toBe('township-regions')
    act(() => township.handlers.mouseover?.())
    expect(township.setStyle).toHaveBeenCalled()
    act(() => township.handlers.click?.({ originalEvent: new MouseEvent('click') }))
    expect(onTownshipSelect).toHaveBeenCalledWith({ id: 'township_a1', name: '示范镇A1' })
  })

  it('restores the latest county style after a color and selection rerender', () => {
    const county = vectorFixture('county_a', '示范县A')
    const onRegionSelect = vi.fn()
    const { rerender } = render(<MapView
      {...baseProps}
      regionVector={county}
      regionLevel="county"
      regionColorMap={new Map([['county_a', '#2563eb']])}
      onRegionSelect={onRegionSelect}
    />)

    const layer = mapMocks.featureLayers.find((item) => item.id === 'county_a')!
    rerender(<MapView
      {...baseProps}
      regionVector={county}
      regionLevel="county"
      selectedRegionId="county_a"
      regionColorMap={new Map([['county_a', '#dc2626']])}
      onRegionSelect={onRegionSelect}
    />)

    act(() => layer.handlers.mouseout?.())
    expect(layer.setStyle).toHaveBeenLastCalledWith(expect.objectContaining({
      color: '#b45309',
      fillColor: '#f59e0b',
    }))
  })


  it('dispatches an existing county layer click through the latest callback', () => {
    const county = vectorFixture('county_a', '示范县A')
    const countyModeSelect = vi.fn()
    const townshipModeSelect = vi.fn()
    const { rerender } = render(
      <MapView
        {...baseProps}
        regionVector={county}
        regionLevel="county"
        onRegionSelect={countyModeSelect}
      />,
    )
    const mountedCountyLayer = mapMocks.featureLayers.find(
      (item) => item.id === 'county_a',
    )!

    rerender(
      <MapView
        {...baseProps}
        regionVector={county}
        regionLevel="county"
        onRegionSelect={townshipModeSelect}
      />,
    )

    act(() => {
      mountedCountyLayer.handlers.click?.({
        originalEvent: new MouseEvent('click'),
      })
    })

    expect(countyModeSelect).not.toHaveBeenCalled()
    expect(townshipModeSelect).toHaveBeenCalledWith({
      id: 'county_a',
      name: '示范县A',
    })
  })

  it('keeps region overlay hooks stable while region data loads', () => {
    const { rerender } = render(<MapView
      {...baseProps}
      regionLevel="county"
    />)

    rerender(<MapView
      {...baseProps}
      regionVector={vectorFixture('county_a', '示范县A')}
      regionLevel="county"
      onRegionSelect={vi.fn()}
    />)

    expect(screen.getByTestId('region-geojson')).toHaveAttribute('data-first-feature-id', 'county_a')
  })

  it('clears an existing point result when administrative statistics disables queries', async () => {
    mockedQueryPoint.mockResolvedValueOnce({
      layerId: 'ndvi', time: '2025-06', lng: 116, lat: 39, value: 0.5, unit: '指数',
    })
    const { rerender } = render(<MapView {...baseProps} />)

    act(() => mapMocks.handlers!.click?.({ latlng: { lat: 39, lng: 116 } }))
    expect(await screen.findByRole('heading', { name: '点查询结果' })).toBeInTheDocument()

    rerender(<MapView {...baseProps} disableQuery />)

    expect(screen.queryByRole('heading', { name: '点查询结果' })).not.toBeInTheDocument()
    act(() => mapMocks.handlers!.click?.({ latlng: { lat: 40, lng: 117 } }))
    expect(mockedQueryPoint).toHaveBeenCalledOnce()
  })
})
