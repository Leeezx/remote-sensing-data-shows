import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ReclamationLegend from '../components/ReclamationLegend'

function swatchFor(label: string) {
  return screen.getByText(label).closest('li')?.querySelector('.reclamation-legend-dot')
}

describe('ReclamationLegend', () => {
  it('uses the same three class colors for current and future scenarios', () => {
    const { rerender } = render(<ReclamationLegend scenario="current" />)
    const currentStyles = ['0-5 一般复耕区', '5-10 建议复耕区', '>10 优先复耕区']
      .map((label) => swatchFor(label)?.getAttribute('style'))

    rerender(<ReclamationLegend scenario="future" />)
    const futureStyles = ['0-5 一般复耕区', '5-10 建议复耕区', '>10 优先复耕区']
      .map((label) => swatchFor(label)?.getAttribute('style'))

    expect(currentStyles).toEqual([
      'background-color: rgba(34, 197, 94, 0.4);',
      'background-color: rgba(245, 158, 11, 0.64);',
      'background-color: rgba(220, 38, 38, 0.82);',
    ])
    expect(futureStyles).toEqual(currentStyles)
  })

  it('keeps the non-reclaimable swatch hollow', () => {
    render(<ReclamationLegend scenario="current" />)

    const swatch = swatchFor('不可复耕')
    expect(swatch).toHaveClass('reclamation-legend-dot-hollow')
    expect(swatch).not.toHaveStyle({ backgroundColor: '#16A34A' })
  })
})
