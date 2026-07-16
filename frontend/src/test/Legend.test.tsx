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
    expect(screen.getByRole('status')).toHaveTextContent('正在加载图例...')
    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite')
    expect(screen.queryByText('静态图例')).not.toBeInTheDocument()
  })

  it('shows only the error state beneath the heading', () => {
    render(<Legend layer={layer} status="error" />)

    expect(screen.getByRole('heading', { name: layer.name })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('图例暂不可用')
    expect(screen.queryByText('静态图例')).not.toBeInTheDocument()
  })

  it('renders separately titled county and township legend groups', () => {
    render(
      <Legend
        layer={layer}
        groups={[
          {
            title: '县级年平均',
            items: [{ value: 100, color: '#111111', label: '县级 100' }],
            status: 'ready',
          },
          {
            title: '当前县乡镇年平均',
            items: [{ value: 10, color: '#222222', label: '乡镇 10' }],
            status: 'ready',
          },
        ]}
      />,
    )

    expect(screen.getByRole('heading', { name: '县级年平均' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '当前县乡镇年平均' })).toBeInTheDocument()
    expect(screen.getByText('县级 100')).toBeInTheDocument()
    expect(screen.getByText('乡镇 10')).toBeInTheDocument()
  })

  it('shows an error only inside the failed legend group', () => {
    render(
      <Legend
        layer={layer}
        groups={[
          { title: '县级年平均', items: [], status: 'error' },
          {
            title: '当前县乡镇年平均',
            items: [{ value: 10, color: '#222222', label: '乡镇 10' }],
            status: 'ready',
          },
        ]}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('图例暂不可用')
    expect(screen.getByText('乡镇 10')).toBeInTheDocument()
  })

  it('renders nothing without a layer', () => {
    const { container } = render(<Legend layer={null} />)

    expect(container).toBeEmptyDOMElement()
  })
})
