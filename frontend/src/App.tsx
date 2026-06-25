import { useCallback, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { getLayers } from './services/api'
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
  // Data from backend
  const [layers, setLayers] = useState<Layer[]>([])
  const [regions, setRegions] = useState<Region[]>([])
  const [layersLoaded, setLayersLoaded] = useState(false)

  // Layer selection
  const [activeLayerId, setActiveLayerId] = useState<string | null>(null)
  const [opacity, setOpacity] = useState(0.7)

  // Time control
  const [currentTime, setCurrentTime] = useState('2025-06')
  const [times, setTimes] = useState<string[]>([])
  const [isPlaying, setIsPlaying] = useState(false)
  const playIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Region
  const [regionId, setRegionId] = useState<string | null>(null)

  // Query results
  const [pointResult, setPointResult] = useState<PointQueryResult | null>(null)
  const [areaCoords, setAreaCoords] = useState<[number, number][] | null>(null)

  // Load layers on mount
  useEffect(() => {
    getLayers()
      .then((data) => {
        setLayers(data)
        if (data.length > 0 && !activeLayerId) {
          setActiveLayerId(data[0].id)
        }
        setLayersLoaded(true)
      })
      .catch(console.error)
    // Regions come from a static fetch — use layers data or a separate endpoint
    fetch('/api/regions')
      .then((r) => r.json())
      .then(setRegions)
      .catch(() => {
        // Fallback: regions may not have an endpoint; use embedded list
        setRegions([])
      })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Load times when layer changes
  useEffect(() => {
    if (!activeLayerId) return
    const layer = layers.find((l) => l.id === activeLayerId)
    if (!layer) return
    const start = layer.timeRange.start
    const end = layer.timeRange.end
    // Generate time array from range (monthly steps)
    const generated: string[] = []
    const [startY, startM] = start.split('-').map(Number)
    const [endY, endM] = end.split('-').map(Number)
    let y = startY,
      m = startM
    while (y < endY || (y === endY && m <= endM)) {
      generated.push(`${y}-${String(m).padStart(2, '0')}`)
      m++
      if (m > 12) {
        m = 1
        y++
      }
    }
    setTimes(generated)
    if (generated.length > 0 && !generated.includes(currentTime)) {
      setCurrentTime(generated[0])
    }
  }, [activeLayerId, layers]) // eslint-disable-line react-hooks/exhaustive-deps

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

        <div className="map-area">
          {layersLoaded ? (
            <MapView
              layers={layers}
              activeLayerId={activeLayerId}
              opacity={opacity}
              currentTime={currentTime}
              onPointResult={handlePointResult}
              onAreaCoords={handleAreaCoords}
            />
          ) : (
            <div className="loading">加载地图数据...</div>
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
          <ExportPanel
            activeLayerId={activeLayerId}
            regionId={regionId}
            startTime={times.length > 0 ? times[0] : '2025-01'}
            endTime={times.length > 0 ? times[times.length - 1] : '2025-12'}
            hasData={true}
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
