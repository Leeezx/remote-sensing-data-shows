import { useEffect, useMemo } from 'react'
import {
  GeoJSON,
  MapContainer,
  Pane,
  TileLayer,
  useMap,
} from 'react-leaflet'
import ReclamationCanvasLayer from './ReclamationCanvasLayer'
import {
  CURRENT_SCENARIO_COLOR,
  FUTURE_SCENARIO_COLOR,
} from './reclamationCanvas'
import type {
  ReclamationFeatureCollection,
  ReclamationOverviewWireResponse,
  ReclamationPoint,
  ReclamationRegionProperties,
  ReclamationScenario,
} from '../types'

const CHINA_BOUNDS: [[number, number], [number, number]] = [
  [18, 73],
  [54, 135],
]

interface ReclamationMapProps {
  overview: ReclamationOverviewWireResponse
  overallRegion: ReclamationRegionProperties
  selectedRegion: ReclamationRegionProperties | null
  points: ReclamationPoint[]
  scenario: ReclamationScenario
  onRegionSelect: (region: ReclamationRegionProperties) => void
  onPointSelect: (point: ReclamationPoint) => void
}

function ReclamationViewController({
  selectedRegion,
}: {
  selectedRegion: ReclamationRegionProperties | null
}) {
  const map = useMap()

  useEffect(() => {
    map.fitBounds(selectedRegion?.bounds ?? [[15, 73], [54, 135]], {
      padding: selectedRegion ? [32, 32] : [20, 20],
      animate: true,
    })
  }, [map, selectedRegion])

  return null
}

export default function ReclamationMap({
  overview,
  overallRegion,
  selectedRegion,
  points,
  scenario,
  onRegionSelect,
  onPointSelect,
}: ReclamationMapProps) {
  const selectedRegions = useMemo<ReclamationFeatureCollection<ReclamationRegionProperties>>(() => ({
    type: 'FeatureCollection',
    features: overview.regions.features,
  }), [overview.regions.features])
  const isOverview = selectedRegion === null
  const pointColor = scenario === 'current'
    ? CURRENT_SCENARIO_COLOR
    : FUTURE_SCENARIO_COLOR

  const regionStyle = () => (
    isOverview
      ? {
          color: '#FFF7ED',
          weight: 1.5,
          fillColor: '#F97316',
          fillOpacity: 0.62,
          className: 'reclamation-region-pulse',
        }
      : {
          color: '#F97316',
          weight: 3,
          fillOpacity: 0,
        }
  )

  return (
    <div className="map-container">
      <MapContainer
        center={[35.5, 104]}
        zoom={4}
        minZoom={3}
        maxZoom={13}
        maxBounds={CHINA_BOUNDS}
        maxBoundsViscosity={0.8}
        style={{ height: '100%', width: '100%' }}
        attributionControl={true}
      >
        <TileLayer
          attribution="&copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ"
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
          maxZoom={13}
          maxNativeZoom={8}
        />

        <ReclamationViewController selectedRegion={selectedRegion} />

        <Pane name="reclamation-china-outline" style={{ zIndex: 400 }}>
          <GeoJSON
            data={overview.chinaOutline as never}
            style={{ color: '#475569', weight: 1.5, fill: false }}
          />
        </Pane>

        <Pane name="reclamation-regions" style={{ zIndex: 410 }}>
          <GeoJSON
            key={isOverview ? 'overview-regions' : `selected-region-${selectedRegion.id}`}
            data={selectedRegions as never}
            style={regionStyle}
            onEachFeature={isOverview ? (_feature, layer) => {
              layer.on({
                click: () => onRegionSelect(overallRegion),
              })
            } : undefined}
          />
        </Pane>

        {selectedRegion && points.length > 0 && (
          <ReclamationCanvasLayer
            points={points}
            scenario={scenario}
            color={pointColor}
            onPointSelect={onPointSelect}
          />
        )}
      </MapContainer>
    </div>
  )
}
