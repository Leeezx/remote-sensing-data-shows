import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import type { TimeSeriesPoint, Layer, Region } from '../types'
import { getSeries } from '../services/api'

interface ChartPanelProps {
  activeLayerId: string | null
  layers: Layer[]
  regionId: string | null
  regions: Region[]
  startTime: string
  endTime: string
}

export default function ChartPanel({
  activeLayerId,
  layers,
  regionId,
  regions,
  startTime,
  endTime,
}: ChartPanelProps) {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<echarts.ECharts | null>(null)
  const [chartType, setChartType] = useState<'line' | 'bar'>('line')
  const [data, setData] = useState<TimeSeriesPoint[]>([])
  const [loading, setLoading] = useState(false)

  const activeLayer = layers.find((l) => l.id === activeLayerId)
  const activeRegion = regions.find((r) => r.id === regionId)

  // Fetch series data
  useEffect(() => {
    if (!activeLayerId) return
    let cancelled = false
    setLoading(true)
    getSeries(activeLayerId, regionId ?? undefined, startTime, endTime)
      .then((d) => {
        if (!cancelled) setData(d)
      })
      .catch(() => {
        if (!cancelled) setData([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [activeLayerId, regionId, startTime, endTime])

  // Render chart
  useEffect(() => {
    if (!chartRef.current) return

    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current)
    }

    const chart = chartInstance.current

    const option: echarts.EChartsOption = {
      title: {
        text: activeLayer
          ? `${activeLayer.name} 时间序列${activeRegion ? ` — ${activeRegion.name}` : ''}`
          : '时间序列',
        left: 'center',
        textStyle: { fontSize: 14 },
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params: unknown) => {
          const p = (params as { data: number[] }[])[0]
          return `${p.data[0]}<br/>${activeLayer?.name ?? ''}: ${p.data[1]} ${activeLayer?.unit ?? ''}`
        },
      },
      xAxis: {
        type: 'category',
        data: data.map((d) => d.time),
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        name: activeLayer?.unit ?? '',
        nameLocation: 'middle',
        nameGap: 40,
      },
      series: [
        {
          name: activeLayer?.name ?? 'Value',
          type: chartType,
          data: data.map((d) => [d.time, d.value]),
          smooth: chartType === 'line',
          itemStyle: { color: '#3388ff' },
        },
      ],
      grid: { top: 40, right: 20, bottom: 50, left: 50 },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20 }],
    }

    chart.setOption(option, true)

    const handleResize = () => chart.resize()
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
    }
  }, [data, activeLayer, activeRegion, chartType])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      chartInstance.current?.dispose()
      chartInstance.current = null
    }
  }, [])

  if (!activeLayerId) {
    return (
      <div className="chart-panel">
        <p className="hint">请先选择一个数据图层</p>
      </div>
    )
  }

  return (
    <div className="chart-panel">
      <div className="chart-controls">
        <button
          className={`btn btn-sm ${chartType === 'line' ? 'btn-primary' : ''}`}
          onClick={() => setChartType('line')}
        >
          📈 折线图
        </button>
        <button
          className={`btn btn-sm ${chartType === 'bar' ? 'btn-primary' : ''}`}
          onClick={() => setChartType('bar')}
        >
          📊 柱状图
        </button>
        <button
          className="btn btn-sm"
          onClick={() => {
            if (chartInstance.current) {
              const url = chartInstance.current.getDataURL({ type: 'png', pixelRatio: 2 })
              const link = document.createElement('a')
              link.href = url
              link.download = `${activeLayerId}_chart.png`
              link.click()
            }
          }}
        >
          💾 导出PNG
        </button>
      </div>
      {loading ? (
        <p className="hint">加载中...</p>
      ) : data.length === 0 ? (
        <p className="hint">暂无数据</p>
      ) : (
        <div ref={chartRef} style={{ width: '100%', height: '320px' }} />
      )}
    </div>
  )
}
