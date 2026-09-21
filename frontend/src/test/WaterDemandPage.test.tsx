import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WaterDemandPage from '../pages/WaterDemandPage'
import type {
  WaterDemandOverviewResponse,
  WaterDemandPointGrid,
  WaterDemandRegionProperties,
} from '../types'

const apiMocks = vi.hoisted(() => ({
  getWaterDemandOverview: vi.fn(),
  getWaterDemandPoints: vi.fn(),
}))

interface MapProps {
  region: WaterDemandRegionProperties
  highlighted: boolean
  grid: WaterDemandPointGrid | null
  selectedIndex: number | null
  onPointSelect: (index: number) => void
}

const mapMocks = vi.hoisted(() => ({ props: null as MapProps | null }))

vi.mock('../services/api', () => apiMocks)

vi.mock('../components/WaterDemandMap', () => ({
  default: (props: MapProps) => {
    mapMocks.props = props
    return (
      <div data-testid="water-demand-map">
        <span data-testid="highlighted">{String(props.highlighted)}</span>
        <span data-testid="loaded-grid">{props.grid ? String(props.grid.pointCount) : 'none'}</span>
        <button type="button" onClick={() => props.onPointSelect(1)}>选择点位</button>
        <button
          type="button"
          onClick={() => {
            if (props.grid) props.onPointSelect(0)
          }}
        >
          选择首点
        </button>
      </div>
    )
  },
}))

const region: WaterDemandRegionProperties = {
  id: 'WR-DEMO-1',
  name: '半干旱区',
  pointCount: 4,
  bounds: [[30, 100], [31, 101]],
}

const overview: WaterDemandOverviewResponse = {
  schemaVersion: 1,
  unit: 'mm',
  metrics: [
    { field: 'ecologicalWaterConsumption', label: '生态耗水', unit: 'mm' },
    { field: 'ecologicalWaterDemand', label: '生态需水', unit: 'mm' },
    { field: 'ecologicalWaterReplenishment', label: '生态补水', unit: 'mm' },
  ],
  valueFields: [],
  legend: [
    { value: 1, color: '#F08A85', label: '立即补水' },
    { value: 2, color: '#F2C744', label: '优先补水' },
    { value: 3, color: '#7BC47F', label: '观察复核' },
  ],
  chinaOutline: { type: 'Polygon', coordinates: [] },
  regions: {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      properties: region,
      geometry: { type: 'Polygon', coordinates: [] },
    }],
  },
}

/** 4 points, row-major, with hand-picked quantisation ranges. */
function makeGrid(): WaterDemandPointGrid {
  const minimums = new Float64Array([0, 10, 20, 30, 40, 50])
  const maximums = new Float64Array([1000, 1010, 1020, 1030, 1040, 1050])
  const fractions = [
    [0, 0, 0, 0, 0, 0],
    [0.25, 0.25, 0.25, 0.25, 0.25, 0.25],
    [0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
    [1, 1, 1, 1, 1, 1],
  ]
  const values = new Uint16Array(6 * fractions.length)
  for (let point = 0; point < fractions.length; point += 1) {
    for (let metric = 0; metric < 6; metric += 1) {
      values[metric * fractions.length + point] = Math.round(fractions[point][metric] * 65535)
    }
  }
  return {
    pointCount: 4,
    lonAxis: new Float64Array([100, 100.01]),
    latAxis: new Float64Array([30, 30.01]),
    gx: Uint16Array.from([0, 1, 0, 1]),
    gy: Uint16Array.from([0, 0, 1, 1]),
    values,
    classes: Uint8Array.from([1, 2, 3, 1]),
    minimums,
    maximums,
  }
}

/** Longest setTimeout delay: auto-drill never fires within a test run. */
const AUTO_DRILL_NEVER = 2_147_483_647

describe('WaterDemandPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mapMocks.props = null
    apiMocks.getWaterDemandOverview.mockResolvedValue(overview)
    apiMocks.getWaterDemandPoints.mockResolvedValue(makeGrid())
  })

  it('highlights the demo region and defers point loading until the delay elapses', async () => {
    render(<WaterDemandPage autoDrillDelayMs={AUTO_DRILL_NEVER} />)

    expect(await screen.findByRole('heading', { name: '需水补水计算与评估' })).toBeInTheDocument()
    expect(screen.getByTestId('highlighted')).toHaveTextContent('true')
    expect(screen.getByText('正在定位示范区...')).toBeInTheDocument()
    // Only the overview is fetched while the national view is showing.
    expect(apiMocks.getWaterDemandOverview).toHaveBeenCalledTimes(1)
    expect(apiMocks.getWaterDemandPoints).not.toHaveBeenCalled()
  })

  it('drills into the demo region automatically and then loads the points', async () => {
    render(<WaterDemandPage autoDrillDelayMs={0} />)

    // Drill-in and the point request both settle asynchronously; await each.
    expect(await screen.findByRole('button', { name: '返回全国' })).toBeInTheDocument()
    expect(await screen.findByTestId('loaded-grid')).toHaveTextContent('4')
    expect(apiMocks.getWaterDemandPoints).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('highlighted')).toHaveTextContent('false')
  })

  it('lets the visitor skip the wait with the explicit entry button', async () => {
    const user = userEvent.setup()
    render(<WaterDemandPage autoDrillDelayMs={AUTO_DRILL_NEVER} />)
    await screen.findByText('正在定位示范区...')

    await user.click(screen.getByRole('button', { name: '立即进入示范区域' }))

    expect(await screen.findByRole('button', { name: '返回全国' })).toBeInTheDocument()
    expect(apiMocks.getWaterDemandPoints).toHaveBeenCalledTimes(1)
  })

  it('shows the three metric labels once the region is open', async () => {
    render(<WaterDemandPage autoDrillDelayMs={0} />)
    await screen.findByRole('button', { name: '返回全国' })

    expect(screen.getByRole('button', { name: '当前情景' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('立即补水')).toBeInTheDocument()
    expect(screen.getByText('优先补水')).toBeInTheDocument()
    expect(screen.getByText('观察复核')).toBeInTheDocument()
  })

  it('opens the info card with mm metrics and scenario-specific values', async () => {
    const user = userEvent.setup()
    render(<WaterDemandPage autoDrillDelayMs={0} />)
    await screen.findByRole('button', { name: '返回全国' })

    await user.click(screen.getByRole('button', { name: '选择点位' }))

    expect(screen.getByRole('heading', { name: '点位信息' })).toBeInTheDocument()
    expect(screen.getByText('情景：当前情景')).toBeInTheDocument()
    // point 1, current scenario: 0.25 of each column's range
    expect(screen.getByText('250.00 mm')).toBeInTheDocument()
    expect(screen.getByText('260.00 mm')).toBeInTheDocument()
    expect(screen.getByText('270.00 mm')).toBeInTheDocument()
    expect(screen.getByText('100.010000')).toBeInTheDocument()
    expect(screen.getByText('30.000000')).toBeInTheDocument()
    expect(screen.getByText('补水等级：优先补水')).toBeInTheDocument()
  })

  it('switches scenarios locally without requesting data again', async () => {
    const user = userEvent.setup()
    render(<WaterDemandPage autoDrillDelayMs={0} />)
    await screen.findByRole('button', { name: '返回全国' })
    await user.click(screen.getByRole('button', { name: '选择点位' }))

    await user.click(screen.getByRole('button', { name: '未来情景' }))

    expect(apiMocks.getWaterDemandPoints).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('heading', { name: '点位信息' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '未来情景' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('returns to the national view and stays there', async () => {
    const user = userEvent.setup()
    render(<WaterDemandPage autoDrillDelayMs={0} />)
    await screen.findByRole('button', { name: '返回全国' })

    await user.click(screen.getByRole('button', { name: '返回全国' }))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 40)) })

    expect(screen.getByText('正在定位示范区...')).toBeInTheDocument()
    expect(screen.getByTestId('highlighted')).toHaveTextContent('true')
    expect(mapMocks.props?.grid).toBeNull()
  })

  it('surfaces an overview error and retries it', async () => {
    const user = userEvent.setup()
    apiMocks.getWaterDemandOverview
      .mockRejectedValueOnce(new Error('概览失败'))
      .mockResolvedValueOnce(overview)
    // A long delay keeps the post-retry highlight state observable.
    render(<WaterDemandPage autoDrillDelayMs={AUTO_DRILL_NEVER} />)

    expect(await screen.findByText('概览失败')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重试' }))
    expect(await screen.findByText('正在定位示范区...')).toBeInTheDocument()
    expect(screen.getByTestId('highlighted')).toHaveTextContent('true')
  })

  it('surfaces a point-transport error and retries it', async () => {
    const user = userEvent.setup()
    apiMocks.getWaterDemandPoints
      .mockRejectedValueOnce(new Error('点位失败'))
      .mockResolvedValueOnce(makeGrid())
    render(<WaterDemandPage autoDrillDelayMs={0} />)

    expect(await screen.findByText('点位失败')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重试' }))
    expect(await screen.findByTestId('loaded-grid')).toHaveTextContent('4')
  })

  it('reports when the artifact declares no demo region', async () => {
    apiMocks.getWaterDemandOverview.mockResolvedValue({
      ...overview,
      regions: { type: 'FeatureCollection', features: [] },
    })
    render(<WaterDemandPage autoDrillDelayMs={0} />)

    expect(await screen.findByText('该板块暂无示范区数据')).toBeInTheDocument()
  })

  it('aborts the pending point request when the page unmounts', async () => {
    let observed: AbortSignal | undefined
    apiMocks.getWaterDemandPoints.mockImplementation((signal?: AbortSignal) => {
      observed = signal
      return new Promise(() => {})
    })
    const { unmount } = render(<WaterDemandPage autoDrillDelayMs={0} />)
    await screen.findByText('加载区域点位...')

    unmount()

    expect(observed?.aborted).toBe(true)
  })
})
