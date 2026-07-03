import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  MapContainer,
  TileLayer,
  useMap,
  useMapEvents,
  Rectangle,
  Marker,
  GeoJSON,
} from 'react-leaflet'
import L from 'leaflet'
import type { IrrigationVectorGeoJSON, Layer } from '../types'
import { useMapQuery } from '../hooks/useMapQuery'
import QueryCard from './QueryCard'

// ===== Internal hook: tile overlay =====

function TileOverlay({
  layer,
  time,
  opacity,
}: {
  layer: Layer | null
  time: string
  opacity: number
}) {
  const map = useMap()
  const tileLayerRef = useRef<L.TileLayer | null>(null)

  useEffect(() => {
    // Remove previous layer
    if (tileLayerRef.current) {
      map.removeLayer(tileLayerRef.current)
      tileLayerRef.current = null
    }

    if (!layer || !time) return

    let url: string
    if (layer.id === 'ssm') {
      // SSM: backend metadata renderer resolves the time and rendering parameters
      url = `/data/ssm-tiles/WebMercatorQuad/{z}/{x}/{y}.png?` + new URLSearchParams({
        time: time,
      }).toString()
    } else {
      url = layer.tileTemplate
        .replace('{time}', time)
        .replace('{z}', '{z}')
        .replace('{x}', '{x}')
        .replace('{y}', '{y}')
    }

    const tileLayer = L.tileLayer(url, {
      opacity,
      minZoom: 4,
      maxZoom: 13,
      maxNativeZoom: 8,
      errorTileUrl: '',
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any)

    tileLayer.addTo(map)
    tileLayerRef.current = tileLayer

    return () => {
      if (tileLayerRef.current) {
        map.removeLayer(tileLayerRef.current)
        tileLayerRef.current = null
      }
    }
  }, [map, layer, time])

  // update opacity
  useEffect(() => {
    if (tileLayerRef.current) {
      tileLayerRef.current.setOpacity(opacity)
    }
  }, [opacity])

  return null
}

// ===== Internal hook: map events (click, shift+drag) =====

function MapEvents({
  enabled,
  onPointCoords,
  onAreaCoords,
}: {
  enabled: boolean
  onPointCoords: (lat: number, lng: number) => void
  onAreaCoords: (coords: [[number, number], [number, number]]) => void
}) {
  const map = useMap()
  const drawingRef = useRef(false)
  const rectRef = useRef<[number, number][]>([])
  const enabledRef = useRef(enabled)
  const onAreaCoordsRef = useRef(onAreaCoords)
  const globalMouseupRef = useRef<(() => void) | null>(null)

  enabledRef.current = enabled
  onAreaCoordsRef.current = onAreaCoords

  const removeGlobalMouseupListener = useCallback(() => {
    if (!globalMouseupRef.current) return
    document.removeEventListener('mouseup', globalMouseupRef.current)
    globalMouseupRef.current = null
  }, [])

  const finishDrawing = useCallback(() => {
    if (!drawingRef.current) return
    drawingRef.current = false
    removeGlobalMouseupListener()
    map.dragging.enable()
    if (enabledRef.current && rectRef.current.length === 2) {
      onAreaCoordsRef.current(
        rectRef.current as [[number, number], [number, number]],
      )
    }
  }, [map, removeGlobalMouseupListener])

  useEffect(() => () => {
    removeGlobalMouseupListener()
    if (drawingRef.current) {
      drawingRef.current = false
      map.dragging.enable()
    }
  }, [map, removeGlobalMouseupListener])

  useMapEvents({
    click: (e) => {
      if (!enabled) return
      onPointCoords(e.latlng.lat, e.latlng.lng)
    },

    mousedown: (e) => {
      if (!enabled || !e.originalEvent.shiftKey) return
      drawingRef.current = true
      rectRef.current = [[e.latlng.lat, e.latlng.lng]]
      map.dragging.disable()
      globalMouseupRef.current = finishDrawing
      document.addEventListener('mouseup', finishDrawing)
    },

    mousemove: (e) => {
      if (!drawingRef.current) return
      rectRef.current = [rectRef.current[0], [e.latlng.lat, e.latlng.lng]]
    },

    mouseup: finishDrawing,
  })

  return null
}

// ===== Administrative region overlay =====

function RegionOverlay({
  data,
  selectedRegionId,
  onRegionSelect,
  colorMap,
  regionLevel,
}: {
  data: IrrigationVectorGeoJSON | null
  selectedRegionId?: string | null
  onRegionSelect?: (region: { id: string; name: string }) => void
  colorMap?: Map<string, string> | null
  regionLevel?: string | null
}) {
  const map = useMap()
  const [showLabels, setShowLabels] = useState(false)
  const geoLayersRef = useRef<L.Layer[]>([])
  const rafRef = useRef(0)

  // Reset layer ref when data changes (render-phase, before child effects)
  const nextLen = data?.features.length ?? 0
  const prevLenRef = useRef(nextLen)
  if (prevLenRef.current !== nextLen) {
    prevLenRef.current = nextLen
    cancelAnimationFrame(rafRef.current)
    // Unbind tooltips from old layers before clearing
    for (const layer of geoLayersRef.current) {
      try { layer.unbindTooltip() } catch { /* ignore */ }
    }
    geoLayersRef.current = []
  }

  // Zoom → label visibility
  useEffect(() => {
    if (!regionLevel) {
      setShowLabels(false)
      return
    }
    const handler = () => {
      const zoom = map.getZoom()
      setShowLabels(regionLevel === 'village' ? zoom >= 11 : zoom >= 9)
    }
    map.on('zoomend', handler)
    handler()
    return () => {
      map.off('zoomend', handler)
    }
  }, [map, regionLevel])

  // Batch-create or remove tooltips when showLabels changes
  useEffect(() => {
    cancelAnimationFrame(rafRef.current)
    const layers = geoLayersRef.current

    if (!showLabels || layers.length === 0) {
      for (const layer of layers) {
        try { layer.unbindTooltip() } catch { /* ignore */ }
      }
      return
    }

    let i = 0
    const BATCH = 60
    const createBatch = () => {
      const end = Math.min(i + BATCH, layers.length)
      for (; i < end; i++) {
        const layer = layers[i]
        const feature: { properties?: Record<string, unknown> } | undefined =
          (layer as L.Path)?.feature
        if (feature?.properties) {
          const name = String(
            feature.properties.name ?? feature.properties.NAME ?? ''
          )
          if (name) {
            layer.bindTooltip(name, {
              permanent: true,
              direction: 'center',
              className: 'region-label',
            })
          }
        }
      }
      if (i < layers.length) {
        rafRef.current = requestAnimationFrame(createBatch)
      }
    }
    rafRef.current = requestAnimationFrame(createBatch)

    return () => {
      cancelAnimationFrame(rafRef.current)
      for (const layer of layers) {
        try { layer.unbindTooltip() } catch { /* ignore */ }
      }
    }
  }, [showLabels])

  if (!data || !onRegionSelect) return null

  const hasColorMap = colorMap !== null && colorMap !== undefined && colorMap.size > 0

  const featureStyle = (feature?: { properties?: Record<string, unknown> }) => {
    const featureId = String(
      feature?.properties?.id ??
      feature?.properties?.gb ??
      feature?.properties?.name ??
      '',
    )
    const selected = featureId && featureId === selectedRegionId
    const fillFromMap = colorMap?.get(featureId)
    return {
      color: selected ? '#b45309' : (hasColorMap ? '#334155' : '#1d4ed8'),
      opacity: selected ? 0.75 : (hasColorMap ? 0.7 : 0.42),
      weight: selected ? 2.6 : (hasColorMap ? 1.0 : 1.2),
      fillColor: selected ? '#f59e0b' : (fillFromMap ?? '#60a5fa'),
      fillOpacity: selected ? 0.4 : (hasColorMap ? 0.65 : 0.035),
    }
  }

  return (
    <GeoJSON
      key={data.features.length}
      data={data as never}
      style={featureStyle}
      onEachFeature={(feature, layer) => {
        // Collect layer reference for later tooltip binding
        geoLayersRef.current.push(layer)
        layer.on('mouseover', () => {
          const pathLayer = layer as L.Path
          pathLayer.setStyle({
            color: '#0f766e',
            opacity: 0.85,
            weight: 2.4,
            fillColor: '#14b8a6',
            fillOpacity: 0.16,
          })
          pathLayer.bringToFront()
        })
        layer.on('mouseout', () => {
          ;(layer as L.Path).setStyle(featureStyle(feature))
        })
        layer.on('click', (event) => {
          if (event.originalEvent) {
            L.DomEvent.stopPropagation(event.originalEvent)
          }
          const id = String(
            feature.properties?.id ?? feature.properties?.gb ?? feature.properties?.name ?? '',
          )
          const name = String(feature.properties?.name ?? feature.properties?.NAME ?? id)
          if (id) onRegionSelect({ id, name })
        })
      }}
    />
  )
}

// ===== Bounds for China =====

const CHINA_BOUNDS: L.LatLngBoundsLiteral = [
  [18, 73],
  [54, 135],
]

const DEFAULT_CENTER: L.LatLngTuple = [36, 104]

// ===== Main MapView =====

interface MapViewProps {
  layers: Layer[]
  activeLayerId: string | null
  opacity: number
  currentTime: string
  regionVector?: IrrigationVectorGeoJSON | null
  selectedRegionId?: string | null
  onRegionSelect?: (region: { id: string; name: string }) => void
  disableQuery?: boolean
  hideRaster?: boolean
  regionColorMap?: Map<string, string> | null
  regionLevel?: string | null
}

export default function MapView({
  layers,
  activeLayerId,
  opacity,
  currentTime,
  regionVector = null,
  selectedRegionId = null,
  onRegionSelect,
  disableQuery = false,
  hideRaster = false,
  regionColorMap = null,
  regionLevel = null,
}: MapViewProps) {
  const [marker, setMarker] = useState<L.LatLng | null>(null)
  const [rect, setRect] = useState<L.LatLngBoundsExpression | null>(null)
  const { state, queryPointAt, queryAreaBounds, reset } = useMapQuery(
    activeLayerId,
    currentTime,
  )
  const activeLayer = useMemo(
    () => layers.find((l) => l.id === activeLayerId) ?? null,
    [layers, activeLayerId],
  )

  useEffect(() => {
    setMarker(null)
    setRect(null)
  }, [activeLayerId, currentTime])

  const handlePointCoords = useCallback((lat: number, lng: number) => {
    setMarker(L.latLng(lat, lng))
    setRect(null)
    void queryPointAt(lat, lng)
  }, [queryPointAt])

  const handleAreaCoords = useCallback((coords: [[number, number], [number, number]]) => {
    const [p1, p2] = coords
    setRect([
      [p1[0], p1[1]],
      [p2[0], p2[1]],
    ])
    setMarker(null)
    void queryAreaBounds(coords)
  }, [queryAreaBounds])

  const handleCloseQuery = useCallback(() => {
    reset()
    setMarker(null)
    setRect(null)
  }, [reset])

  return (
    <div className="map-container">
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={5}
        minZoom={4}
        maxZoom={13}
        maxBounds={CHINA_BOUNDS}
        maxBoundsViscosity={0.8}
        style={{ height: '100%', width: '100%' }}
        attributionControl={true}
      >
        {/* ArcGIS World Street Map base layer (WGS84, matches SSM data CRS) */}
        <TileLayer
          attribution='&copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ'
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
        />

        {/* Remote sensing overlay */}
        {!hideRaster && (
          <TileOverlay layer={activeLayer} time={currentTime} opacity={opacity} />
        )}

        <RegionOverlay
          data={regionVector}
          selectedRegionId={selectedRegionId}
          onRegionSelect={onRegionSelect}
          colorMap={regionColorMap}
          regionLevel={regionLevel}
        />

        {/* Point click + rectangle drawing */}
        <MapEvents
          enabled={Boolean(activeLayerId && currentTime && !disableQuery)}
          onPointCoords={handlePointCoords}
          onAreaCoords={handleAreaCoords}
        />

        {/* Drawn rectangle */}
        {rect && (
          <Rectangle
            bounds={rect}
            pathOptions={{ color: '#3388ff', weight: 2, dashArray: '6 4', fill: false }}
          />
        )}

        {/* Point marker */}
        {marker && <Marker position={marker} />}
      </MapContainer>
      <QueryCard state={state} activeLayer={activeLayer} onClose={handleCloseQuery} />
    </div>
  )
}
