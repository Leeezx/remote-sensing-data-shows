import type { Layer, LegendItem, LegendStatus } from '../types'

interface LegendProps {
  layer: Layer | null
  items?: LegendItem[]
  status?: LegendStatus
}

export default function Legend({
  layer,
  items = layer?.legend ?? [],
  status = 'ready',
}: LegendProps) {
  if (!layer) return null

  return (
    <div className="legend">
      <h4>{layer.name}</h4>
      {status === 'loading' ? (
        <div className="legend-status">正在加载图例...</div>
      ) : status === 'error' ? (
        <div className="legend-status">图例暂不可用</div>
      ) : (
        <div className="legend-items">
          {items.map((item) => (
            <div key={`${item.value}:${item.color}`} className="legend-item">
              <span
                className="legend-color"
                style={{ backgroundColor: item.color }}
              />
              <span className="legend-label">{item.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
