import { useCallback, useEffect, useRef, useState } from 'react'
import {
  MapContainer,
  TileLayer,
  useMap,
  useMapEvents,
  Rectangle,
  Marker,
  Popup,
} from 'react-leaflet'
import L from 'leaflet'
import type { Layer, PointQueryResult } from '../types'
import { queryPoint } from '../services/api'

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
      // SSM: proxy endpoint resolves time→COG filename, then TiTiler renders
      url = `/data/ssm-tiles/WebMercatorQuad/{z}/{x}/{y}.png?` + new URLSearchParams({
        time: time,
        colormap_name: 'rdylgn',
        rescale: `${layer.range.min},${layer.range.max}`,
      }).toString()
    } else {
      url = layer.tileTemplate
        .replace('{time}', time)
        .replace('{z}', '{z}')
        .replace('{x}', '{x}')
        .replace('{y}', '{y}')
    }

    // _r suffix to avoid cache on missing tiles
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
  activeLayerId,
  currentTime,
  onPointResult,
  onAreaCoords,
}: {
  activeLayerId: string | null
  currentTime: string
  onPointResult: (r: PointQueryResult) => void
  onAreaCoords: (coords: [number, number][]) => void
}) {
  const drawingRef = useRef(false)
  const rectRef = useRef<[number, number][]>([])

  useMapEvents({
    click: async (e) => {
      if (!activeLayerId) return
      const { lat, lng } = e.latlng
      try {
        const result = await queryPoint(
          activeLayerId,
          currentTime,
          Number(lng.toFixed(4)),
          Number(lat.toFixed(4)),
        )
        onPointResult(result)
      } catch {
        // Point outside any region — silently ignore
      }
    },

    mousedown: (e) => {
      if (!e.originalEvent.shiftKey || !activeLayerId) return
      drawingRef.current = true
      rectRef.current = [[e.latlng.lat, e.latlng.lng]]
    },

    mousemove: (e) => {
      if (!drawingRef.current) return
      rectRef.current = [rectRef.current[0], [e.latlng.lat, e.latlng.lng]]
    },

    mouseup: () => {
      if (!drawingRef.current) return
      drawingRef.current = false
      if (rectRef.current.length === 2) {
        onAreaCoords(rectRef.current)
      }
    },
  })

  return null
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
  onPointResult: (r: PointQueryResult) => void
  onAreaCoords: (coords: [number, number][]) => void
}

export default function MapView({
  layers,
  activeLayerId,
  opacity,
  currentTime,
  onPointResult,
  onAreaCoords,
}: MapViewProps) {
  const [rect, setRect] = useState<L.LatLngBoundsExpression | null>(null)
  const activeLayer = layers.find((l) => l.id === activeLayerId) ?? null

  const handleAreaCoords = useCallback((coords: [number, number][]) => {
    const [p1, p2] = coords
    setRect([
      [p1[0], p1[1]],
      [p2[0], p2[1]],
    ])
    onAreaCoords(coords)
  }, [onAreaCoords])

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
        {/* Base layer — plain background via CSS, no external tiles */}

        {/* Remote sensing overlay */}
        <TileOverlay layer={activeLayer} time={currentTime} opacity={opacity} />

        {/* Point click + rectangle drawing */}
        <MapEvents
          activeLayerId={activeLayerId}
          currentTime={currentTime}
          onPointResult={onPointResult}
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
        <PointMarker />
      </MapContainer>
    </div>
  )
}

// ===== Point marker sub-component =====

function PointMarker() {
  const [marker, setMarker] = useState<L.LatLng | null>(null)

  useMapEvents({
    click: (e) => {
      setMarker(e.latlng)
    },
  })

  return marker ? (
    <Marker position={marker}>
      <Popup>
        {marker.lat.toFixed(4)}, {marker.lng.toFixed(4)}
      </Popup>
    </Marker>
  ) : null
}
