import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

const apiMocks = vi.hoisted(() => ({
  getLayers: vi.fn(),
  getLayerTimes: vi.fn(),
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
    legend: [],
  },
]

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.getLayers.mockResolvedValue(layers)
    apiMocks.getLayerTimes.mockResolvedValue(['2025-01-01', '2025-01-09'])
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
})
