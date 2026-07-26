import { CURRENT_SCENARIO_COLOR, FUTURE_SCENARIO_COLOR } from './reclamationCanvas'
import type { ReclamationScenario } from '../types'

interface ReclamationLegendProps {
  scenario: ReclamationScenario
}

export default function ReclamationLegend({ scenario }: ReclamationLegendProps) {
  const color = scenario === 'current' ? CURRENT_SCENARIO_COLOR : FUTURE_SCENARIO_COLOR

  return (
    <aside className="reclamation-legend" aria-label="复耕潜力图例">
      <h3>复耕潜力</h3>
      <p className="reclamation-legend-scenario">
        <span className="reclamation-legend-dot" style={{ backgroundColor: color }} />
        {scenario === 'current' ? '当前情景' : '未来情景'}
      </p>
      <ul>
        <li><span className="reclamation-legend-dot reclamation-legend-dot-hollow" />不可复耕</li>
        <li><span className="reclamation-legend-dot" style={{ backgroundColor: color }} />0-5 一般复耕区</li>
        <li><span className="reclamation-legend-dot" style={{ backgroundColor: color }} />5-10 建议复耕区</li>
        <li><span className="reclamation-legend-dot" style={{ backgroundColor: color }} />&gt;10 优先复耕区</li>
      </ul>
      <p className="reclamation-legend-scale">每个圆代表约 1 km × 1 km 范围</p>
    </aside>
  )
}
