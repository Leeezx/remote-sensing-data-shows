import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import QueryCard from '../components/QueryCard'
import type { Layer, MapQueryState } from '../types'

const activeLayer: Layer = {
  id: 'ndvi',
  name: '植被指数',
  description: '归一化植被指数',
  type: 'raster',
  unit: '',
  range: { min: -1, max: 1 },
  timeRange: { start: '2025-01', end: '2025-12', step: 'month' },
  tileTemplate: '/tiles/{z}/{x}/{y}',
  legend: [],
}

function renderCard(state: MapQueryState, onClose = vi.fn(), layer: Layer | null = activeLayer) {
  return {
    onClose,
    ...render(<QueryCard state={state} activeLayer={layer} onClose={onClose} />),
  }
}

describe('QueryCard', () => {
  it('renders nothing while idle', () => {
    const { container } = renderCard({ status: 'idle' })

    expect(container).toBeEmptyDOMElement()
  })

  it.each([
    ['point', '正在查询点位…'],
    ['area', '正在统计框选区域…'],
  ] as const)('shows the %s loading message', (kind, message) => {
    renderCard({ status: 'loading', kind })

    expect(screen.getByRole('status')).toHaveTextContent(message)
  })

  it('shows a point query result with formatted values and active layer name', () => {
    renderCard({
      status: 'point',
      result: {
        layerId: 'ndvi',
        time: '2025-06',
        lng: 116.3913,
        lat: 39.9075,
        value: 0.67891,
        unit: '指数',
      },
    })

    expect(screen.getByRole('heading', { name: '点位查询结果' })).toBeInTheDocument()
    expect(screen.getByText('116.3913')).toBeInTheDocument()
    expect(screen.getByText('39.9075')).toBeInTheDocument()
    expect(screen.getByText('植被指数')).toBeInTheDocument()
    expect(screen.getByText('2025-06')).toBeInTheDocument()
    expect(screen.getByText('0.6789 指数')).toBeInTheDocument()
  })

  it('falls back to the point result layer id when no active layer is available', () => {
    renderCard({
      status: 'point',
      result: {
        layerId: 'lst',
        time: '2025-06',
        lng: 1,
        lat: 2,
        value: 3,
        unit: '°C',
      },
    }, vi.fn(), null)

    expect(screen.getByText('lst')).toBeInTheDocument()
  })

  it('shows all four area statistics', () => {
    renderCard({
      status: 'area',
      result: { mean: 0.45678, max: 0.98765, min: 0.12345, count: 321 },
    })

    expect(screen.getByRole('heading', { name: '区域统计结果' })).toBeInTheDocument()
    expect(screen.getByText('0.4568')).toBeInTheDocument()
    expect(screen.getByText('0.9877')).toBeInTheDocument()
    expect(screen.getByText('0.1235')).toBeInTheDocument()
    expect(screen.getByText('321')).toBeInTheDocument()
  })

  it('shows query errors', () => {
    renderCard({ status: 'error', kind: 'area', message: '区域统计失败' })

    expect(screen.getByText('区域统计失败')).toBeInTheDocument()
  })

  it('calls onClose from the accessible close button', async () => {
    const user = userEvent.setup()
    const { onClose } = renderCard({ status: 'loading', kind: 'point' })

    await user.click(screen.getByRole('button', { name: '关闭查询结果' }))

    expect(onClose).toHaveBeenCalledOnce()
  })
})
