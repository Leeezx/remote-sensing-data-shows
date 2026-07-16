import type { Layer, LegendItem, LegendStatus } from '../types'

export interface LegendGroup {
  title: string
  items: LegendItem[]
  status?: LegendStatus
}

interface LegendProps {
  layer: Layer | null
  items?: LegendItem[]
  status?: LegendStatus
  groups?: LegendGroup[]
}

function LegendBody({
  items,
  status,
}: {
  items: LegendItem[]
  status: LegendStatus
}) {
  if (status === 'loading') {
    return (
      <div className="legend-status" role="status" aria-live="polite">
        正在加载图例...
      </div>
    )
  }
  if (status === 'error') {
    return (
      <div className="legend-status" role="alert">
        图例暂不可用
      </div>
    )
  }
  return (
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
  )
}

export default function Legend({
  layer,
  items = layer?.legend ?? [],
  status = 'ready',
  groups,
}: LegendProps) {
  if (!layer) return null

  return (
    <div className="legend">
      <h4>{layer.name}</h4>
      {groups && groups.length > 0 ? (
        <div className="legend-groups">
          {groups.map((group) => (
            <section className="legend-group" key={group.title}>
              <h5>{group.title}</h5>
              <LegendBody items={group.items} status={group.status ?? 'ready'} />
            </section>
          ))}
        </div>
      ) : (
        <LegendBody items={items} status={status} />
      )}
    </div>
  )
}
