import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Legend from '../components/Legend'
import MapView from '../components/MapView'
import {
  getIrrigationLayer,
  getIrrigationLegend,
  getIrrigationSeries,
  getIrrigationTimes,
  getIrrigationRegionAverages,
  getIrrigationVectorGeoJSON,
  getIrrigationVectorStatus,
} from '../services/api'
import type {
  IrrigationRasterResolution,
  IrrigationRegionAverage,
  IrrigationRegionLevel,
  IrrigationSeriesPeriod,
  IrrigationSeriesPoint,
  IrrigationSeriesResponse,
  IrrigationVectorGeoJSON,
  IrrigationVectorStatus,
  LegendItem,
  LegendStatus,
  Layer,
} from '../types'

function formatTime(time: string): string {
  const parts = time.split('-')
  if (parts.length === 3) return `${parts[0]}年${parts[1]}月${parts[2]}日`
  if (parts.length === 2) return `${parts[0]}年${parts[1]}月`
  return time
}

/** Interpolate a value into a hex color using legend stops (emulates np.interp). */
function interpolateColor(value: number, legend: LegendItem[]): string {
  if (legend.length === 0) return '#cccccc'
  // legend expected sorted ascending by value
  const stops = [...legend].sort((a, b) => a.value - b.value)
  if (value <= stops[0].value) return stops[0].color
  if (value >= stops[stops.length - 1].value) return stops[stops.length - 1].color

  // Find bracket
  let lo = stops[0], hi = stops[stops.length - 1]
  for (let i = 0; i < stops.length - 1; i++) {
    if (value >= stops[i].value && value <= stops[i + 1].value) {
      lo = stops[i]
      hi = stops[i + 1]
      break
    }
  }

  const t = (value - lo.value) / (hi.value - lo.value)
  const toByte = (hex: string, offset: number) => parseInt(hex.slice(1 + offset * 2, 3 + offset * 2), 16)
  const r = Math.round(toByte(lo.color, 0) + t * (toByte(hi.color, 0) - toByte(lo.color, 0)))
  const g = Math.round(toByte(lo.color, 1) + t * (toByte(hi.color, 1) - toByte(lo.color, 1)))
  const b = Math.round(toByte(lo.color, 2) + t * (toByte(hi.color, 2) - toByte(lo.color, 2)))
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
}

function buildRegionColorMap(
  averages: IrrigationRegionAverage[],
  legend: LegendItem[],
): Map<string, string> | null {
  if (averages.length === 0 || legend.length === 0) return null
  const result = new Map<string, string>()
  for (const item of averages) {
    if (item.average !== null) result.set(item.regionId, interpolateColor(item.average, legend))
  }
  return result.size > 0 ? result : null
}

function SeriesChart({
  regionName,
  period,
  unit,
  data,
}: {
  regionName: string
  period: IrrigationSeriesPeriod
  unit: string
  data: IrrigationSeriesPoint[]
}) {
  const width = 420
  const height = 180
  const padding = 28
  const values = data.map((point) => point.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(1, max - min)
  const xStep = data.length > 1 ? (width - padding * 2) / (data.length - 1) : 0
  const points = data.map((point, index) => {
    const x = padding + xStep * index
    const y = height - padding - ((point.value - min) / span) * (height - padding * 2)
    return { ...point, x, y }
  })
  const polyline = points.map((point) => `${point.x},${point.y}`).join(' ')
  const periodLabel = period === 'monthly' ? '月度' : '年度'

  if (data.length === 0) {
    return <div className="chart-empty">暂无时间序列数据</div>
  }

  return (
    <svg
      className="irrigation-chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${regionName} ${periodLabel}灌溉用水量折线图`}
    >
      <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
      <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} />
      <polyline points={polyline} fill="none" />
      {points.map((point) => (
        <circle key={point.time} cx={point.x} cy={point.y} r="3.5">
          <title>{`${point.time}: ${point.value} ${unit}`}</title>
        </circle>
      ))}
      <text x={padding} y={18}>{`${max} ${unit}`}</text>
      <text x={padding} y={height - 6}>{data[0]?.time}</text>
      <text x={width - padding} y={height - 6} textAnchor="end">
        {data[data.length - 1]?.time}
      </text>
    </svg>
  )
}

export default function IrrigationPage() {
  const vectorCacheRef = useRef(new Map<string, IrrigationVectorGeoJSON>())
  const [layer, setLayer] = useState<Layer | null>(null)
  const [layerError, setLayerError] = useState('')
  const [opacity, setOpacity] = useState(0.72)
  const [rasterResolution, setRasterResolution] =
    useState<IrrigationRasterResolution>('annual')
  const [times, setTimes] = useState<string[]>([])
  const [currentTime, setCurrentTime] = useState('')
  const [legendState, setLegendState] = useState<{
    key: string | null
    status: LegendStatus
    items: LegendItem[]
  }>({ key: null, status: 'loading', items: [] })

  const [regionLevel, setRegionLevel] = useState<IrrigationRegionLevel | null>(null)
  const [vectorStatus, setVectorStatus] = useState<IrrigationVectorStatus | null>(null)
  const [countyVector, setCountyVector] = useState<IrrigationVectorGeoJSON | null>(null)
  const townshipRequestIdRef = useRef(0)
  const [townshipVector, setTownshipVector] = useState<IrrigationVectorGeoJSON | null>(null)
  const [townshipAverages, setTownshipAverages] = useState<IrrigationRegionAverage[]>([])
  const [townshipLegend, setTownshipLegend] = useState<LegendItem[]>([])
  const [townshipLegendStatus, setTownshipLegendStatus] = useState<LegendStatus>('loading')
  const [townshipCounty, setTownshipCounty] = useState<{ id: string; name: string } | null>(null)
  const [pendingTownshipCounty, setPendingTownshipCounty] = useState<{ id: string; name: string } | null>(null)
  const [selectedRegion, setSelectedRegion] = useState<{ id: string; name: string } | null>(null)
  const [monthlySeries, setMonthlySeries] = useState<IrrigationSeriesResponse | null>(null)
  const [annualSeries, setAnnualSeries] = useState<IrrigationSeriesResponse | null>(null)
  const [seriesError, setSeriesError] = useState('')
  const [countyAverages, setCountyAverages] = useState<IrrigationRegionAverage[]>([])
  const [countyLegend, setCountyLegend] = useState<LegendItem[]>([])
  const [countyLegendStatus, setCountyLegendStatus] = useState<LegendStatus>('loading')
  const [adminStatsLoading, setAdminStatsLoading] = useState(false)

  const activeIndex = Math.max(0, times.indexOf(currentTime))

  const loadVector = useCallback(async (
    level: IrrigationRegionLevel,
    countyId?: string,
  ) => {
    const cacheKey = `${level}:${countyId ?? 'all'}`
    const cached = vectorCacheRef.current.get(cacheKey)
    if (cached) return cached
    const data = await getIrrigationVectorGeoJSON(level, countyId)
    if (level === 'township' && data.features.length > 499) {
      throw new Error('乡镇分片超过 499 个要素，已停止加载以保护地图性能')
    }
    vectorCacheRef.current.set(cacheKey, data)
    return data
  }, [])

  const loadTownshipCounty = useCallback(async (county: { id: string; name: string }) => {
    const requestId = ++townshipRequestIdRef.current
    setPendingTownshipCounty(county)
    setSelectedRegion(null)
    setSeriesError('')
    setAdminStatsLoading(true)
    try {
      const vector = await loadVector('township', county.id)
      if (requestId !== townshipRequestIdRef.current) return
      setTownshipVector(vector)
      setTownshipCounty(county)
      setTownshipAverages([])
      setTownshipLegend([])
      setTownshipLegendStatus('loading')
      setVectorStatus({
        level: 'township',
        available: true,
        url: `/api/irrigation/vectors/township?countyId=${encodeURIComponent(county.id)}`,
        message: `已加载${county.name} ${vector.features.length} 个乡镇`,
      })
      try {
        const averages = await getIrrigationRegionAverages('township', county.id)
        if (requestId !== townshipRequestIdRef.current) return
        setTownshipAverages(averages.averages)
        setTownshipLegend(averages.legend)
        setTownshipLegendStatus('ready')
      } catch {
        if (requestId === townshipRequestIdRef.current) setTownshipLegendStatus('error')
      }
    } catch (error) {
      if (requestId !== townshipRequestIdRef.current) return
      setVectorStatus({
        level: 'township',
        available: false,
        url: null,
        message: error instanceof Error ? error.message : '该县乡镇矢量暂不可用',
      })
    } finally {
      if (requestId === townshipRequestIdRef.current) setPendingTownshipCounty(null)
      if (requestId === townshipRequestIdRef.current) setAdminStatsLoading(false)
    }
  }, [loadVector])

  useEffect(() => {
    let cancelled = false
    getIrrigationLayer()
      .then((data) => {
        if (!cancelled) setLayer(data)
      })
      .catch(() => {
        if (!cancelled) setLayerError('灌溉用水图层元数据暂不可用')
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setTimes([])
    setCurrentTime('')
    getIrrigationTimes(rasterResolution)
      .then((data) => {
        if (cancelled) return
        setTimes(data)
        setCurrentTime(data[0] ?? '')
      })
      .catch(() => {
        if (!cancelled) setTimes([])
      })
    return () => {
      cancelled = true
    }
  }, [rasterResolution])

  useEffect(() => {
    if (!currentTime) {
      setLegendState({ key: null, status: 'loading', items: [] })
      return
    }
    const key = `irrigation_water:${currentTime}`
    let cancelled = false
    setLegendState({ key, status: 'loading', items: [] })
    getIrrigationLegend(currentTime)
      .then((data) => {
        if (!cancelled) setLegendState({ key, status: 'ready', items: data.legend })
      })
      .catch(() => {
        if (!cancelled) setLegendState({ key, status: 'error', items: [] })
      })
    return () => {
      cancelled = true
    }
  }, [currentTime])

  useEffect(() => {
    if (!regionLevel) {
      townshipRequestIdRef.current += 1
      setVectorStatus(null)
      setCountyVector(null)
      setTownshipVector(null)
      setTownshipAverages([])
      setTownshipLegend([])
      setTownshipLegendStatus('loading')
      setTownshipCounty(null)
      setPendingTownshipCounty(null)
      setSelectedRegion(null)
      setMonthlySeries(null)
      setAnnualSeries(null)
      setSeriesError('')
      setCountyAverages([])
      setCountyLegend([])
      setCountyLegendStatus('loading')
      setAdminStatsLoading(false)
      return
    }
    let cancelled = false
    townshipRequestIdRef.current += 1
    setVectorStatus(null)
    setCountyVector(null)
    setTownshipVector(null)
    setTownshipAverages([])
    setTownshipLegend([])
    setTownshipLegendStatus('loading')
    setTownshipCounty(null)
    setPendingTownshipCounty(null)
    setSelectedRegion(null)
    setMonthlySeries(null)
    setAnnualSeries(null)
    setSeriesError('')
    setAdminStatsLoading(true)
    setCountyAverages([])
    setCountyLegend([])
    setCountyLegendStatus('loading')
    const loadInitialAdminLayer = async () => {
      const statusAndVector = getIrrigationVectorStatus(regionLevel)
        .then(async (status) => {
          if (cancelled) return
          setVectorStatus(status)
          if (!status.available) return
          try {
            const vector = await loadVector('county')
            if (!cancelled) setCountyVector(vector)
          } catch {
            if (!cancelled) {
              setVectorStatus({
                level: regionLevel,
                available: false,
                url: null,
                message: '行政区矢量暂不可用',
              })
            }
          }
        })
        .catch(() => {
          if (!cancelled) {
            setVectorStatus({
              level: regionLevel,
              available: false,
              url: null,
              message: '行政区矢量暂不可用',
            })
          }
        })
      const averages = getIrrigationRegionAverages('county')
        .then((avgData) => {
          if (cancelled) return
          setCountyAverages(avgData.averages)
          setCountyLegend(avgData.legend)
          setCountyLegendStatus('ready')
        })
        .catch(() => {
          if (!cancelled) setCountyLegendStatus('error')
        })
      await Promise.all([statusAndVector, averages])
      if (!cancelled) setAdminStatsLoading(false)
    }
    void loadInitialAdminLayer()
    return () => {
      cancelled = true
    }
  }, [loadVector, regionLevel])

  useEffect(() => {
    if (!regionLevel || !selectedRegion) {
      setMonthlySeries(null)
      setAnnualSeries(null)
      return
    }
    let cancelled = false
    setSeriesError('')
    Promise.all([
      getIrrigationSeries(regionLevel, selectedRegion.id, 'monthly'),
      getIrrigationSeries(regionLevel, selectedRegion.id, 'annual'),
    ])
      .then(([monthly, annual]) => {
        if (!cancelled) {
          setMonthlySeries(monthly)
          setAnnualSeries(annual)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMonthlySeries(null)
          setAnnualSeries(null)
          setSeriesError('行政区灌溉用水统计暂不可用')
        }
      })
    return () => {
      cancelled = true
    }
  }, [regionLevel, selectedRegion])

  const countyColorMap = useMemo(
    () => buildRegionColorMap(countyAverages, countyLegend),
    [countyAverages, countyLegend],
  )

  const townshipColorMap = useMemo(
    () => buildRegionColorMap(townshipAverages, townshipLegend),
    [townshipAverages, townshipLegend],
  )

  const isAdminStatsMode = regionLevel !== null

  const handleCountySelect = useCallback((region: { id: string; name: string }) => {
    if (regionLevel === 'township') {
      void loadTownshipCounty(region)
      return
    }
    setSelectedRegion(region)
  }, [loadTownshipCounty, regionLevel])

  const returnToCountySelection = useCallback(() => {
    townshipRequestIdRef.current += 1
    setTownshipCounty(null)
    setPendingTownshipCounty(null)
    setTownshipVector(null)
    setTownshipAverages([])
    setTownshipLegend([])
    setTownshipLegendStatus('loading')
    setSelectedRegion(null)
    setMonthlySeries(null)
    setAnnualSeries(null)
    setSeriesError('')
    setVectorStatus({
      level: 'township',
      available: true,
      url: '/api/irrigation/vectors/township?countyId={countyId}',
      message: '请先在地图上选择县域，再加载该县乡镇',
    })
  }, [])

  const adminLegendGroups = regionLevel === 'township' && townshipVector
    ? [
        { title: '县级年平均', items: countyLegend, status: countyLegendStatus },
        { title: '当前县乡镇年平均', items: townshipLegend, status: townshipLegendStatus },
      ]
    : [{ title: '县级年平均', items: countyLegend, status: countyLegendStatus }]

  const setPreviousTime = useCallback(() => {
    if (activeIndex > 0) setCurrentTime(times[activeIndex - 1])
  }, [activeIndex, times])

  const setNextTime = useCallback(() => {
    if (activeIndex < times.length - 1) setCurrentTime(times[activeIndex + 1])
  }, [activeIndex, times])

  return (
    <main className="app-main irrigation-main">
      <aside className="irrigation-panel">
        <section className="sidebar-section">
          <h2>灌溉用水数据展示</h2>
          <p className="layer-desc">
            展示年度与月度灌溉用水栅格，并通过行政区矢量点击读取县级、乡镇级统计结果。
          </p>
        </section>

        <section className="sidebar-section">
          <h3>栅格数据</h3>
          <div className="resolution-toggle">
            <button
              className={`btn btn-sm ${rasterResolution === 'annual' ? 'btn-primary' : ''}`}
              onClick={() => setRasterResolution('annual')}
              disabled={isAdminStatsMode}
            >
              年度
            </button>
            <button
              className={`btn btn-sm ${rasterResolution === 'month' ? 'btn-primary' : ''}`}
              onClick={() => setRasterResolution('month')}
              disabled={isAdminStatsMode}
            >
              月度
            </button>
          </div>
          <div className="time-display">{currentTime ? formatTime(currentTime) : '暂无时间'}</div>
          <div className="timeline-track">
            <button className="timeline-prev" onClick={setPreviousTime} title="上一个" disabled={isAdminStatsMode}>
              ◀
            </button>
            <div className="timeline-bar-wrapper">
              <div className="timeline-bar">
                <div
                  className="timeline-filled"
                  style={{
                    width: `${(activeIndex / Math.max(1, times.length - 1)) * 100}%`,
                  }}
                />
                <div
                  className="timeline-thumb"
                  style={{
                    left: `${(activeIndex / Math.max(1, times.length - 1)) * 100}%`,
                  }}
                />
              </div>
            </div>
            <button className="timeline-next" onClick={setNextTime} title="下一个" disabled={isAdminStatsMode}>
              ▶
            </button>
          </div>
        </section>

        <section className="sidebar-section">
          <h3>图层透明度</h3>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={opacity}
            onChange={(event) => setOpacity(Number(event.target.value))}
          />
          <span className="opacity-value">{Math.round(opacity * 100)}%</span>
        </section>

        <section className="sidebar-section">
          <h3>行政区统计</h3>
          <div className="resolution-toggle">
            <button
              className={`btn btn-sm ${regionLevel === 'county' ? 'btn-primary' : ''}`}
              onClick={() => setRegionLevel((level) => (level === 'county' ? null : 'county'))}
            >
              县级统计
            </button>
            <button
              className={`btn btn-sm ${regionLevel === 'township' ? 'btn-primary' : ''}`}
              onClick={() => setRegionLevel((level) => (level === 'township' ? null : 'township'))}
            >
              乡镇级统计
            </button>
          </div>
          {!(regionLevel === 'township' && townshipVector && vectorStatus?.available === false) && (
            <p className="hint">
              {!regionLevel
                ? '未开启行政区统计'
                : vectorStatus?.message
                  ?? `正在加载${regionLevel === 'county' ? '县级' : '乡镇级'}行政区矢量...`}
            </p>
          )}
          {regionLevel && vectorStatus?.available && (
            <p className="hint">
              {regionLevel === 'township' && !townshipCounty
                ? '请在地图上点击一个县域'
                : `请在地图上点击${regionLevel === 'county' ? '县级' : '乡镇级'}行政区`}
            </p>
          )}
          {regionLevel === 'township' && townshipCounty && (
            <button className="btn btn-sm" onClick={returnToCountySelection}>
              返回县级选择
            </button>
          )}
        </section>
      </aside>

      <section className="map-area irrigation-map-area">
        {layerError ? (
          <div className="loading error">{layerError}</div>
        ) : (
          <div className="map-area-wrapper">
            <MapView
              layers={layer ? [layer] : []}
              activeLayerId={layer?.id ?? null}
              opacity={opacity}
              currentTime={currentTime}
              regionVector={isAdminStatsMode ? countyVector : null}
              selectedRegionId={regionLevel === 'county' ? selectedRegion?.id ?? null : townshipCounty?.id ?? null}
              onRegionSelect={handleCountySelect}
              disableQuery={isAdminStatsMode}
              hideRaster={isAdminStatsMode}
              regionColorMap={countyColorMap}
              regionLevel={isAdminStatsMode ? 'county' : null}
              detailRegionVector={regionLevel === 'township' ? townshipVector : null}
              detailRegionLevel={regionLevel === 'township' && townshipVector ? 'township' : null}
              detailRegionColorMap={townshipColorMap}
              detailSelectedRegionId={regionLevel === 'township' ? selectedRegion?.id : null}
              onDetailRegionSelect={regionLevel === 'township' ? setSelectedRegion : undefined}
            />
          </div>
        )}
        <Legend
          layer={layer}
          items={
            legendState.key === `irrigation_water:${currentTime}` ? legendState.items : []
          }
          status={
            legendState.key === `irrigation_water:${currentTime}` ? legendState.status : 'loading'
          }
          groups={isAdminStatsMode ? adminLegendGroups : undefined}
        />
      </section>

      <aside className="irrigation-stats">
        <section className="stats-header">
          <h3>{selectedRegion?.name ?? townshipCounty?.name ?? pendingTownshipCounty?.name ?? '行政区统计'}</h3>
          <p>{selectedRegion
            ? '月度与年度灌溉用水量'
            : townshipCounty
              ? '等待乡镇选择'
              : regionLevel === 'township'
                ? '等待县域选择'
                : regionLevel
                  ? '等待地图选择'
                  : '未开启行政区统计'}</p>
        </section>
        {seriesError ? (
          <div className="loading error">{seriesError}</div>
        ) : monthlySeries && annualSeries ? (
          <>
            <div className="stats-grid">
              <div>月度总量 {monthlySeries.summary.total} {monthlySeries.unit}</div>
              <div>月度均值 {monthlySeries.summary.average} {monthlySeries.unit}</div>
              <div>年度最大 {annualSeries.summary.max} {annualSeries.unit}</div>
              <div>年度最小 {annualSeries.summary.min} {annualSeries.unit}</div>
            </div>
            <SeriesChart
              regionName={monthlySeries.region.name}
              period={monthlySeries.period}
              unit={monthlySeries.unit}
              data={monthlySeries.series}
            />
            <SeriesChart
              regionName={annualSeries.region.name}
              period={annualSeries.period}
              unit={annualSeries.unit}
              data={annualSeries.series}
            />
          </>
        ) : selectedRegion ? (
          <div className="loading">加载统计数据...</div>
        ) : (regionLevel && adminStatsLoading) ? (
          <div className="loading">加载行政区统计数据...</div>
        ) : !regionLevel ? (
          <div className="chart-empty">未开启行政区统计</div>
        ) : (
          <div className="chart-empty">
            {vectorStatus?.available
              ? regionLevel === 'township' && !townshipCounty
                ? '请先在地图上点击一个县域'
                : `请在地图上点击${regionLevel === 'county' ? '县级' : '乡镇级'}行政区`
              : vectorStatus?.message ?? '行政区矢量加载中...'}
          </div>
        )}
      </aside>
    </main>
  )
}
