import type { Layer, Region } from '../types'

interface SidebarProps {
  layers: Layer[]
  regions: Region[]
  activeLayerId: string | null
  onLayerChange: (id: string) => void
  opacity: number
  onOpacityChange: (v: number) => void
  currentTime: string
  times: string[]
  onTimeChange: (t: string) => void
  isPlaying: boolean
  onPlayToggle: () => void
  regionId: string | null
  onRegionChange: (id: string | null) => void
}

function formatTime(t: string): string {
  // e.g. "2025-06" → "2025年06月"
  const [y, m] = t.split('-')
  return `${y}年${m}月`
}

export default function Sidebar({
  layers,
  regions,
  activeLayerId,
  onLayerChange,
  opacity,
  onOpacityChange,
  currentTime,
  times,
  onTimeChange,
  isPlaying,
  onPlayToggle,
  regionId,
  onRegionChange,
}: SidebarProps) {
  const activeLayer = layers.find((l) => l.id === activeLayerId)

  return (
    <aside className="sidebar">
      {/* Layer Selector */}
      <section className="sidebar-section">
        <h3>📊 数据图层</h3>
        <div className="layer-list">
          {layers.map((layer) => (
            <label
              key={layer.id}
              className={`layer-item ${activeLayerId === layer.id ? 'active' : ''}`}
            >
              <input
                type="radio"
                name="layer"
                value={layer.id}
                checked={activeLayerId === layer.id}
                onChange={() => onLayerChange(layer.id)}
              />
              <span className="layer-name">{layer.name}</span>
              <span className="layer-unit">({layer.unit})</span>
            </label>
          ))}
        </div>
      </section>

      {/* Opacity */}
      <section className="sidebar-section">
        <h3>🔍 透明度</h3>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={opacity}
          onChange={(e) => onOpacityChange(Number(e.target.value))}
        />
        <span className="opacity-value">{Math.round(opacity * 100)}%</span>
      </section>

      {/* Time Control */}
      <section className="sidebar-section">
        <h3>⏱️ 时间控制</h3>
        <div className="time-display">{formatTime(currentTime)}</div>
        <input
          type="range"
          min="0"
          max={times.length - 1}
          step="1"
          value={Math.max(0, times.indexOf(currentTime))}
          onChange={(e) => onTimeChange(times[Number(e.target.value)])}
        />
        <button className={`btn btn-play ${isPlaying ? 'playing' : ''}`} onClick={onPlayToggle}>
          {isPlaying ? '⏸ 暂停' : '▶ 播放'}
        </button>
      </section>

      {/* Region Filter */}
      <section className="sidebar-section">
        <h3>📍 区域筛选</h3>
        <select
          value={regionId ?? ''}
          onChange={(e) => onRegionChange(e.target.value || null)}
        >
          <option value="">全部区域</option>
          {regions.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      </section>

      {/* Query Actions */}
      <section className="sidebar-section">
        <h3>🎯 空间查询</h3>
        <p className="hint">
          点击地图查询像元值；按住 Shift 拖拽框选区域
        </p>
      </section>

      {/* Layer Info */}
      {activeLayer && (
        <section className="sidebar-section">
          <h3>ℹ️ 图层信息</h3>
          <p className="layer-desc">{activeLayer.description}</p>
          <p className="layer-range">
            范围: {activeLayer.range.min} – {activeLayer.range.max} {activeLayer.unit}
          </p>
        </section>
      )}
    </aside>
  )
}
