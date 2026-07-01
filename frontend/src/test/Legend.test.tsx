import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Legend from '../components/Legend'
import type { Layer } from '../types'

const layer: Layer = {
  id: 'ssm',
  name: '表层土壤湿度',
  description: '土壤表层含水量',
  type: 'raster',
  unit: 'm³/m³',
  range: { min: 0, max: 0.5 },
  timeRange: { start: '2025-01', end: '2025-12', step: 'month' },
  tileTemplate: '/tiles/{z}/{x}/{y}',
  legend: [
    { value: 0.1, color: '#static', label: '静态图例' },
  ],
}

describe('Legend', () => {
  it('uses supplied dynamic items instead of the layer static legend', () => {
    render(
      <Legend
        layer={layer}
        items={[{ value: 0.2, color: '#123456', label: '动态图例' }]}
      />,
    )

    expect(screen.getByRole('heading', { name: layer.name })).toBeInTheDocument()
    expect(screen.getByText('动态图例')).toBeInTheDocument()
    expect(screen.queryByText('静态图例')).not.toBeInTheDocument()
    expect(screen.getByText('动态图例').previousElementSibling).toHaveStyle({
      backgroundColor: '#123456',
    })
  })

  it('defaults to the layer static legend', () => {
    render(<Legend layer={layer} />)

    expect(screen.getByText('静态图例')).toBeInTheDocument()
  })

  it('shows only the loading state beneath the heading', () => {
    render(<Legend layer={layer} status="loading" />)

    expect(screen.getByRole('heading', { name: layer.name })).toBeInTheDocument()
    expect(screen.getByText('正在加载图例...')).toBeInTheDocument()
    expect(screen.queryByText('静态图例')).not.toBeInTheDocument()
  })

  it('shows only the error state beneath the heading', () => {
    render(<Legend layer={layer} status="error" />)

    expect(screen.getByRole('heading', { name: layer.name })).toBeInTheDocument()
    expect(screen.getByText('图例暂不可用')).toBeInTheDocument()
    expect(screen.queryByText('静态图例')).not.toBeInTheDocument()
  })

  it('renders nothing without a layer', () => {
    const { container } = render(<Legend layer={null} />)

    expect(container).toBeEmptyDOMElement()
  })
})
