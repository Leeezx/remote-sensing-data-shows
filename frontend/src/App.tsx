import { useCallback, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { getLayers, getLayerTimes, getRegions } from './services/api'
import type { Layer, PointQueryResult, Region } from './types'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import MapView from './components/MapView'
import Legend from './components/Legend'
import QueryPanel from './components/QueryPanel'
import ChartPanel from './components/ChartPanel'
import ExportPanel from './components/ExportPanel'
import './App.css'

function MainPage() {
  // Loading / error state
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  // Data from backend
  const [layers, setLayers] = useState<Layer[]>([])
  const [regions, setRegions] = useState<Region[]>([])

  // Layer selection
  const [activeLayerId, setActiveLayerId] = useState<string | null>(null)
  const [opacity, setOpacity] = useState(0.7)

  // Time control
  const [currentTime, setCurrentTime] = useState('')
  const [times, setTimes] = useState<string[]>([])
  const [isPlaying, setIsPlaying] = useState(false)
  const playIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Region
  const [regionId, setRegionId] = useState<string | null>(null)

  // Query results
  const [pointResult, setPointResult] = useState<PointQueryResult | null>(null)
  const [areaCoords, setAreaCoords] = useState<[number, number][] | null>(null)

  // Load layers and regions on mount
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setLoadError('')

    Promise.all([getLayers(), getRegions()])
      .then(([layerData, regionData]) => {
        if (cancelled) return
        setLayers(layerData)
        setRegions(regionData)
        if (layerData.length > 0) {
          setActiveLayerId(layerData[0].id)
        }
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const msg = err instanceof Error ? err.message : '数据加载失败'
        setLoadError(msg)
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  // Load times from backend when layer changes
  useEffect(() => {
    if (!activeLayerId) return
    let cancelled = false

    getLayerTimes(activeLayerId)
      .then((data) => {
        if (cancelled) return
        setTimes(data)
        if (data.length > 0) {
          setCurrentTime((prev) => (data.includes(prev) ? prev : data[0]))
        }
      })
      .catch(() => {
        if (!cancelled) setTimes([])
      })

    return () => {
      cancelled = true
    }
  }, [activeLayerId])

  // Play/pause animation
  useEffect(() => {
    if (isPlaying && times.length > 0) {
      playIntervalRef.current = setInterval(() => {
        setCurrentTime((prev) => {
          const idx = times.indexOf(prev)
          return times[(idx + 1) % times.length]
        })
      }, 800)
    }
    return () => {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current)
        playIntervalRef.current = null
      }
    }
  }, [isPlaying, times])

  const handleLayerChange = useCallback((id: string) => {
    setActiveLayerId(id)
    setPointResult(null)
    setAreaCoords(null)
  }, [])

  const handleTimeChange = useCallback((t: string) => {
    setCurrentTime(t)
    setPointResult(null)
    setAreaCoords(null)
  }, [])

  const handlePlayToggle = useCallback(() => {
    setIsPlaying((p) => !p)
  }, [])

  const handlePointResult = useCallback((r: PointQueryResult) => {
    setPointResult(r)
  }, [])

  const handleAreaCoords = useCallback((coords: [number, number][]) => {
    setAreaCoords(coords)
  }, [])

  return (
    <div className="app">
      <Header />
      <main className="app-main">
        <div className="sidebar-area">
          <Sidebar
            layers={layers}
            regions={regions}
            activeLayerId={activeLayerId}
            onLayerChange={handleLayerChange}
            opacity={opacity}
            onOpacityChange={setOpacity}
            currentTime={currentTime}
            times={times}
            onTimeChange={handleTimeChange}
            isPlaying={isPlaying}
            onPlayToggle={handlePlayToggle}
            regionId={regionId}
            onRegionChange={setRegionId}
          />
          <ExportPanel
            activeLayerId={activeLayerId}
            regionId={regionId}
            startTime={times.length > 0 ? times[0] : '2025-01'}
            endTime={times.length > 0 ? times[times.length - 1] : '2025-12'}
            hasData={activeLayerId !== null && times.length > 0}
          />
        </div>

        <div className="map-area">
          {loading ? (
            <div className="loading">加载地图数据...</div>
          ) : loadError ? (
            <div className="loading error">{loadError}</div>
          ) : (
            <MapView
              layers={layers}
              activeLayerId={activeLayerId}
              opacity={opacity}
              currentTime={currentTime}
              onPointResult={handlePointResult}
              onAreaCoords={handleAreaCoords}
            />
          )}
          <Legend layer={layers.find((l) => l.id === activeLayerId) ?? null} />
        </div>

        <div className="right-panel">
          <QueryPanel
            pointResult={pointResult}
            areaCoords={areaCoords}
            activeLayerId={activeLayerId}
            currentTime={currentTime}
            layers={layers}
          />
          <ChartPanel
            activeLayerId={activeLayerId}
            layers={layers}
            regionId={regionId}
            regions={regions}
            startTime={times.length > 0 ? times[0] : '2025-01'}
            endTime={times.length > 0 ? times[times.length - 1] : '2025-12'}
          />
        </div>
      </main>
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/*" element={<MainPage />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
