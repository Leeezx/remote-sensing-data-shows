import { useCallback, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { getLayerLegend, getLayers, getLayerTimes } from './services/api'
import type { Layer, LegendItem, LegendStatus } from './types'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import MapView from './components/MapView'
import Legend from './components/Legend'
import VideoModal from './components/VideoModal'
import IrrigationPage from './pages/IrrigationPage'
import ReclamationPage from './pages/ReclamationPage'
import WaterDemandPage from './pages/WaterDemandPage'
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
  const [isPlaybackMode, setIsPlaybackMode] = useState(false)
  const [playbackImageReady, setPlaybackImageReady] = useState(false)
  const playbackStartTimeRef = useRef('')
  const isPlayingRef = useRef(false)
  const playbackStepTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const activeLayer = layers.find((layer) => layer.id === activeLayerId) ?? null
  const dynamicLayerId = activeLayer?.id === 'ssm' || activeLayer?.id === 'et'
    ? activeLayer.id
    : null
  const hasDynamicLegend = dynamicLayerId !== null
  const legendKey = dynamicLayerId && currentTime
    ? `${dynamicLayerId}:${currentTime}`
    : null
  const [dynamicLegend, setDynamicLegend] = useState<DynamicLegendState>({
    key: null,
    status: 'loading',
    items: [],
  })
  const playbackImage = isPlaybackMode && activeLayerId && currentTime
    ? `/data/playback-images/${encodeURIComponent(activeLayerId)}/${encodeURIComponent(currentTime)}.png`
    : null
  isPlayingRef.current = isPlaying

  // Tile loading overlay
  const [tileLoading, setTileLoading] = useState(false)
  const tileLoadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Video modal
  const [videoOpen, setVideoOpen] = useState(false)

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

  // SSM and ET thresholds depend on the selected acquisition time.
  useEffect(() => {
    if (isPlaybackMode) return
    if (!dynamicLayerId) {
      setDynamicLegend({ key: null, status: 'ready', items: [] })
      return
    }

    if (!currentTime || !legendKey) {
      setDynamicLegend({ key: null, status: 'loading', items: [] })
      return
    }

    let cancelled = false
    setDynamicLegend({ key: legendKey, status: 'loading', items: [] })

    getLayerLegend(dynamicLayerId, currentTime)
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
  }, [dynamicLayerId, currentTime, legendKey, isPlaybackMode])

  const clearPlaybackStep = useCallback(() => {
    if (playbackStepTimeoutRef.current) {
      clearTimeout(playbackStepTimeoutRef.current)
      playbackStepTimeoutRef.current = null
    }
  }, [])

  const schedulePlaybackStep = useCallback(() => {
    clearPlaybackStep()
    if (!isPlayingRef.current || times.length === 0) return
    playbackStepTimeoutRef.current = setTimeout(() => {
      setPlaybackImageReady(false)
      setCurrentTime((prev) => {
        const idx = times.indexOf(prev)
        return times[(idx + 1 + times.length) % times.length]
      })
    }, 800)
  }, [clearPlaybackStep, times])

  useEffect(() => () => clearPlaybackStep(), [clearPlaybackStep])

  // Advance only after the current JPEG frame has loaded.
  useEffect(() => {
    if (!isPlaying) clearPlaybackStep()
  }, [isPlaying, clearPlaybackStep])

  const stopPlayback = useCallback((restoreTime: boolean) => {
    clearPlaybackStep()
    setIsPlaying(false)
    setIsPlaybackMode(false)
    setPlaybackImageReady(false)
    if (restoreTime) setCurrentTime(playbackStartTimeRef.current)
  }, [clearPlaybackStep])

  const handleLayerChange = useCallback((id: string) => {
    stopPlayback(false)
    setActiveLayerId(id)
    setTileLoading(true)
    if (tileLoadTimerRef.current) clearTimeout(tileLoadTimerRef.current)
    tileLoadTimerRef.current = setTimeout(() => setTileLoading(false), 2000)
  }, [stopPlayback])

  const handleTimeChange = useCallback((t: string) => {
    if (isPlaybackMode) stopPlayback(false)
    setCurrentTime(t)
  }, [isPlaybackMode, stopPlayback])

  const handleTimeResolutionChange = useCallback((resolution: 'month' | '8day') => {
    if (resolution === timeResolution) return
    stopPlayback(false)
    setCurrentTime('')
    setTimes([])
    setTimeResolution(resolution)
  }, [stopPlayback, timeResolution])

  const handlePlayToggle = useCallback(() => {
    if (isPlaying) {
      clearPlaybackStep()
      setIsPlaying(false)
      return
    }
    if (!isPlaybackMode) {
      playbackStartTimeRef.current = currentTime
      setIsPlaybackMode(true)
      setPlaybackImageReady(false)
    } else if (playbackImageReady) {
      schedulePlaybackStep()
    }
    setIsPlaying(true)
  }, [clearPlaybackStep, currentTime, isPlaybackMode, isPlaying, playbackImageReady, schedulePlaybackStep])

  const handlePlaybackImageLoad = useCallback(() => {
    setPlaybackImageReady(true)
    if (isPlayingRef.current) schedulePlaybackStep()
  }, [schedulePlaybackStep])

  const handlePlaybackImageError = useCallback(() => {
    if (isPlayingRef.current) schedulePlaybackStep()
  }, [schedulePlaybackStep])

  const legendItems = isPlaybackMode
    ? activeLayer?.legend ?? []
    : hasDynamicLegend
    ? dynamicLegend.key === legendKey ? dynamicLegend.items : []
    : activeLayer?.legend ?? []
  const legendStatus: LegendStatus = isPlaybackMode
    ? 'ready'
    : hasDynamicLegend
    ? dynamicLegend.key === legendKey ? dynamicLegend.status : 'loading'
    : 'ready'

  return (
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
            isPlaybackMode={isPlaybackMode}
            onPlayToggle={handlePlayToggle}
            onPlayEnd={() => stopPlayback(true)}
            onOpenVideo={() => setVideoOpen(true)}
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
                playbackImage={playbackImage}
                onPlaybackImageLoad={handlePlaybackImageLoad}
                onPlaybackImageError={handlePlaybackImageError}
              />
            </div>
          )}
          <Legend
            layer={activeLayer}
            items={legendItems}
            status={legendStatus}
          />
        </div>

        {videoOpen && <VideoModal onClose={() => setVideoOpen(false)} />}
      </main>
  )
}

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Header />
        <Routes>
          <Route path="/" element={<MainPage />} />
          <Route path="/base" element={<MainPage />} />
          <Route path="/irrigation" element={<IrrigationPage />} />
          <Route path="/reclamation" element={<ReclamationPage />} />
          <Route path="/water-demand" element={<WaterDemandPage />} />
          <Route path="*" element={<MainPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}

export default App
