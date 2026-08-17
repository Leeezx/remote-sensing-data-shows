import {
  CURRENT_SCENARIO_COLOR,
  FUTURE_SCENARIO_COLOR,
  reclamationValueStyle,
} from './reclamationCanvas'
import type { ReclamationScenario } from '../types'

interface ReclamationLegendProps {
  scenario: ReclamationScenario
}

export default function ReclamationLegend({ scenario }: ReclamationLegendProps) {
  const color = scenario === 'current' ? CURRENT_SCENARIO_COLOR : FUTURE_SCENARIO_COLOR
  const dotStyle = (valueClass: 'general' | 'recommended' | 'priority') => ({
    backgroundColor: reclamationValueStyle(valueClass, CURRENT_SCENARIO_COLOR).fill ?? CURRENT_SCENARIO_COLOR,
  })

  return (
    <aside className="reclamation-legend" aria-label="复耕潜力图例">
      <h3>复耕潜力</h3>
      <p className="reclamation-legend-scenario">
        <span className="reclamation-legend-dot" style={{ backgroundColor: color }} />
        {scenario === 'current' ? '当前情景' : '未来情景'}
      </p>
      <ul>
        <li><span className="reclamation-legend-dot reclamation-legend-dot-hollow" />不可复耕</li>
        <li><span className="reclamation-legend-dot reclamation-legend-dot-general" style={dotStyle('general')} />0-5 一般复耕区</li>
        <li><span className="reclamation-legend-dot reclamation-legend-dot-recommended" style={dotStyle('recommended')} />5-10 建议复耕区</li>
        <li><span className="reclamation-legend-dot reclamation-legend-dot-priority" style={dotStyle('priority')} />&gt;10 优先复耕区</li>
      </ul>
    </aside>
  )
}
