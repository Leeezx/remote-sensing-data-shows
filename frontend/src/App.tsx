import { useCallback, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { getLayerLegend, getLayers, getLayerTimes } from './services/api'
import type { Layer, LegendItem, LegendStatus } from './types'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import MapView from './components/MapView'
import Legend from './components/Legend'
import ExportPanel from './components/ExportPanel'
import './App.css'

interface DynamicLegendState {
  key: string | null
  status: LegendStatus
  items: LegendItem[]
}

function MainPage() {
  // Loading / error state
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  // Data from backend
  const [layers, setLayers] = useState<Layer[]>([])

  // Layer selection
  const [activeLayerId, setActiveLayerId] = useState<string | null>(null)
  const [opacity, setOpacity] = useState(0.7)

  // Time control
  const [currentTime, setCurrentTime] = useState('')
  const [times, setTimes] = useState<string[]>([])
  const [timeResolution, setTimeResolution] = useState<'month' | '8day'>('8day')
  const [isPlaying, setIsPlaying] = useState(false)
  const playIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const activeLayer = layers.find((layer) => layer.id === activeLayerId) ?? null
  const legendKey = activeLayer?.id === 'ssm' && currentTime
    ? `${activeLayer.id}:${currentTime}`
    : null
  const [dynamicLegend, setDynamicLegend] = useState<DynamicLegendState>({
    key: null,
    status: 'loading',
    items: [],
  })

  // Tile loading overlay
  const [tileLoading, setTileLoading] = useState(false)
  const tileLoadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Load layers on mount
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setLoadError('')

    getLayers()
      .then((layerData) => {
        if (cancelled) return
        setLayers(layerData)
        if (layerData.length > 0) {
          // Prefer SSM as default (has COG data); fallback to first layer
          setActiveLayerId(layerData.find((l) => l.id === 'ssm')?.id ?? layerData[0].id)
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

  // Load times from backend when layer changes or resolution changes
  useEffect(() => {
    if (!activeLayerId) return
    let cancelled = false

    // Immediately clear time to prevent stale tile requests
    setCurrentTime('')
    setTimes([])

    getLayerTimes(activeLayerId, timeResolution)
      .then((data) => {
        if (cancelled) return
        setTimes(data)
        if (data.length > 0) {
          setCurrentTime(data[0])
        }
      })
      .catch(() => {
        if (!cancelled) setTimes([])
      })

    return () => {
      cancelled = true
    }
  }, [activeLayerId, timeResolution])

  // SSM thresholds depend on the selected acquisition time.
  useEffect(() => {
    if (activeLayerId !== 'ssm') {
      setDynamicLegend({ key: null, status: 'ready', items: [] })
      return
    }

    if (!currentTime || !legendKey) {
      setDynamicLegend({ key: null, status: 'loading', items: [] })
      return
    }

    let cancelled = false
    setDynamicLegend({ key: legendKey, status: 'loading', items: [] })

    getLayerLegend(activeLayerId, currentTime)
      .then((data) => {
        if (!cancelled) {
          setDynamicLegend({ key: legendKey, status: 'ready', items: data.legend })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDynamicLegend({ key: legendKey, status: 'error', items: [] })
        }
      })

    return () => {
      cancelled = true
    }
  }, [activeLayerId, currentTime, legendKey])

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
    setTileLoading(true)
    if (tileLoadTimerRef.current) clearTimeout(tileLoadTimerRef.current)
    tileLoadTimerRef.current = setTimeout(() => setTileLoading(false), 2000)
  }, [])

  const handleTimeChange = useCallback((t: string) => {
    setCurrentTime(t)
  }, [])

  const handleTimeResolutionChange = useCallback((resolution: 'month' | '8day') => {
    if (resolution === timeResolution) return
    setCurrentTime('')
    setTimes([])
    setTimeResolution(resolution)
  }, [timeResolution])

  const handlePlayToggle = useCallback(() => {
    setIsPlaying((p) => !p)
  }, [])

  const legendItems = activeLayer?.id === 'ssm'
    ? dynamicLegend.key === legendKey ? dynamicLegend.items : []
    : activeLayer?.legend ?? []
  const legendStatus: LegendStatus = activeLayer?.id === 'ssm'
    ? dynamicLegend.key === legendKey ? dynamicLegend.status : 'loading'
    : 'ready'

  return (
    <div className="app">
      <Header />
      <main className="app-main">
        <div className="sidebar-area">
          <Sidebar
            layers={layers}
            activeLayerId={activeLayerId}
            onLayerChange={handleLayerChange}
            opacity={opacity}
            onOpacityChange={setOpacity}
            currentTime={currentTime}
            times={times}
            onTimeChange={handleTimeChange}
            timeResolution={timeResolution}
            onTimeResolutionChange={handleTimeResolutionChange}
            isPlaying={isPlaying}
            onPlayToggle={handlePlayToggle}
          />
          <ExportPanel
            activeLayerId={activeLayerId}
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
            <div className="map-area-wrapper">
              {tileLoading && (
                <div className="tile-loading-overlay">
                  <div className="tile-loading-spinner" />
                  <span>加载瓦片中...</span>
                </div>
              )}
              <MapView
                layers={layers}
                activeLayerId={activeLayerId}
                opacity={opacity}
                currentTime={currentTime}
              />
            </div>
          )}
          <Legend
            layer={activeLayer}
            items={legendItems}
            status={legendStatus}
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
