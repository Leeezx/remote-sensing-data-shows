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

const OVERALL_REGION_ID = 'DEMO'

function buildOverallRegion(
  overview: ReclamationOverviewWireResponse,
): ReclamationRegionProperties {
  const features = overview.regions.features
  const initialBounds: ReclamationRegionProperties['bounds'] = [[90, 180], [-90, -180]]
  const bounds = features.reduce<ReclamationRegionProperties['bounds']>((current, feature) => {
    const [[south, west], [north, east]] = feature.properties.bounds
    return [
      [Math.min(current[0][0], south), Math.min(current[0][1], west)],
      [Math.max(current[1][0], north), Math.max(current[1][1], east)],
    ]
  }, initialBounds)

  return {
    id: OVERALL_REGION_ID,
    name: '示范区域',
    pointCount: features.reduce((sum, feature) => sum + feature.properties.pointCount, 0),
    bounds: features.length > 0 ? bounds : [[15, 73], [54, 135]],
  }
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
    const regionRequests = region.id === OVERALL_REGION_ID && overview
      ? overview.regions.features.map((feature) => (
        getReclamationPoints(feature.properties.id, controller.signal)
      ))
      : [getReclamationPoints(region.id, controller.signal)]

    Promise.all(regionRequests)
      .then((responses) => {
        if (requestRef.current?.id !== id || controller.signal.aborted) return
        const firstResponse = responses[0]
        const data: ReclamationPointsResponse = {
          schemaVersion: firstResponse?.schemaVersion ?? 1,
          region: { id: region.id, name: region.name },
          unit: firstResponse?.unit ?? 'thousand_usd',
          fields: firstResponse?.fields ?? [],
          points: responses.flatMap((response) => response.points),
        }
        cacheRef.current.set(region.id, data)
        requestRef.current = null
        setPointsState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (requestRef.current?.id !== id || controller.signal.aborted || isAbort(error)) return
        requestRef.current = null
        setPointsState({ status: 'error', message: errorMessage(error, '复耕点位加载失败') })
      })
  }, [overview])

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

  const overallRegion = buildOverallRegion(overview)
  const points = pointsState.status === 'ready' ? pointsState.data.points : []
  const reclaimablePoints = points.filter((point) => (
    isReclaimable(scenarioMetrics(point, scenario))
  ))
  const selectedPointIndex = selectedPoint
    ? reclaimablePoints.findIndex((point) => point.id === selectedPoint.id)
    : -1

  const selectRelativePoint = (offset: -1 | 1) => {
    const nextIndex = offset === 1
      ? Math.min(selectedPointIndex + 1, reclaimablePoints.length - 1)
      : Math.max(selectedPointIndex - 1, 0)
    const point = reclaimablePoints[nextIndex]
    if (point) selectPoint(point)
  }

  return (
    <main className="reclamation-page">
      <h2 className="reclamation-page-heading">复耕潜力评估</h2>
      <ReclamationMap
        overview={overview}
        overallRegion={overallRegion}
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
            <button
              type="button"
              aria-label="选择示范区域"
              onClick={() => selectRegion(overallRegion)}
            >
              进入示范区域
            </button>
          </nav>
        </>
      )}
      {selectedRegion && pointsState.status === 'ready' && (
        <div className="reclamation-point-selector" aria-label="选择可复耕点位">
          <span className="reclamation-point-selector-status" role="status" aria-live="polite">
            {selectedPointIndex >= 0
              ? `点位 ${selectedPointIndex + 1}/${reclaimablePoints.length}：${selectedPoint?.id}`
              : `未选择点位（${reclaimablePoints.length} 个可复耕点位）`}
          </span>
          <button
            type="button"
            aria-label="上一个可复耕点位"
            disabled={selectedPointIndex <= 0}
            onClick={() => selectRelativePoint(-1)}
          >上一点</button>
          <button
            type="button"
            aria-label="下一个可复耕点位"
            disabled={reclaimablePoints.length === 0 || selectedPointIndex >= reclaimablePoints.length - 1}
            onClick={() => selectRelativePoint(1)}
          >下一点</button>
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
