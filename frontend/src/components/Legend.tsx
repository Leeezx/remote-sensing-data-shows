import type { Layer } from '../types'

interface LegendProps {
  layer: Layer | null
}

export default function Legend({ layer }: LegendProps) {
  if (!layer) return null

  return (
    <div className="legend">
      <h4>{layer.name}</h4>
      <div className="legend-items">
        {layer.legend.map((item, i) => (
          <div key={i} className="legend-item">
            <span
              className="legend-color"
              style={{ backgroundColor: item.color }}
            />
            <span className="legend-label">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
