import { useCallback, useEffect, useRef, useState } from 'react'
import axios from 'axios'
import ReclamationInfoCard from '../components/ReclamationInfoCard'
import ReclamationLegend from '../components/ReclamationLegend'
import ReclamationMap from '../components/ReclamationMap'
import ScenarioSwitch from '../components/ScenarioSwitch'
import { isReclaimable, scenarioMetrics } from '../components/reclamationCanvas'
import { getReclamationOverview, getReclamationPoints } from '../services/api'
import type {
  ReclamationOverviewWireResponse,
  ReclamationPoint,
  ReclamationPointsResponse,
  ReclamationRegionProperties,
  ReclamationScenario,
} from '../types'

type PointsState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: ReclamationPointsResponse }

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback
}

function isAbort(error: unknown) {
  return axios.isCancel(error) || (error instanceof Error && error.name === 'AbortError')
}

export default function ReclamationPage() {
  const [overview, setOverview] = useState<ReclamationOverviewWireResponse | null>(null)
  const [overviewStatus, setOverviewStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [overviewError, setOverviewError] = useState('')
  const [overviewAttempt, setOverviewAttempt] = useState(0)
  const [selectedRegion, setSelectedRegion] = useState<ReclamationRegionProperties | null>(null)
  const [pointsState, setPointsState] = useState<PointsState>({ status: 'idle' })
  const [scenario, setScenario] = useState<ReclamationScenario>('current')
  const [selectedPoint, setSelectedPoint] = useState<ReclamationPoint | null>(null)
  const cacheRef = useRef(new Map<string, ReclamationPointsResponse>())
  const requestRef = useRef<{ id: number; controller: AbortController } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    setOverviewStatus('loading')
    setOverviewError('')
    getReclamationOverview(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        setOverview(data)
        setOverviewStatus('ready')
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || isAbort(error)) return
        setOverviewError(errorMessage(error, '复耕概览加载失败'))
        setOverviewStatus('error')
      })
    return () => controller.abort()
  }, [overviewAttempt])

  useEffect(() => () => {
    requestRef.current?.controller.abort()
    requestRef.current = null
  }, [])

  const selectRegion = useCallback((region: ReclamationRegionProperties) => {
    const prior = requestRef.current
    if (prior) prior.controller.abort()
    const id = (prior?.id ?? 0) + 1
    requestRef.current = null
    setSelectedRegion(region)
    setSelectedPoint(null)
    setScenario('current')

    const cached = cacheRef.current.get(region.id)
    if (cached) {
      setPointsState({ status: 'ready', data: cached })
      return
    }

    const controller = new AbortController()
    requestRef.current = { id, controller }
    setPointsState({ status: 'loading' })
    getReclamationPoints(region.id, controller.signal)
      .then((data) => {
        if (requestRef.current?.id !== id || controller.signal.aborted) return
        cacheRef.current.set(region.id, data)
        requestRef.current = null
        setPointsState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (requestRef.current?.id !== id || controller.signal.aborted || isAbort(error)) return
        requestRef.current = null
        setPointsState({ status: 'error', message: errorMessage(error, '复耕点位加载失败') })
      })
  }, [])

  const retryPoints = useCallback(() => {
    if (selectedRegion) selectRegion(selectedRegion)
  }, [selectRegion, selectedRegion])

  const returnToOverview = useCallback(() => {
    requestRef.current?.controller.abort()
    requestRef.current = null
    setSelectedRegion(null)
    setPointsState({ status: 'idle' })
    setSelectedPoint(null)
    setScenario('current')
  }, [])

  const selectPoint = useCallback((point: ReclamationPoint) => {
    if (isReclaimable(scenarioMetrics(point, scenario))) setSelectedPoint(point)
  }, [scenario])

  const changeScenario = useCallback((next: ReclamationScenario) => {
    setScenario(next)
    setSelectedPoint(null)
  }, [])

  if (overviewStatus === 'loading') {
    return <main className="reclamation-page"><div className="reclamation-state" aria-live="polite">加载复耕潜力概览...</div></main>
  }

  if (overviewStatus === 'error' || !overview) {
    return (
      <main className="reclamation-page">
        <div className="reclamation-state reclamation-state-error" aria-live="polite">
          <p>{overviewError || '复耕概览加载失败'}</p>
          <button type="button" onClick={() => setOverviewAttempt((attempt) => attempt + 1)}>重试</button>
        </div>
      </main>
    )
  }

  const points = pointsState.status === 'ready' ? pointsState.data.points : []
  const reclaimablePoints = points.filter((point) => (
    isReclaimable(scenarioMetrics(point, scenario))
  ))

  return (
    <main className="reclamation-page">
      <h2 className="reclamation-page-heading">复耕潜力评估</h2>
      <ReclamationMap
        overview={overview}
        selectedRegion={selectedRegion}
        points={points}
        scenario={scenario}
        onRegionSelect={selectRegion}
        onPointSelect={selectPoint}
      />
      {selectedRegion ? (
        <div className="reclamation-region-controls">
          <button type="button" onClick={returnToOverview}>返回全国</button>
          <span>{selectedRegion.name}</span>
        </div>
      ) : (
        <>
          <p className="reclamation-overview-instruction">点击高亮区域查看复耕潜力</p>
          <nav className="reclamation-region-selector" aria-label="选择复耕评估区域">
            {overview.regions.features.map((feature) => {
              const region = feature.properties
              return (
                <button
                  key={region.id}
                  type="button"
                  aria-label={`选择区域：${region.name}`}
                  onClick={() => selectRegion(region)}
                >
                  {region.name}
                </button>
              )
            })}
          </nav>
        </>
      )}
      {selectedRegion && pointsState.status === 'ready' && (
        <div className="reclamation-point-selector">
          <label htmlFor="reclamation-point-select">选择可复耕点位</label>
          <select
            id="reclamation-point-select"
            value={selectedPoint?.id ?? ''}
            onChange={(event) => {
              const point = reclaimablePoints.find((candidate) => candidate.id === event.currentTarget.value)
              if (point) {
                selectPoint(point)
              } else {
                setSelectedPoint(null)
              }
            }}
            onKeyDown={(event) => {
              if (event.key === 'ArrowDown' && event.currentTarget.value === '' && reclaimablePoints[0]) {
                event.preventDefault()
                selectPoint(reclaimablePoints[0])
              }
            }}
          >
            <option value="">选择点位</option>
            {reclaimablePoints.map((point) => (
              <option key={point.id} value={point.id}>
                {point.id}（{point.longitude.toFixed(6)}, {point.latitude.toFixed(6)}）
              </option>
            ))}
          </select>
        </div>
      )}
      <ScenarioSwitch scenario={scenario} onChange={changeScenario} />
      {pointsState.status === 'loading' && <div className="reclamation-state reclamation-inline-state" aria-live="polite">加载区域点位...</div>}
      {pointsState.status === 'error' && (
        <div className="reclamation-state reclamation-state-error reclamation-inline-state" aria-live="polite">
          <span>{pointsState.message}</span>
          <button type="button" onClick={retryPoints}>重试</button>
        </div>
      )}
      {selectedPoint && <ReclamationInfoCard point={selectedPoint} scenario={scenario} onClose={() => setSelectedPoint(null)} />}
      <ReclamationLegend scenario={scenario} />
    </main>
  )
}
