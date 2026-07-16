import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type {
  IrrigationRegion,
  IrrigationRegionAveragesResponse,
  IrrigationSeriesPeriod,
  IrrigationVectorGeoJSON,
} from '../types'

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
  getIrrigationRegionAverages: vi.fn(),
}))

const mapViewMocks = vi.hoisted(() => ({
  props: null as Record<string, unknown> | null,
}))

vi.mock('../services/api', () => ({
  ...apiMocks,
  queryPoint: vi.fn(),
  queryArea: vi.fn(),
  getExportCsvUrl: vi.fn(() => '/api/export/csv'),
  login: vi.fn(),
  getIrrigationRegionAverages: apiMocks.getIrrigationRegionAverages,
}))

vi.mock('../components/MapView', () => ({
  default: (props: {
    onRegionSelect?: (region: { id: string; name: string }) => void
    onDetailRegionSelect?: (region: { id: string; name: string }) => void
    regionVector?: IrrigationVectorGeoJSON | null
    detailRegionVector?: IrrigationVectorGeoJSON | null
    detailSelectedRegionId?: string | null
    regionLevel?: string | null
    disableQuery?: boolean
    hideRaster?: boolean
    regionColorMap?: Map<string, string> | null
  }) => {
    mapViewMocks.props = props
    return (
      <div data-testid="map-view">
        地图
        <span data-testid="query-disabled">{String(Boolean(props.disableQuery))}</span>
        <span data-testid="raster-hidden">{String(Boolean(props.hideRaster))}</span>
        <span data-testid="county-layer">{props.regionVector ? 'loaded' : 'empty'}</span>
        <span data-testid="township-layer">{props.detailRegionVector ? 'loaded' : 'empty'}</span>
        <span data-testid="detail-first-id">{props.detailRegionVector?.features[0]?.properties?.id ?? 'none'}</span>
        <span data-testid="map-region-level">{props.regionLevel ?? 'none'}</span>
        <button
          type="button"
          onClick={() => props.onRegionSelect?.({ id: 'county_a', name: '示范县A' })}
        >
          选择示范县A
        </button>
        <button
          type="button"
          onClick={() => props.onRegionSelect?.({ id: 'county_b', name: '示范县B' })}
        >
          选择示范县B
        </button>
        <button
          type="button"
          onClick={() => props.onDetailRegionSelect?.({ id: 'township_a1', name: '示范镇A1' })}
        >
          选择示范镇A1
        </button>
      </div>
    )
  },
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

const etLayer = {
  id: 'et',
  name: '蒸散发',
  description: '8天蒸散发',
  type: 'evapotranspiration',
  unit: 'mm/8天',
  range: { min: 0, max: 120 },
  timeRange: { start: '2025-01-01', end: '2025-01-09', step: '8day' },
  tileTemplate: '/tiles/et/{time}/{z}/{x}/{y}.png',
  legend: [{ value: 0, color: '#d53e4f', label: 'ET 静态图例' }],
}

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

const townshipRegions: IrrigationRegion[] = [
  { id: 'township_a1', name: '示范镇A1', level: 'township' as const, parentId: 'county_a' },
]

function vectorFixture(
  level: 'county' | 'township',
  countyId?: string,
): IrrigationVectorGeoJSON {
  const isCountyB = countyId === 'county_b'
  const id = level === 'county' ? 'county_a' : isCountyB ? 'township_b1' : 'township_a1'
  const name = level === 'county' ? '示范县A' : isCountyB ? '示范镇B1' : '示范镇A1'
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      properties: {
        id,
        name,
        ...(level === 'township' ? { parentId: countyId ?? 'county_a' } : {}),
      },
      geometry: {
        type: 'Polygon',
        coordinates: [[[100, 30], [101, 30], [101, 31], [100, 30]]],
      },
    }],
  }
}

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
    mapViewMocks.props = null
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
    apiMocks.getIrrigationRegions.mockImplementation((level: 'county' | 'township') => (
      Promise.resolve(level === 'county' ? countyRegions : townshipRegions)
    ))
    apiMocks.getIrrigationSeries.mockImplementation(
      (level: 'county' | 'township', _regionId: string, period: 'annual' | 'monthly') => (
        Promise.resolve(irrigationSeries(
          level === 'county' ? countyRegions[0] : townshipRegions[0],
          period,
        ))
      ),
    )
    apiMocks.getIrrigationVectorStatus.mockImplementation((level: 'county' | 'township') => (
      Promise.resolve(level === 'county'
        ? {
            level: 'county',
            available: true,
            url: '/api/irrigation/vectors/county',
            message: '县级行政区矢量可用',
          }
        : {
            level: 'township',
            available: true,
            url: '/api/irrigation/vectors/township?countyId={countyId}',
            message: '请先在地图上选择县域，再加载该县乡镇',
          })
    ))
    apiMocks.getIrrigationVectorGeoJSON.mockImplementation(
      (level: 'county' | 'township', countyId?: string) => Promise.resolve(vectorFixture(level, countyId)),
    )
    apiMocks.getIrrigationRegionAverages.mockImplementation(
      (level: 'county' | 'township') => Promise.resolve({
        level,
        unit: '万m³',
        averages: level === 'county'
          ? [
              { regionId: 'county_a', name: '示范县A', average: 1480.5 },
              { regionId: 'county_b', name: '示范县B', average: 320.0 },
            ]
          : [{ regionId: 'township_a1', name: '示范镇A1', average: 118.5 }],
        legend: [
          { value: 100, color: '#eff3ff', label: '100 万m³' },
          { value: 400, color: '#bdd7e7', label: '400 万m³' },
          { value: 700, color: '#6baed6', label: '700 万m³' },
          { value: 1000, color: '#3182bd', label: '1000 万m³' },
          { value: 1300, color: '#08519c', label: '1300 万m³' },
          { value: 1600, color: '#042d60', label: '1600 万m³' },
        ],
      }),
    )
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
    await waitFor(() => expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded'))
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

  it('reuses the mounted county layer when switching from county to township statistics', async () => {
    window.history.pushState({}, '', '/irrigation')
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '县级统计' }))
    await waitFor(() => expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded'))
    const vectorCalls = apiMocks.getIrrigationVectorGeoJSON.mock.calls
      .filter(([level]) => level === 'county').length
    const averageCalls = apiMocks.getIrrigationRegionAverages.mock.calls
      .filter(([level]) => level === 'county').length

    await user.click(screen.getByRole('button', { name: '乡镇级统计' }))

    expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
    expect(apiMocks.getIrrigationVectorGeoJSON.mock.calls.filter(([level]) => level === 'county'))
      .toHaveLength(vectorCalls)
    expect(apiMocks.getIrrigationRegionAverages.mock.calls.filter(([level]) => level === 'county'))
      .toHaveLength(averageCalls)
  })

  it('loads townships only after selecting a county and then selects a township', async () => {
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

    await user.click(screen.getByRole('button', { name: '乡镇级统计' }))

    expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
    expect(screen.getByTestId('township-layer')).toHaveTextContent('empty')
    expect(apiMocks.getIrrigationRegionAverages).toHaveBeenCalledWith('county')

    await waitFor(() => {
      expect(apiMocks.getIrrigationVectorStatus).toHaveBeenCalledWith('township')
    })
    await waitFor(() => {
      expect(apiMocks.getIrrigationVectorGeoJSON).toHaveBeenCalledWith('county', undefined)
    })
    expect(apiMocks.getIrrigationVectorGeoJSON).not.toHaveBeenCalledWith('township', undefined)
    expect(apiMocks.getIrrigationRegionAverages).not.toHaveBeenCalledWith('township')
    expect(screen.getByTestId('map-region-level')).toHaveTextContent('county')

    await user.click(screen.getByRole('button', { name: '选择示范县A' }))

    await waitFor(() => {
      expect(apiMocks.getIrrigationVectorGeoJSON).toHaveBeenCalledWith('township', 'county_a')
      expect(apiMocks.getIrrigationRegionAverages).toHaveBeenCalledWith('township', 'county_a')
    })
    expect(await screen.findByText('已加载示范县A 1 个乡镇')).toBeInTheDocument()
    expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
    expect(screen.getByTestId('township-layer')).toHaveTextContent('loaded')
    expect(screen.getByRole('heading', { name: '县级年平均' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '当前县乡镇年平均' })).toBeInTheDocument()
    expect(screen.getByTestId('map-region-level')).toHaveTextContent('county')
    expect(screen.getByRole('button', { name: '返回县级选择' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '选择示范镇A1' }))

    await waitFor(() => {
      expect(apiMocks.getIrrigationSeries).toHaveBeenCalledWith(
        'township',
        'township_a1',
        'monthly',
      )
      expect(apiMocks.getIrrigationSeries).toHaveBeenCalledWith(
        'township',
        'township_a1',
        'annual',
      )
    })
    expect(screen.getByRole('img', { name: '示范镇A1 月度灌溉用水量折线图' })).toBeInTheDocument()
  })

  it('keeps township layers visible when JSON statistics are unavailable', async () => {
    window.history.pushState({}, '', '/irrigation')
    apiMocks.getIrrigationSeries.mockRejectedValueOnce({ response: { status: 404 } })
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '乡镇级统计' }))
    await user.click(screen.getByRole('button', { name: '选择示范县A' }))
    await screen.findByText('已加载示范县A 1 个乡镇')
    await user.click(screen.getByRole('button', { name: '选择示范镇A1' }))

    expect(await screen.findByText('暂无统计数据')).toBeInTheDocument()
    expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
    expect(screen.getByTestId('township-layer')).toHaveTextContent('loaded')
  })

  it('keeps counties visible while switching the township detail to another county', async () => {
    window.history.pushState({}, '', '/irrigation')
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '乡镇级统计' }))
    await user.click(await screen.findByRole('button', { name: '选择示范县A' }))
    await screen.findByText('已加载示范县A 1 个乡镇')

    await user.click(screen.getByRole('button', { name: '选择示范县B' }))
    expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
    expect(screen.getByTestId('township-layer')).toHaveTextContent('loaded')

    await waitFor(() => {
      expect(apiMocks.getIrrigationVectorGeoJSON).toHaveBeenCalledWith('township', 'county_b')
    })
    expect(await screen.findByText('已加载示范县B 1 个乡镇')).toBeInTheDocument()
    expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
  })

  it('ignores a stale township response after a newer county finishes first', async () => {
    window.history.pushState({}, '', '/irrigation')
    const countyAChunk = deferred<IrrigationVectorGeoJSON>()
    const countyBChunk = deferred<IrrigationVectorGeoJSON>()
    apiMocks.getIrrigationVectorGeoJSON.mockImplementation(
      (level: 'county' | 'township', countyId?: string) => {
        if (level === 'township' && countyId === 'county_a') return countyAChunk.promise
        if (level === 'township' && countyId === 'county_b') return countyBChunk.promise
        return Promise.resolve(vectorFixture(level, countyId))
      },
    )
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '乡镇级统计' }))
    await screen.findByText('请在地图上点击一个县域')
    await user.click(screen.getByRole('button', { name: '选择示范县A' }))
    await user.click(screen.getByRole('button', { name: '选择示范县B' }))

    countyBChunk.resolve(vectorFixture('township', 'county_b'))
    expect(await screen.findByText('已加载示范县B 1 个乡镇')).toBeInTheDocument()

    countyAChunk.resolve(vectorFixture('township', 'county_a'))
    await waitFor(() => {
      expect(screen.getByTestId('detail-first-id')).toHaveTextContent('township_b1')
    })
    expect(screen.queryByText(/已加载示范县A/)).not.toBeInTheDocument()
  })

  it('keeps the previous township layer when a new county chunk fails', async () => {
    window.history.pushState({}, '', '/irrigation')
    apiMocks.getIrrigationVectorGeoJSON.mockImplementation(
      (level: 'county' | 'township', countyId?: string) => {
        if (level === 'township' && countyId === 'county_b') {
          return Promise.reject(new Error('县B分片不可用'))
        }
        return Promise.resolve(vectorFixture(level, countyId))
      },
    )
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '乡镇级统计' }))
    await user.click(await screen.findByRole('button', { name: '选择示范县A' }))
    await screen.findByText('已加载示范县A 1 个乡镇')
    await user.click(screen.getByRole('button', { name: '选择示范县B' }))

    expect(await screen.findByText('县B分片不可用')).toBeInTheDocument()
    expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
    expect(screen.getByTestId('detail-first-id')).toHaveTextContent('township_a1')
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

  it('loads a per-time dynamic legend for ET', async () => {
    apiMocks.getLayers.mockResolvedValue([...layers, etLayer])
    apiMocks.getLayerLegend.mockImplementation((layerId: string) => Promise.resolve(
      layerId === 'et'
        ? {
            layerId: 'et',
            time: '2025-01-01',
            unit: 'mm/8天',
            legend: [{ value: 12.3, color: '#d53e4f', label: 'ET 动态图例' }],
          }
        : legendResponse('2025-01-01', '首期动态图例'),
    ))
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('首期动态图例')

    await user.click(screen.getByRole('radio', { name: /蒸散发/ }))

    expect(await screen.findByText('ET 动态图例')).toBeInTheDocument()
    expect(apiMocks.getLayerLegend).toHaveBeenCalledWith('et', '2025-01-01')
    expect(screen.queryByText('ET 静态图例')).not.toBeInTheDocument()
  })

  it('shows admin stats controls when county statistics is enabled', async () => {
    window.history.pushState({}, '', '/irrigation')
    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('县级统计')).toBeInTheDocument()
    })
    // Click admin stats button
    const countyBtn = screen.getByText('县级统计')
    await userEvent.click(countyBtn)
    // After click, averages should have been requested
    await waitFor(() => {
      expect(apiMocks.getIrrigationRegionAverages).toHaveBeenCalledWith('county')
    })
    // Click again to disable
    await userEvent.click(countyBtn)
    // Should restore to initial state
    await waitFor(() => {
      expect(screen.getAllByText('未开启行政区统计').length).toBeGreaterThan(0)
    })
  })

  it('disables raster queries immediately while county averages are still loading', async () => {
    window.history.pushState({}, '', '/irrigation')
    const averages = deferred<IrrigationRegionAveragesResponse>()
    apiMocks.getIrrigationRegionAverages.mockReturnValueOnce(averages.promise)
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '县级统计' }))

    expect(screen.getByTestId('query-disabled')).toHaveTextContent('true')
    expect(screen.getByTestId('raster-hidden')).toHaveTextContent('true')
    expect(screen.getByRole('button', { name: '年度' })).toBeDisabled()
  })

  it('keeps county statistics mode active and colors counties after averages arrive', async () => {
    window.history.pushState({}, '', '/irrigation')
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '县级统计' }))
    await waitFor(() => expect(apiMocks.getIrrigationRegionAverages).toHaveBeenCalledWith('county'))
    await waitFor(() => {
      const colorMap = mapViewMocks.props?.regionColorMap as Map<string, string> | null
      expect(colorMap?.has('county_a')).toBe(true)
      expect(colorMap?.has('county_b')).toBe(true)
    })
    expect(screen.getByRole('heading', { name: '县级年平均' })).toBeInTheDocument()
  })

  it('keeps raster queries disabled when county averages fail', async () => {
    window.history.pushState({}, '', '/irrigation')
    apiMocks.getIrrigationRegionAverages.mockRejectedValueOnce(new Error('averages unavailable'))
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '县级统计' }))
    await waitFor(() => expect(apiMocks.getIrrigationRegionAverages).toHaveBeenCalledWith('county'))

    expect(screen.getByTestId('query-disabled')).toHaveTextContent('true')
    expect(screen.getByTestId('raster-hidden')).toHaveTextContent('true')
    expect(screen.getByRole('alert')).toHaveTextContent('图例暂不可用')
  })
})
