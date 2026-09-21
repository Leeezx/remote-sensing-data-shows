import { useEffect, type ReactNode } from 'react'
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import WaterDemandMap from '../components/WaterDemandMap'
import type {
  WaterDemandOverviewResponse,
  WaterDemandPointGrid,
  WaterDemandRegionProperties,
} from '../types'

const fakeMap = vi.hoisted(() => ({
  fitBounds: vi.fn(),
}))

const tileLayerProps = vi.hoisted(() => ({
  maxZoom: null as number | null,
  maxNativeZoom: null as number | null,
}))

const geoJsonLayers = vi.hoisted((): Array<{ data: unknown; style?: () => { className?: string } }> => [])

const canvasProps = vi.hoisted(() => ({
  current: null as Record<string, unknown> | null,
}))

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TileLayer: (props: { maxZoom?: number; maxNativeZoom?: number }) => {
    tileLayerProps.maxZoom = props.maxZoom ?? null
    tileLayerProps.maxNativeZoom = props.maxNativeZoom ?? null
    return null
  },
  Pane: ({ children }: { children: ReactNode }) => <>{children}</>,
  GeoJSON: ({ data, style }: { data: unknown; style?: () => { className?: string } }) => {
    useEffect(() => {
      geoJsonLayers.push({ data, style })
    }, [data, style])
    return null
  },
  useMap: () => fakeMap,
}))

vi.mock('../components/WaterDemandCanvasLayer', () => ({
  default: (props: Record<string, unknown>) => {
    canvasProps.current = props
    return <div data-testid="water-demand-canvas-layer">画布</div>
  },
}))

const region: WaterDemandRegionProperties = {
  id: 'WR-DEMO-1',
  name: '半干旱区',
  pointCount: 4,
  bounds: [[29.1, 73.7], [49.9, 121.3]],
}

const overview: WaterDemandOverviewResponse = {
  schemaVersion: 1,
  unit: 'mm',
  metrics: [],
  valueFields: [],
  legend: [
    { value: 1, color: '#F08A85', label: '立即补水' },
    { value: 2, color: '#F2C744', label: '优先补水' },
    { value: 3, color: '#7BC47F', label: '观察复核' },
  ],
  chinaOutline: { type: 'Polygon', coordinates: [] },
  regions: {
    type: 'FeatureCollection',
    features: [{ type: 'Feature', properties: region, geometry: { type: 'Polygon', coordinates: [] } }],
  },
}

const colors: Record<1 | 2 | 3, string> = { 1: '#F08A85', 2: '#F2C744', 3: '#7BC47F' }

const grid: WaterDemandPointGrid = {
  pointCount: 4,
  lonAxis: new Float64Array([100, 100.01]),
  latAxis: new Float64Array([30, 30.01]),
  gx: Uint16Array.from([0, 1, 0, 1]),
  gy: Uint16Array.from([0, 0, 1, 1]),
  values: new Uint16Array(24),
  classes: Uint8Array.from([1, 2, 3, 1]),
  minimums: new Float64Array(6),
  maximums: new Float64Array(6),
}

function renderMap(props: Partial<Parameters<typeof WaterDemandMap>[0]> = {}) {
  return render(
    <WaterDemandMap
      overview={overview}
      region={region}
      highlighted={false}
      grid={grid}
      classColors={colors}
      selectedIndex={null}
      onPointSelect={() => undefined}
      {...props}
    />,
  )
}

describe('WaterDemandMap', () => {
  beforeEach(() => {
    geoJsonLayers.length = 0
    canvasProps.current = null
    fakeMap.fitBounds.mockReset()
  })

  afterEach(() => {
    geoJsonLayers.length = 0
  })

  it('fits the national extent while the demo region is highlighted', () => {
    renderMap({ highlighted: true, grid: null })

    expect(fakeMap.fitBounds).toHaveBeenCalledWith([[15, 73], [54, 135]], {
      padding: [20, 20],
      animate: true,
    })
  })

  it('fits the demo region bounds after drilling in', () => {
    renderMap({ highlighted: false })

    expect(fakeMap.fitBounds).toHaveBeenCalledWith(region.bounds, {
      padding: [32, 32],
      animate: true,
    })
  })

  it('draws the pulsing highlight style only in the national view', () => {
    const { unmount } = renderMap({ highlighted: true, grid: null })
    const highlighted = geoJsonLayers.at(-1)?.style?.()
    expect(highlighted?.className).toBe('reclamation-region-pulse')
    unmount()

    geoJsonLayers.length = 0
    renderMap({ highlighted: false })
    const drilled = geoJsonLayers.at(-1)?.style?.()
    expect(drilled?.className).toBeUndefined()
  })

  it('mounts the canvas layer only after drilling in with point data', () => {
    const { unmount } = renderMap({ highlighted: true, grid: null })
    expect(screen.queryByTestId('water-demand-canvas-layer')).not.toBeInTheDocument()
    unmount()

    renderMap({ highlighted: false })
    expect(screen.getByTestId('water-demand-canvas-layer')).toBeInTheDocument()
    expect(canvasProps.current?.grid).toBe(grid)
  })

  it('sets the base tile zoom limits used by the other analysis pages', () => {
    renderMap()

    expect(tileLayerProps.maxZoom).toBe(13)
    expect(tileLayerProps.maxNativeZoom).toBe(8)
  })
})
