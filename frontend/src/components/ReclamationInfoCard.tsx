import { scenarioMetrics } from './reclamationCanvas'
import type { ReclamationPoint, ReclamationScenario } from '../types'

interface ReclamationInfoCardProps {
  point: ReclamationPoint
  scenario: ReclamationScenario
  onClose: () => void
}

const metrics = [
  ['复耕潜力', 'reclamationValue'],
  ['用水量', 'waterConsumption'],
  ['产值', 'yieldValue'],
  ['土壤碳汇价值', 'soilCarbonValue'],
] as const

export default function ReclamationInfoCard({ point, scenario, onClose }: ReclamationInfoCardProps) {
  const values = scenarioMetrics(point, scenario)

  return (
    <aside className="reclamation-info-card">
      <button
        className="reclamation-info-card-close"
        type="button"
        aria-label="关闭点位信息"
        onClick={onClose}
      >
        ×
      </button>
      <h2>点位信息</h2>
      <p className="reclamation-info-card-scenario">情景：{scenario === 'current' ? '当前情景' : '未来情景'}</p>
      <dl>
        {metrics.map(([label, key]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{values[key].toFixed(2)} 千美元</dd>
          </div>
        ))}
        <div><dt>经度</dt><dd>{point.longitude.toFixed(6)}</dd></div>
        <div><dt>纬度</dt><dd>{point.latitude.toFixed(6)}</dd></div>
      </dl>
    </aside>
  )
}
