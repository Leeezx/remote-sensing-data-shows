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
  timeResolution: 'month' | '8day'
  onTimeResolutionChange: (r: 'month' | '8day') => void
  isPlaying: boolean
  onPlayToggle: () => void
  regionId: string | null
  onRegionChange: (id: string | null) => void
}

function formatTime(t: string): string {
  // e.g. "2025-06" → "2025年06月"
  // e.g. "2010-01-01" → "2010年01月01日"
  const parts = t.split('-')
  if (parts.length === 3) {
    return `${parts[0]}年${parts[1]}月${parts[2]}日`
  }
  if (parts.length === 2) {
    return `${parts[0]}年${parts[1]}月`
  }
  return t
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
  timeResolution,
  onTimeResolutionChange,
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
        <h3>⏱️ 时间轴</h3>
        <div className="time-display">{formatTime(currentTime)}</div>
        {activeLayerId === 'ssm' && (
          <div className="resolution-toggle">
            <button
              className={`btn btn-sm ${timeResolution === '8day' ? 'btn-primary' : ''}`}
              onClick={() => onTimeResolutionChange('8day')}
            >
              8天
            </button>
            <button
              className={`btn btn-sm ${timeResolution === 'month' ? 'btn-primary' : ''}`}
              onClick={() => onTimeResolutionChange('month')}
            >
              月度
            </button>
          </div>
        )}
        <div className="timeline">
          <div className="timeline-track">
            <button
              className="timeline-prev"
              onClick={() => {
                const idx = times.indexOf(currentTime)
                if (idx > 0) onTimeChange(times[idx - 1])
              }}
              title="上一个"
            >
              ◀
            </button>
            <div className="timeline-bar-wrapper">
              <div className="timeline-bar">
                <div
                  className="timeline-filled"
                  style={{
                    width: `${(Math.max(0, times.indexOf(currentTime)) / Math.max(1, times.length - 1)) * 100}%`,
                  }}
                />
                <div
                  className="timeline-thumb"
                  style={{
                    left: `${(Math.max(0, times.indexOf(currentTime)) / Math.max(1, times.length - 1)) * 100}%`,
                  }}
                />
              </div>
              <div className="timeline-labels">
                <span className="timeline-label-start">{times.length > 0 ? formatTime(times[0]) : ''}</span>
                <span className="timeline-label-end">{times.length > 0 ? formatTime(times[times.length - 1]) : ''}</span>
              </div>
            </div>
            <button
              className="timeline-next"
              onClick={() => {
                const idx = times.indexOf(currentTime)
                if (idx < times.length - 1) onTimeChange(times[idx + 1])
              }}
              title="下一个"
            >
              ▶
            </button>
          </div>
        </div>
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
