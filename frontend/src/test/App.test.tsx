import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { IrrigationRegion, IrrigationSeriesPeriod } from '../types'

const apiMocks = vi.hoisted(() => ({
  getLayers: vi.fn(),
  getLayerTimes: vi.fn(),
  getLayerLegend: vi.fn(),
  getRegions: vi.fn(),
  getIrrigationLayer: vi.fn(),
  getIrrigationLegend: vi.fn(),
  getIrrigationTimes: vi.fn(),
  getIrrigationRegions: vi.fn(),
  getIrrigationSeries: vi.fn(),
  getIrrigationVectorStatus: vi.fn(),
  getIrrigationVectorGeoJSON: vi.fn(),
}))

vi.mock('../services/api', () => ({
  ...apiMocks,
  queryPoint: vi.fn(),
  queryArea: vi.fn(),
  getExportCsvUrl: vi.fn(() => '/api/export/csv'),
  login: vi.fn(),
}))

vi.mock('../components/MapView', () => ({
  default: (props: {
    onRegionSelect?: (region: { id: string; name: string }) => void
    regionVector?: unknown
  }) => (
    <div data-testid="map-view">
      地图
      {props.regionVector ? <span>行政区矢量已加载</span> : null}
      <button
        type="button"
        onClick={() => props.onRegionSelect?.({ id: 'county_a', name: '示范县A' })}
      >
        选择示范县A
      </button>
    </div>
  ),
}))

const layers = [
  {
    id: 'ssm',
    name: '土壤湿度',
    description: '表层土壤湿度',
    type: 'raster',
    unit: 'm³/m³',
    range: { min: 0, max: 1 },
    timeRange: { start: '2025-01-01', end: '2025-01-09', step: '8day' },
    tileTemplate: '/tiles/{time}/{z}/{x}/{y}.png',
    legend: [{ value: 0, color: '#999999', label: 'SSM 静态图例' }],
  },
  {
    id: 'ndvi',
    name: '植被指数',
    description: '归一化植被指数',
    type: 'raster',
    unit: '',
    range: { min: -1, max: 1 },
    timeRange: { start: '2025-01-01', end: '2025-01-25', step: '8day' },
    tileTemplate: '/tiles/ndvi/{time}/{z}/{x}/{y}.png',
    legend: [{ value: 0.5, color: '#00aa00', label: 'NDVI 静态图例' }],
  },
]

const irrigationLayer = {
  id: 'irrigation_water',
  name: '灌溉用水量',
  description: '年度与8天时间分辨率灌溉用水栅格数据',
  type: 'irrigation',
  unit: '万m³',
  range: { min: 0, max: 220 },
  timeRange: { start: '2021', end: '2023', step: 'annual' },
  tileTemplate: '/data/tiles/irrigation_water/{time}/{z}/{x}/{y}.png',
  legend: [{ value: 80, color: '#2b8cbe', label: '80 万m³' }],
}

const countyRegions: IrrigationRegion[] = [
  { id: 'county_a', name: '示范县A', level: 'county' as const, parentId: null },
  { id: 'county_b', name: '示范县B', level: 'county' as const, parentId: null },
]

const villageRegions: IrrigationRegion[] = [
  { id: 'village_a1', name: '灌区村A1', level: 'village' as const, parentId: 'county_a' },
]

function irrigationSeries(
  region: IrrigationRegion = countyRegions[0],
  period: IrrigationSeriesPeriod = 'monthly',
) {
  return {
    region,
    period,
    unit: '万m³',
    series: period === 'monthly'
      ? [
          { time: '2023-01', value: 118.4 },
          { time: '2023-02', value: 101.8 },
          { time: '2023-03', value: 109.6 },
        ]
      : [
          { time: '2021', value: 1420.5 },
          { time: '2022', value: 1488.7 },
          { time: '2023', value: 1532.2 },
        ],
    summary: { total: 1532.2, average: 127.7, max: 214.5, min: 101.8 },
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function legendResponse(time: string, label: string) {
  return {
    layerId: 'ssm',
    time,
    unit: 'm³/m³',
    legend: [{ value: 0.25, color: '#123456', label }],
  }
}

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.history.pushState({}, '', '/')
    apiMocks.getLayers.mockResolvedValue(layers)
    apiMocks.getLayerTimes.mockResolvedValue([
      '2025-01-01',
      '2025-01-09',
      '2025-01-17',
    ])
    apiMocks.getLayerLegend.mockResolvedValue(
      legendResponse('2025-01-01', '首期动态图例'),
    )
    apiMocks.getRegions.mockResolvedValue([])
    apiMocks.getIrrigationLayer.mockResolvedValue(irrigationLayer)
    apiMocks.getIrrigationLegend.mockImplementation((time: string) => (
      Promise.resolve({
        layerId: 'irrigation_water',
        time,
        unit: '万m³',
        legend: [{ value: 9.5, color: '#123456', label: `${time} 动态图例` }],
      })
    ))
    apiMocks.getIrrigationTimes.mockResolvedValue(['2021', '2022', '2023'])
    apiMocks.getIrrigationRegions.mockImplementation((level: 'county' | 'village') => (
      Promise.resolve(level === 'county' ? countyRegions : villageRegions)
    ))
    apiMocks.getIrrigationSeries.mockImplementation(
      (level: 'county' | 'village', _regionId: string, period: 'annual' | 'monthly') => (
        Promise.resolve(irrigationSeries(
          level === 'county' ? countyRegions[0] : villageRegions[0],
          period,
        ))
      ),
    )
    apiMocks.getIrrigationVectorStatus.mockImplementation((level: 'county' | 'village') => (
      Promise.resolve(level === 'county'
        ? {
            level: 'county',
            available: true,
            url: '/api/irrigation/vectors/county',
            message: '县级行政区矢量可用',
          }
        : {
            level: 'village',
            available: false,
            url: null,
            message: '村级行政区矢量暂未配置',
          })
    ))
    apiMocks.getIrrigationVectorGeoJSON.mockResolvedValue({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { id: 'county_a', name: '示范县A' },
          geometry: {
            type: 'Polygon',
            coordinates: [[[100, 30], [101, 30], [101, 31], [100, 30]]],
          },
        },
      ],
    })
  })

  it('shows navigation for the four platform sections', async () => {
    render(<App />)

    expect(await screen.findByRole('link', { name: '基础数据展示' })).toHaveAttribute('href', '/base')
    expect(screen.getByRole('link', { name: '灌溉用水数据展示' })).toHaveAttribute('href', '/irrigation')
    expect(screen.getByRole('link', { name: '复耕潜力评估' })).toHaveAttribute('href', '/reclamation')
    expect(screen.getByRole('link', { name: '需水补水计算与评估' })).toHaveAttribute('href', '/water-demand')
  })

  it('loads the irrigation page with annual/monthly timeline and leaves statistics off by default', async () => {
    window.history.pushState({}, '', '/irrigation')

    render(<App />)

    expect(await screen.findByRole('heading', { name: '灌溉用水数据展示' })).toBeInTheDocument()
    expect(apiMocks.getIrrigationLayer).toHaveBeenCalledOnce()
    expect(apiMocks.getIrrigationTimes).toHaveBeenCalledWith('annual')
    await waitFor(() => {
      expect(apiMocks.getIrrigationLegend).toHaveBeenCalledWith('2021')
    })
    expect(apiMocks.getIrrigationVectorStatus).not.toHaveBeenCalled()
    expect(apiMocks.getIrrigationVectorGeoJSON).not.toHaveBeenCalled()
    expect(apiMocks.getIrrigationSeries).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: '年度' })).toHaveClass('btn-primary')
    expect(screen.getByRole('button', { name: '月度' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '县级统计' })).not.toHaveClass('btn-primary')
    expect(screen.queryByText('行政区矢量已加载')).not.toBeInTheDocument()
    expect((await screen.findAllByText('未开启行政区统计')).length).toBeGreaterThan(0)
  })

  it('loads county statistics after selecting a county on the map', async () => {
    window.history.pushState({}, '', '/irrigation')
    const user = userEvent.setup()

    render(<App />)

    await user.click(await screen.findByRole('button', { name: '县级统计' }))
    await screen.findByText('行政区矢量已加载')
    await user.click(await screen.findByRole('button', { name: '选择示范县A' }))

    await waitFor(() => {
      expect(apiMocks.getIrrigationSeries).toHaveBeenCalledWith(
        'county',
        'county_a',
        'monthly',
      )
    })
    expect(screen.getByText('月度总量 1532.2 万m³')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '示范县A 月度灌溉用水量折线图' })).toBeInTheDocument()
  })

  it('switches monthly raster timeline and reports missing village vector data', async () => {
    window.history.pushState({}, '', '/irrigation')
    const user = userEvent.setup()

    render(<App />)
    expect(await screen.findByRole('button', { name: '月度' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '月度' }))

    await waitFor(() => {
      expect(apiMocks.getIrrigationTimes).toHaveBeenLastCalledWith('month')
    })
    await waitFor(() => {
      expect(apiMocks.getIrrigationLegend).toHaveBeenCalledWith('2021')
    })

    await user.click(screen.getByRole('button', { name: '村级统计' }))

    await waitFor(() => {
      expect(apiMocks.getIrrigationVectorStatus).toHaveBeenCalledWith('village')
    })
    expect((await screen.findAllByText('村级行政区矢量暂未配置')).length).toBeGreaterThan(0)
  })

  it('loads the map without legacy region or chart panels', async () => {
    const { container } = render(<App />)

    expect(await screen.findByTestId('map-view')).toBeInTheDocument()
    await waitFor(() => {
      expect(apiMocks.getLayers).toHaveBeenCalledOnce()
      expect(apiMocks.getLayerTimes).toHaveBeenCalledWith('ssm', '8day')
    })

    expect(apiMocks.getRegions).not.toHaveBeenCalled()
    expect(screen.queryByText(/区域筛选/)).not.toBeInTheDocument()
    expect(screen.queryByText(/折线图|柱状图/)).not.toBeInTheDocument()
    expect(container.querySelector('.right-panel')).not.toBeInTheDocument()
    expect(screen.getByText(/点击地图查询像元值；按住 Shift 拖拽框选区域/)).toBeInTheDocument()
  })

  it('clears stale times while a changed resolution is loading', async () => {
    const pendingTimes = new Promise<string[]>(() => undefined)
    apiMocks.getLayerTimes
      .mockReset()
      .mockResolvedValueOnce(['2025-01-01', '2025-01-09'])
      .mockReturnValueOnce(pendingTimes)
    const user = userEvent.setup()

    render(<App />)
    expect(await screen.findByText('2025年01月09日')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '月度' }))
    await waitFor(() => {
      expect(apiMocks.getLayerTimes).toHaveBeenLastCalledWith('ssm', 'month')
    })

    expect(screen.queryAllByText(/2025年01月(?:01|09)日/)).toHaveLength(0)
  })

  it('invalidates the dynamic legend in the resolution-change event', async () => {
    const pendingTimes = new Promise<string[]>(() => undefined)
    let oldLegendVisibleWhenMonthRequestStarted: boolean | undefined
    apiMocks.getLayerTimes
      .mockReset()
      .mockResolvedValueOnce(['2025-01-01', '2025-01-09'])
      .mockImplementationOnce(() => {
        oldLegendVisibleWhenMonthRequestStarted = screen.queryByText(
          '首期动态图例',
        ) !== null
        return pendingTimes
      })
    const user = userEvent.setup()

    render(<App />)
    expect(await screen.findByText('首期动态图例')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '月度' }))
    await waitFor(() => {
      expect(apiMocks.getLayerTimes).toHaveBeenLastCalledWith('ssm', 'month')
    })

    expect(oldLegendVisibleWhenMonthRequestStarted).toBe(false)
    expect(screen.queryByText('首期动态图例')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('正在加载图例...')
  })

  it('keeps the current time and legend when clicking the active resolution', async () => {
    const user = userEvent.setup()
    render(<App />)
    expect(await screen.findByText('首期动态图例')).toBeInTheDocument()
    expect(screen.getAllByText('2025年01月01日').length).toBeGreaterThan(0)
    expect(apiMocks.getLayerTimes).toHaveBeenCalledOnce()
    expect(apiMocks.getLayerLegend).toHaveBeenCalledOnce()

    await user.click(screen.getByRole('button', { name: '8天' }))

    expect(screen.getByText('首期动态图例')).toBeInTheDocument()
    expect(screen.getAllByText('2025年01月01日').length).toBeGreaterThan(0)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(apiMocks.getLayerTimes).toHaveBeenCalledOnce()
    expect(apiMocks.getLayerLegend).toHaveBeenCalledOnce()
  })

  it('loads the dynamic legend for the initial SSM time', async () => {
    render(<App />)

    expect(await screen.findByText('首期动态图例')).toBeInTheDocument()
    expect(apiMocks.getLayerLegend).toHaveBeenCalledWith('ssm', '2025-01-01')
    expect(screen.queryByText('SSM 静态图例')).not.toBeInTheDocument()
  })

  it('clears the old dynamic legend while the next time is loading', async () => {
    const nextLegend = deferred<ReturnType<typeof legendResponse>>()
    apiMocks.getLayerLegend
      .mockResolvedValueOnce(legendResponse('2025-01-01', '旧动态图例'))
      .mockReturnValueOnce(nextLegend.promise)
    const user = userEvent.setup()

    render(<App />)
    expect(await screen.findByText('旧动态图例')).toBeInTheDocument()

    await user.click(screen.getByTitle('下一个'))

    expect(screen.queryByText('旧动态图例')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('正在加载图例...')

    await act(async () => {
      nextLegend.resolve(legendResponse('2025-01-09', '次期动态图例'))
    })
    expect(await screen.findByText('次期动态图例')).toBeInTheDocument()
  })

  it('does not let an older request replace the final selected legend', async () => {
    const olderLegend = deferred<ReturnType<typeof legendResponse>>()
    const finalLegend = deferred<ReturnType<typeof legendResponse>>()
    apiMocks.getLayerLegend
      .mockResolvedValueOnce(legendResponse('2025-01-01', '首期动态图例'))
      .mockReturnValueOnce(olderLegend.promise)
      .mockReturnValueOnce(finalLegend.promise)
    const user = userEvent.setup()

    render(<App />)
    expect(await screen.findByText('首期动态图例')).toBeInTheDocument()
    await user.click(screen.getByTitle('下一个'))
    await user.click(screen.getByTitle('下一个'))

    await act(async () => {
      finalLegend.resolve(legendResponse('2025-01-17', '最终动态图例'))
    })
    expect(await screen.findByText('最终动态图例')).toBeInTheDocument()

    await act(async () => {
      olderLegend.resolve(legendResponse('2025-01-09', '过期动态图例'))
    })
    expect(screen.getByText('最终动态图例')).toBeInTheDocument()
    expect(screen.queryByText('过期动态图例')).not.toBeInTheDocument()
  })

  it('shows an unavailable state when the dynamic legend request fails', async () => {
    apiMocks.getLayerLegend.mockRejectedValue(new Error('legend unavailable'))

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('图例暂不可用')
    expect(screen.queryByText('首期动态图例')).not.toBeInTheDocument()
    expect(screen.queryByText('SSM 静态图例')).not.toBeInTheDocument()
  })

  it('uses the static legend without requesting dynamic data for non-SSM layers', async () => {
    const user = userEvent.setup()
    render(<App />)
    expect(await screen.findByText('首期动态图例')).toBeInTheDocument()
    apiMocks.getLayerLegend.mockClear()

    await user.click(screen.getByRole('radio', { name: /植被指数/ }))

    expect(await screen.findByText('NDVI 静态图例')).toBeInTheDocument()
    expect(apiMocks.getLayerLegend).not.toHaveBeenCalled()
  })
})
