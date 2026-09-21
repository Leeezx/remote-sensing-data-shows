import { useEffect } from 'react'
import { GeoJSON, MapContainer, Pane, TileLayer, useMap } from 'react-leaflet'
import WaterDemandCanvasLayer from './WaterDemandCanvasLayer'
import type {
  WaterDemandClass,
  WaterDemandOverviewResponse,
  WaterDemandPointGrid,
  WaterDemandRegionProperties,
} from '../types'

const CHINA_BOUNDS: [[number, number], [number, number]] = [
  [18, 73],
  [54, 135],
]

interface WaterDemandMapProps {
  overview: WaterDemandOverviewResponse
  region: WaterDemandRegionProperties
  highlighted: boolean
  grid: WaterDemandPointGrid | null
  classColors: Record<WaterDemandClass, string>
  selectedIndex: number | null
  onPointSelect: (index: number) => void
}

function WaterDemandViewController({
  region,
  highlighted,
}: {
  region: WaterDemandRegionProperties
  highlighted: boolean
}) {
  const map = useMap()

  useEffect(() => {
    map.fitBounds(highlighted ? [[15, 73], [54, 135]] : region.bounds, {
      padding: highlighted ? [20, 20] : [32, 32],
      animate: true,
    })
  }, [map, region, highlighted])

  return null
}

export default function WaterDemandMap({
  overview,
  region,
  highlighted,
  grid,
  classColors,
  selectedIndex,
  onPointSelect,
}: WaterDemandMapProps) {
  const regionStyle = () => (
    highlighted
      ? {
          color: '#FFF7ED',
          weight: 1.5,
          fillColor: '#DC2626',
          fillOpacity: 0.62,
          className: 'reclamation-region-pulse',
        }
      : {
          color: '#DC2626',
          weight: 2.5,
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

        <WaterDemandViewController region={region} highlighted={highlighted} />

        <Pane name="water-demand-china-outline" style={{ zIndex: 400 }}>
          <GeoJSON
            data={overview.chinaOutline as never}
            style={{ color: '#475569', weight: 1.5, fill: false }}
          />
        </Pane>

        <Pane name="water-demand-regions" style={{ zIndex: 410 }}>
          <GeoJSON
            key={highlighted ? 'water-demand-overview' : 'water-demand-region'}
            data={overview.regions as never}
            style={regionStyle}
          />
        </Pane>

        {!highlighted && grid && (
          <WaterDemandCanvasLayer
            grid={grid}
            colors={classColors}
            selectedIndex={selectedIndex}
            onPointSelect={onPointSelect}
          />
        )}
      </MapContainer>
    </div>
  )
}
