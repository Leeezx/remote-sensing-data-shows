import type { WaterDemandLegendEntry } from '../types'

interface WaterDemandLegendProps {
  entries: WaterDemandLegendEntry[]
}

export default function WaterDemandLegend({ entries }: WaterDemandLegendProps) {
  return (
    <aside className="water-demand-legend" aria-label="补水等级图例">
      <h3>补水等级</h3>
      <ul>
        {entries.map((entry) => (
          <li key={entry.value}>
            <span className="water-demand-legend-dot" style={{ backgroundColor: entry.color }} />
            {entry.label}
          </li>
        ))}
      </ul>
    </aside>
  )
}
