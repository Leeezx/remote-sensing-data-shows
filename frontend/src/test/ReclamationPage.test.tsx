import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReclamationPage from '../pages/ReclamationPage'
import type {
  ReclamationOverviewWireResponse,
  ReclamationPoint,
  ReclamationPointsResponse,
  ReclamationRegionProperties,
} from '../types'

const apiMocks = vi.hoisted(() => ({
  getReclamationOverview: vi.fn(),
  getReclamationPoints: vi.fn(),
}))

const mapMocks = vi.hoisted(() => ({
  props: null as {
    selectedRegion: ReclamationRegionProperties | null
    points: ReclamationPoint[]
    onRegionSelect: (region: ReclamationRegionProperties) => void
    onPointSelect: (point: ReclamationPoint) => void
  } | null,
}))

vi.mock('../services/api', () => apiMocks)

vi.mock('../components/ReclamationMap', () => ({
  default: (props: typeof mapMocks.props extends infer T ? NonNullable<T> : never) => {
    mapMocks.props = props
    const point = props.points[0]
    return (
      <div data-testid="reclamation-map">
        <button type="button" onClick={() => props.onRegionSelect(regionA)}>选择区域A</button>
        <button type="button" onClick={() => props.onRegionSelect(regionB)}>选择区域B</button>
        <button type="button" disabled={!point} onClick={() => point && props.onPointSelect(point)}>选择点位</button>
        <button type="button" onClick={() => props.onPointSelect(nonReclaimablePoint)}>选择不可复耕点</button>
        <span>{props.selectedRegion?.name ?? '全国'}</span>
        <span data-testid="loaded-point">{point?.id ?? 'none'}</span>
      </div>
    )
  },
}))

const regionA: ReclamationRegionProperties = {
  id: 'A',
  name: '区域A',
  pointCount: 1,
  bounds: [[30, 100], [31, 101]],
}

const regionB: ReclamationRegionProperties = {
  id: 'B',
  name: '区域B',
  pointCount: 1,
  bounds: [[32, 102], [33, 103]],
}

const reclaimablePoint: ReclamationPoint = {
  id: 'A:0',
  longitude: 100.1234567,
  latitude: 30.7654321,
  current: {
    reclamationValue: 1,
    waterConsumption: 2.345,
    yieldValue: 3.456,
    soilCarbonValue: 4.567,
  },
  future: {
    reclamationValue: 12.345,
    waterConsumption: 5.678,
    yieldValue: 6.789,
    soilCarbonValue: 7.891,
  },
}

const nonReclaimablePoint: ReclamationPoint = {
  ...reclaimablePoint,
  id: 'A:non-reclaimable',
  current: {
    reclamationValue: -999,
    waterConsumption: -999,
    yieldValue: -999,
    soilCarbonValue: -999,
  },
}

const overview: ReclamationOverviewWireResponse = {
  schemaVersion: 1,
  unit: 'thousand_usd',
  chinaOutline: { type: 'Polygon', coordinates: [] },
  metrics: [],
  regions: {
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', properties: regionA, geometry: { type: 'Polygon', coordinates: [] } },
      { type: 'Feature', properties: regionB, geometry: { type: 'Polygon', coordinates: [] } },
    ],
  },
}

function pointsFor(region: ReclamationRegionProperties): ReclamationPointsResponse {
  return {
    schemaVersion: 1,
    region: { id: region.id, name: region.name },
    unit: 'thousand_usd',
    fields: [],
    points: [{ ...reclaimablePoint, id: `${region.id}:0` }],
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

async function selectRegion(name: 'A' | 'B') {
  await userEvent.setup().click(screen.getByRole('button', { name: `选择区域${name}` }))
}

async function backAndSelectRegion(name: 'A' | 'B') {
  await userEvent.setup().click(screen.getByRole('button', { name: '返回全国' }))
  await selectRegion(name)
}

async function renderLoadedRegionAndSelectPoint() {
  const user = userEvent.setup()
  render(<ReclamationPage />)
  await screen.findByText('点击高亮区域查看复耕潜力')
  expect(screen.getByRole('heading', { name: '复耕潜力评估' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '选择区域A' }))
  await screen.findByRole('button', { name: '返回全国' })
  await user.click(screen.getByRole('button', { name: '选择点位' }))
  return user
}

describe('ReclamationPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mapMocks.props = null
    apiMocks.getReclamationOverview.mockResolvedValue(overview)
    apiMocks.getReclamationPoints.mockImplementation((id: string) => (
      Promise.resolve(pointsFor(id === 'A' ? regionA : regionB))
    ))
  })

  it('loads only the overview and defaults to current after a region click', async () => {
    const user = userEvent.setup()
    render(<ReclamationPage />)
    expect(await screen.findByText('点击高亮区域查看复耕潜力')).toBeInTheDocument()
    expect(apiMocks.getReclamationPoints).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: '选择区域A' }))
    expect(apiMocks.getReclamationPoints).toHaveBeenCalledWith('A', expect.any(AbortSignal))
    expect(await screen.findByRole('button', { name: '当前情景' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('lets keyboard users select an overview region from the region selector', async () => {
    const user = userEvent.setup()
    render(<ReclamationPage />)
    await screen.findByText('点击高亮区域查看复耕潜力')

    const regionButton = screen.getByRole('button', { name: '选择区域：区域A' })
    regionButton.focus()
    await user.keyboard('{Enter}')

    expect(apiMocks.getReclamationPoints).toHaveBeenCalledWith('A', expect.any(AbortSignal))
    expect(await screen.findByRole('button', { name: '返回全国' })).toBeInTheDocument()
  })

  it('switches scenarios locally and closes the old point card', async () => {
    const user = await renderLoadedRegionAndSelectPoint()
    expect(screen.getByText('1.00 千美元')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '未来情景' }))

    expect(apiMocks.getReclamationPoints).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('heading', { name: '点位信息' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '未来情景' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('aborts stale region requests and reuses successful cached regions', async () => {
    const first = deferred<ReclamationPointsResponse>()
    const second = deferred<ReclamationPointsResponse>()
    const observedSignals = new Map<string, AbortSignal | undefined>()
    apiMocks.getReclamationPoints.mockImplementation((id: string, signal?: AbortSignal) => {
      observedSignals.set(id, signal)
      return id === 'A' ? first.promise : second.promise
    })
    render(<ReclamationPage />)
    await screen.findByText('点击高亮区域查看复耕潜力')
    await selectRegion('A')
    await selectRegion('B')
    expect(observedSignals.get('A')?.aborted).toBe(true)
    await act(async () => {
      second.resolve(pointsFor(regionB))
      first.resolve(pointsFor(regionA))
    })
    expect(await screen.findByRole('button', { name: '返回全国' })).toBeInTheDocument()
    expect(screen.getByTestId('loaded-point')).toHaveTextContent('B:0')

    await backAndSelectRegion('B')
    expect(apiMocks.getReclamationPoints).toHaveBeenCalledTimes(2)
  })

  it('aborts a pending point request when the page unmounts', async () => {
    const pending = deferred<ReclamationPointsResponse>()
    let observedSignal: AbortSignal | undefined
    apiMocks.getReclamationPoints.mockImplementation((_id: string, signal?: AbortSignal) => {
      observedSignal = signal
      return pending.promise
    })
    const { unmount } = render(<ReclamationPage />)
    await screen.findByText('点击高亮区域查看复耕潜力')
    await selectRegion('A')

    unmount()

    expect(observedSignal?.aborted).toBe(true)
  })

  it('retries the overview after an error', async () => {
    const user = userEvent.setup()
    apiMocks.getReclamationOverview
      .mockRejectedValueOnce(new Error('概览失败'))
      .mockResolvedValueOnce(overview)
    render(<ReclamationPage />)
    expect(await screen.findByText('概览失败')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重试' }))
    expect(await screen.findByText('点击高亮区域查看复耕潜力')).toBeInTheDocument()
  })

  it('retries points while retaining the selected region border', async () => {
    const user = userEvent.setup()
    apiMocks.getReclamationPoints
      .mockRejectedValueOnce(new Error('点位失败'))
      .mockResolvedValueOnce(pointsFor(regionA))
    render(<ReclamationPage />)
    await screen.findByText('点击高亮区域查看复耕潜力')
    await user.click(screen.getByRole('button', { name: '选择区域A' }))
    expect(await screen.findByText('点位失败')).toBeInTheDocument()
    expect(mapMocks.props?.selectedRegion).toEqual(regionA)
    await user.click(screen.getByRole('button', { name: '重试' }))
    expect(await screen.findByRole('button', { name: '选择点位' })).toBeEnabled()
  })

  it('does not open a card for a non-reclaimable point', async () => {
    const user = await renderLoadedRegionAndSelectPoint()
    await user.click(screen.getByRole('button', { name: '关闭点位信息' }))
    await user.click(screen.getByRole('button', { name: '选择不可复耕点' }))
    expect(screen.queryByRole('heading', { name: '点位信息' })).not.toBeInTheDocument()
  })

  it('lets keyboard users choose a valid point and excludes non-reclaimable points', async () => {
    const user = userEvent.setup()
    render(<ReclamationPage />)
    await screen.findByText('点击高亮区域查看复耕潜力')
    await user.click(screen.getByRole('button', { name: '选择区域A' }))

    const pointSelector = await screen.findByRole('combobox', { name: '选择可复耕点位' })
    expect(screen.getByRole('option', { name: /A:0/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /A:non-reclaimable/ })).not.toBeInTheDocument()

    pointSelector.focus()
    await user.keyboard('{ArrowDown}')

    expect(await screen.findByRole('heading', { name: '点位信息' })).toBeInTheDocument()
  })

  it('formats point metrics and coordinates, exposes scale legend text, and returns to overview', async () => {
    const user = await renderLoadedRegionAndSelectPoint()
    expect(screen.getByText('2.35 千美元')).toBeInTheDocument()
    expect(screen.getByText('100.123457')).toBeInTheDocument()
    expect(screen.getByText('30.765432')).toBeInTheDocument()
    expect(screen.getByText('不可复耕')).toBeInTheDocument()
    expect(screen.getByText('0-5 一般复耕区')).toBeInTheDocument()
    expect(screen.getByText('5-10 建议复耕区')).toBeInTheDocument()
    expect(screen.getByText('>10 优先复耕区')).toBeInTheDocument()
    expect(screen.getByText('每个圆代表约 1 km × 1 km 范围')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '返回全国' }))
    expect(await screen.findByText('点击高亮区域查看复耕潜力')).toBeInTheDocument()
    expect(mapMocks.props?.selectedRegion).toBeNull()
  })
})
