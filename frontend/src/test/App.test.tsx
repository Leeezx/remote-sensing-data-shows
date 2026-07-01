import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

const apiMocks = vi.hoisted(() => ({
  getLayers: vi.fn(),
  getLayerTimes: vi.fn(),
  getLayerLegend: vi.fn(),
  getRegions: vi.fn(),
}))

vi.mock('../services/api', () => ({
  ...apiMocks,
  queryPoint: vi.fn(),
  queryArea: vi.fn(),
  getExportCsvUrl: vi.fn(() => '/api/export/csv'),
  login: vi.fn(),
}))

vi.mock('../components/MapView', () => ({
  default: () => <div data-testid="map-view">地图</div>,
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
