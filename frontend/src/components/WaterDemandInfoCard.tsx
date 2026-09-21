import { scenarioMetrics } from './waterDemandCanvas'
import type {
  WaterDemandLegendEntry,
  WaterDemandPointGrid,
  WaterDemandScenario,
} from '../types'

interface WaterDemandInfoCardProps {
  grid: WaterDemandPointGrid
  index: number
  scenario: WaterDemandScenario
  legend: WaterDemandLegendEntry[]
  onClose: () => void
}

const metrics = [
  ['生态耗水', 'ecologicalWaterConsumption'],
  ['生态需水', 'ecologicalWaterDemand'],
  ['生态补水', 'ecologicalWaterReplenishment'],
] as const

export default function WaterDemandInfoCard({
  grid,
  index,
  scenario,
  legend,
  onClose,
}: WaterDemandInfoCardProps) {
  const values = scenarioMetrics(grid, index, scenario)
  const longitude = grid.lonAxis[grid.gx[index]]
  const latitude = grid.latAxis[grid.gy[index]]
  const tier = legend.find((entry) => entry.value === grid.classes[index])

  return (
    <aside className="water-demand-info-card">
      <button
        className="water-demand-info-card-close"
        type="button"
        aria-label="关闭点位信息"
        onClick={onClose}
      >
        ×
      </button>
      <h2>点位信息</h2>
      <p className="water-demand-info-card-scenario">
        情景：{scenario === 'current' ? '当前情景' : '未来情景'}
      </p>
      {tier && (
        <p className="water-demand-info-card-tier">
          <span className="water-demand-legend-dot" style={{ backgroundColor: tier.color }} />
          补水等级：{tier.label}
        </p>
      )}
      <dl>
        {metrics.map(([label, key]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{values[key].toFixed(2)} mm</dd>
          </div>
        ))}
        <div><dt>经度</dt><dd>{longitude.toFixed(6)}</dd></div>
        <div><dt>纬度</dt><dd>{latitude.toFixed(6)}</dd></div>
      </dl>
    </aside>
  )
}
