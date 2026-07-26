// oxlint-disable react-hooks/exhaustive-deps -- the GeoJSON mock intentionally binds only on mount.
import { useEffect, useRef, type ReactNode } from 'react'
import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReclamationMap from '../components/ReclamationMap'
import type {
  ReclamationOverviewWireResponse,
  ReclamationPoint,
  ReclamationRegionProperties,
} from '../types'

interface GeoJsonLayer {
  data: unknown
  style: (feature: ReclamationFeature) => { className?: string }
  onEachFeature?: (feature: ReclamationFeature, layer: FeatureLayer) => void
}

interface ReclamationFeature {
  type: 'Feature'
  properties: ReclamationRegionProperties
  geometry: { type: string; coordinates: unknown }
}

interface FeatureLayer {
  on: (handlers: Record<string, (event?: { originalEvent?: Event }) => void>) => void
}

const fakeMap = vi.hoisted(() => ({
  fitBounds: vi.fn(),
}))

const geoJsonLayers = vi.hoisted((): GeoJsonLayer[] => [])
const featureLayers = vi.hoisted((): Array<{
  feature: ReclamationFeature
  handlers: Record<string, (event?: { originalEvent?: Event }) => void>
}> => [])

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TileLayer: () => null,
  Pane: ({ children }: { children: ReactNode }) => <>{children}</>,
  GeoJSON: ({ data, style, onEachFeature }: GeoJsonLayer) => {
    const initialOnEachFeature = useRef(onEachFeature)

    useEffect(() => {
      geoJsonLayers.push({ data, style, onEachFeature: initialOnEachFeature.current })
      const createdLayers: typeof featureLayers = []
      if (initialOnEachFeature.current && typeof data === 'object' && data !== null && 'features' in data) {
        for (const feature of (data as { features: ReclamationFeature[] }).features) {
          const handlers: Record<string, (event?: { originalEvent?: Event }) => void> = {}
          initialOnEachFeature.current(feature, { on: (next) => Object.assign(handlers, next) })
          const createdLayer = { feature, handlers }
          createdLayers.push(createdLayer)
          featureLayers.push(createdLayer)
        }
      }

      return () => {
        for (const createdLayer of createdLayers) {
          const index = featureLayers.indexOf(createdLayer)
          if (index >= 0) featureLayers.splice(index, 1)
        }
      }
    }, [])

    return null
  },
  useMap: () => fakeMap,
}))

vi.mock('../components/ReclamationCanvasLayer', () => ({
  default: () => <div data-testid="reclamation-canvas-layer" />,
}))

const overview: ReclamationOverviewWireResponse = {
  schemaVersion: 1,
  unit: 'thousand_usd',
  chinaOutline: {
    type: 'Polygon',
    coordinates: [[[73, 15], [135, 15], [135, 54], [73, 15]]],
  },
  metrics: [],
  regions: {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: {
          id: 'ningxia',
          name: '宁夏示范区',
          pointCount: 2,
          bounds: [[37.2, 104.6], [41.8, 112.8]],
        },
        geometry: {
          type: 'Polygon',
          coordinates: [[[104.6, 37.2], [112.8, 37.2], [112.8, 41.8], [104.6, 37.2]]],
        },
      },
      ...['gansu', 'xinjiang', 'inner-mongolia'].map((id, index) => ({
        type: 'Feature' as const,
        properties: {
          id,
          name: `示范区${index + 2}`,
          pointCount: 1,
          bounds: [[30 + index, 90 + index], [31 + index, 91 + index]] as [[number, number], [number, number]],
        },
        geometry: {
          type: 'Polygon',
          coordinates: [[[90 + index, 30 + index], [91 + index, 30 + index], [91 + index, 31 + index], [90 + index, 30 + index]]],
        },
      })),
    ],
  },
}

const points: ReclamationPoint[] = [{
  id: 'point-1',
  longitude: 106,
  latitude: 39,
  current: { reclamationValue: 12, waterConsumption: 2, yieldValue: 3, soilCarbonValue: 4 },
  future: { reclamationValue: 15, waterConsumption: 2, yieldValue: 3, soilCarbonValue: 4 },
}]

const onRegionSelect = vi.fn()
const onPointSelect = vi.fn()

const overviewProps = {
  overview,
  points,
  scenario: 'current' as const,
  onRegionSelect,
  onPointSelect,
}

describe('ReclamationMap', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    geoJsonLayers.length = 0
    featureLayers.length = 0
  })

  it('shows China and four pulsing demo polygons before selection', () => {
    render(<ReclamationMap {...overviewProps} selectedRegion={null} points={[]} />)

    expect(geoJsonLayers).toHaveLength(2)
    expect(geoJsonLayers[0].data).toEqual(overview.chinaOutline)
    expect((geoJsonLayers[1].data as typeof overview.regions).features).toHaveLength(4)
    expect(geoJsonLayers[1].style(overview.regions.features[0]).className)
      .toContain('reclamation-region-pulse')
    expect(screen.queryByTestId('reclamation-canvas-layer')).not.toBeInTheDocument()
  })

  it('selects a typed demo region when its polygon is clicked', () => {
    render(<ReclamationMap {...overviewProps} selectedRegion={null} points={[]} />)

    act(() => featureLayers[0].handlers.click?.({ originalEvent: new MouseEvent('click') }))

    expect(onRegionSelect).toHaveBeenCalledWith({
      id: 'ningxia',
      name: '宁夏示范区',
      pointCount: 2,
      bounds: [[37.2, 104.6], [41.8, 112.8]],
    })
  })

  it('fits the clicked region and mounts one canvas layer after data arrives', () => {
    render(<ReclamationMap
      {...overviewProps}
      selectedRegion={overview.regions.features[0].properties}
    />)

    expect(fakeMap.fitBounds).toHaveBeenCalledWith(
      [[37.2, 104.6], [41.8, 112.8]],
      expect.objectContaining({ padding: [32, 32], animate: true }),
    )
    expect(screen.getByTestId('reclamation-canvas-layer')).toBeInTheDocument()
  })

  it('does not bind region click handlers after a region is selected', () => {
    render(<ReclamationMap
      {...overviewProps}
      selectedRegion={overview.regions.features[0].properties}
    />)

    expect(featureLayers).toHaveLength(0)
  })

  it('removes overview region click handlers when transitioning to a selected region', () => {
    const { rerender } = render(<ReclamationMap {...overviewProps} selectedRegion={null} points={[]} />)

    expect(featureLayers).toHaveLength(4)

    rerender(<ReclamationMap
      {...overviewProps}
      selectedRegion={overview.regions.features[0].properties}
    />)

    expect(featureLayers).toHaveLength(0)
    act(() => featureLayers[0]?.handlers.click?.({ originalEvent: new MouseEvent('click') }))
    expect(onRegionSelect).not.toHaveBeenCalled()
  })
})
