import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import axios from 'axios'
import ScenarioSwitch from '../components/ScenarioSwitch'
import WaterDemandInfoCard from '../components/WaterDemandInfoCard'
import WaterDemandLegend from '../components/WaterDemandLegend'
import WaterDemandMap from '../components/WaterDemandMap'
import { getWaterDemandOverview, getWaterDemandPoints } from '../services/api'
import type {
  WaterDemandClass,
  WaterDemandLegendEntry,
  WaterDemandOverviewResponse,
  WaterDemandPointGrid,
  WaterDemandRegionProperties,
  WaterDemandScenario,
} from '../types'

/** Heading shown before the map auto-drills into the demo region. */
export const AUTO_DRILL_DELAY_MS = 1000

const FALLBACK_WATER_DEMAND_LEGEND: WaterDemandLegendEntry[] = [
  { value: 1, color: '#F08A85', label: '立即补水' },
  { value: 2, color: '#F2C744', label: '优先补水' },
  { value: 3, color: '#7BC47F', label: '观察复核' },
]

type PointsState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; grid: WaterDemandPointGrid }

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback
}

function isAbort(error: unknown) {
  return axios.isCancel(error) || (error instanceof Error && error.name === 'AbortError')
}

function legendColors(legend: WaterDemandLegendEntry[]): Record<WaterDemandClass, string> {
  const entries = legend.length > 0 ? legend : FALLBACK_WATER_DEMAND_LEGEND
  const colors: Record<WaterDemandClass, string> = { 1: '#F08A85', 2: '#F2C744', 3: '#7BC47F' }
  for (const entry of entries) colors[entry.value] = entry.color
  return colors
}

interface WaterDemandPageProps {
  /** Milliseconds before the demo region is entered automatically. */
  autoDrillDelayMs?: number
}

export default function WaterDemandPage({
  autoDrillDelayMs = AUTO_DRILL_DELAY_MS,
}: WaterDemandPageProps = {}) {
  const [overview, setOverview] = useState<WaterDemandOverviewResponse | null>(null)
  const [overviewStatus, setOverviewStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [overviewError, setOverviewError] = useState('')
  const [overviewAttempt, setOverviewAttempt] = useState(0)
  const [drilled, setDrilled] = useState(false)
  const [pointsState, setPointsState] = useState<PointsState>({ status: 'idle' })
  const [scenario, setScenario] = useState<WaterDemandScenario>('current')
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const requestRef = useRef<AbortController | null>(null)
  const suppressAutoDrillRef = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    setOverviewStatus('loading')
    setOverviewError('')
    getWaterDemandOverview(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        setOverview(data)
        setOverviewStatus('ready')
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || isAbort(error)) return
        setOverviewError(errorMessage(error, '需水补水概览加载失败'))
        setOverviewStatus('error')
      })
    return () => controller.abort()
  }, [overviewAttempt])

  useEffect(() => () => {
    requestRef.current?.abort()
    requestRef.current = null
  }, [])

  const loadPoints = useCallback(() => {
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller
    setPointsState({ status: 'loading' })

    getWaterDemandPoints(controller.signal)
      .then((grid) => {
        if (controller.signal.aborted) return
        requestRef.current = null
        setPointsState({ status: 'ready', grid })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || isAbort(error)) return
        requestRef.current = null
        setPointsState({ status: 'error', message: errorMessage(error, '需水补水点位加载失败') })
      })
  }, [])

  // Entering the section highlights the demo region, then drills in automatically.
  useEffect(() => {
    if (overviewStatus !== 'ready' || drilled || suppressAutoDrillRef.current) return undefined
    const timer = setTimeout(() => setDrilled(true), autoDrillDelayMs)
    return () => clearTimeout(timer)
  }, [overviewStatus, drilled, autoDrillDelayMs])

  useEffect(() => {
    if (drilled && pointsState.status === 'idle') loadPoints()
  }, [drilled, pointsState.status, loadPoints])

  const returnToOverview = useCallback(() => {
    // Returning to the national view is a deliberate choice: stay there.
    suppressAutoDrillRef.current = true
    requestRef.current?.abort()
    requestRef.current = null
    setDrilled(false)
    setPointsState({ status: 'idle' })
    setSelectedIndex(null)
    setScenario('current')
  }, [])

  const enterRegion = useCallback(() => setDrilled(true), [])

  const changeScenario = useCallback((next: WaterDemandScenario) => {
    setScenario(next)
    setSelectedIndex(null)
  }, [])

  const selectPoint = useCallback((index: number) => {
    setSelectedIndex(index)
  }, [])

  const colors = useMemo(
    () => legendColors(overview?.legend ?? []),
    [overview],
  )

  if (overviewStatus === 'loading') {
    return <main className="water-demand-page"><div className="water-demand-state" aria-live="polite">加载需水补水概览...</div></main>
  }

  if (overviewStatus === 'error' || !overview) {
    return (
      <main className="water-demand-page">
        <div className="water-demand-state water-demand-state-error" aria-live="polite">
          <p>{overviewError || '需水补水概览加载失败'}</p>
          <button type="button" onClick={() => setOverviewAttempt((attempt) => attempt + 1)}>重试</button>
        </div>
      </main>
    )
  }

  const feature = overview.regions.features[0]
  if (!feature) {
    return (
      <main className="water-demand-page">
        <div className="water-demand-state water-demand-state-error" aria-live="polite">
          该板块暂无示范区数据
        </div>
      </main>
    )
  }
  const region: WaterDemandRegionProperties = feature.properties
  const grid = pointsState.status === 'ready' ? pointsState.grid : null

  return (
    <main className="water-demand-page">
      <h2 className="water-demand-page-heading">需水补水计算与评估</h2>
      <WaterDemandMap
        overview={overview}
        region={region}
        highlighted={!drilled}
        grid={grid}
        classColors={colors}
        selectedIndex={selectedIndex}
        onPointSelect={selectPoint}
      />
      {drilled ? (
        <div className="water-demand-region-controls">
          <button type="button" onClick={returnToOverview}>返回全国</button>
          <span>{region.name}</span>
        </div>
      ) : (
        <>
          <p className="water-demand-overview-instruction">正在定位示范区...</p>
          <nav className="water-demand-region-selector" aria-label="选择需水补水评估区域">
            <button type="button" aria-label="立即进入示范区域" onClick={enterRegion}>
              立即进入示范区域
            </button>
          </nav>
        </>
      )}
      {drilled && (
        <>
          <ScenarioSwitch scenario={scenario} onChange={changeScenario} />
          {pointsState.status === 'loading' && (
            <div className="water-demand-state water-demand-inline-state" aria-live="polite">
              加载区域点位...
            </div>
          )}
          {pointsState.status === 'error' && (
            <div className="water-demand-state water-demand-state-error water-demand-inline-state" aria-live="polite">
              <span>{pointsState.message}</span>
              <button type="button" onClick={loadPoints}>重试</button>
            </div>
          )}
          {selectedIndex !== null && grid && (
            <WaterDemandInfoCard
              grid={grid}
              index={selectedIndex}
              scenario={scenario}
              legend={overview.legend}
              onClose={() => setSelectedIndex(null)}
            />
          )}
          <WaterDemandLegend entries={overview.legend} />
        </>
      )}
    </main>
  )
}
