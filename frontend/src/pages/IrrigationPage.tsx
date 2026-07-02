import { useCallback, useEffect, useState } from 'react'
import Legend from '../components/Legend'
import MapView from '../components/MapView'
import {
  getIrrigationLayer,
  getIrrigationLegend,
  getIrrigationSeries,
  getIrrigationTimes,
  getIrrigationVectorGeoJSON,
  getIrrigationVectorStatus,
} from '../services/api'
import type {
  IrrigationRasterResolution,
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
  const [regionVector, setRegionVector] = useState<IrrigationVectorGeoJSON | null>(null)
  const [selectedRegion, setSelectedRegion] = useState<{ id: string; name: string } | null>(null)
  const [monthlySeries, setMonthlySeries] = useState<IrrigationSeriesResponse | null>(null)
  const [annualSeries, setAnnualSeries] = useState<IrrigationSeriesResponse | null>(null)
  const [seriesError, setSeriesError] = useState('')

  const activeIndex = Math.max(0, times.indexOf(currentTime))

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
      setVectorStatus(null)
      setRegionVector(null)
      setSelectedRegion(null)
      setMonthlySeries(null)
      setAnnualSeries(null)
      setSeriesError('')
      return
    }
    let cancelled = false
    setVectorStatus(null)
    setRegionVector(null)
    setSelectedRegion(null)
    setMonthlySeries(null)
    setAnnualSeries(null)
    setSeriesError('')
    getIrrigationVectorStatus(regionLevel)
      .then((status) => {
        if (cancelled) return
        setVectorStatus(status)
        if (!status.available) return null
        return getIrrigationVectorGeoJSON(regionLevel)
      })
      .then((data) => {
        if (!cancelled && data) {
          setRegionVector(data)
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
    return () => {
      cancelled = true
    }
  }, [regionLevel])

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
            展示年度与月度灌溉用水栅格，并通过行政区矢量点击读取县级、村级统计结果。
          </p>
        </section>

        <section className="sidebar-section">
          <h3>栅格数据</h3>
          <div className="resolution-toggle">
            <button
              className={`btn btn-sm ${rasterResolution === 'annual' ? 'btn-primary' : ''}`}
              onClick={() => setRasterResolution('annual')}
            >
              年度
            </button>
            <button
              className={`btn btn-sm ${rasterResolution === 'month' ? 'btn-primary' : ''}`}
              onClick={() => setRasterResolution('month')}
            >
              月度
            </button>
          </div>
          <div className="time-display">{currentTime ? formatTime(currentTime) : '暂无时间'}</div>
          <div className="timeline-track">
            <button className="timeline-prev" onClick={setPreviousTime} title="上一个">
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
            <button className="timeline-next" onClick={setNextTime} title="下一个">
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
              className={`btn btn-sm ${regionLevel === 'village' ? 'btn-primary' : ''}`}
              onClick={() => setRegionLevel((level) => (level === 'village' ? null : 'village'))}
            >
              村级统计
            </button>
          </div>
          <p className="hint">
            {!regionLevel
              ? '未开启行政区统计'
              : vectorStatus?.message
                ?? `正在加载${regionLevel === 'county' ? '县级' : '村级'}行政区矢量...`}
          </p>
          {regionLevel && vectorStatus?.available && (
            <p className="hint">
              请在地图上点击{regionLevel === 'county' ? '县级' : '村级'}行政区
            </p>
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
              regionVector={regionVector}
              selectedRegionId={selectedRegion?.id ?? null}
              onRegionSelect={setSelectedRegion}
            />
          </div>
        )}
        <Legend
          layer={layer}
          items={legendState.key === `irrigation_water:${currentTime}` ? legendState.items : []}
          status={legendState.key === `irrigation_water:${currentTime}` ? legendState.status : 'loading'}
        />
      </section>

      <aside className="irrigation-stats">
        <section className="stats-header">
          <h3>{selectedRegion?.name ?? '行政区统计'}</h3>
          <p>{selectedRegion ? '月度与年度灌溉用水量' : regionLevel ? '等待地图选择' : '未开启行政区统计'}</p>
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
        ) : !regionLevel ? (
          <div className="chart-empty">未开启行政区统计</div>
        ) : (
          <div className="chart-empty">
            {vectorStatus?.available
              ? `请在地图上点击${regionLevel === 'county' ? '县级' : '村级'}行政区`
              : vectorStatus?.message ?? '行政区矢量加载中...'}
          </div>
        )}
      </aside>
    </main>
  )
}
