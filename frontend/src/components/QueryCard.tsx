import type { Layer, MapQueryState } from '../types'

interface QueryCardProps {
  state: MapQueryState
  activeLayer: Layer | null
  onClose: () => void
}

function formatFiniteNumber(value: number, fractionDigits?: number): string {
  if (!Number.isFinite(value)) return '—'
  return fractionDigits === undefined ? String(value) : value.toFixed(fractionDigits)
}

export default function QueryCard({ state, activeLayer, onClose }: QueryCardProps) {
  if (state.status === 'idle') return null

  return (
    <section className="query-card" aria-label="查询结果">
      <button
        type="button"
        className="query-card-close"
        aria-label="关闭查询结果"
        onClick={onClose}
      >
        ×
      </button>

      {state.status === 'error' ? (
        <p className="query-card-message query-card-error" role="alert">
          {state.message}
        </p>
      ) : (
        <div role="status" aria-live="polite">
          {state.status === 'loading' && (
            <p className="query-card-message">
              {state.kind === 'point' ? '正在查询点位…' : '正在统计框选区域…'}
            </p>
          )}

          {state.status === 'point' && (
            <>
              <h3>点查询结果</h3>
              <dl>
                <dt>经度</dt>
                <dd>{formatFiniteNumber(state.result.lng, 4)}</dd>
                <dt>纬度</dt>
                <dd>{formatFiniteNumber(state.result.lat, 4)}</dd>
                <dt>图层</dt>
                <dd>
                  {activeLayer?.id === state.result.layerId
                    ? activeLayer.name
                    : state.result.layerId}
                </dd>
                <dt>时间</dt>
                <dd>{state.result.time}</dd>
                <dt>数值</dt>
                <dd>
                  {Number.isFinite(state.result.value)
                    ? `${formatFiniteNumber(state.result.value, 4)} ${state.result.unit}`
                    : '—'}
                </dd>
              </dl>
            </>
          )}

          {state.status === 'area' && (
            <>
              <h3>框选区域统计</h3>
              <dl>
                <dt>平均值</dt>
                <dd>{formatFiniteNumber(state.result.mean, 4)}</dd>
                <dt>最大值</dt>
                <dd>{formatFiniteNumber(state.result.max, 4)}</dd>
                <dt>最小值</dt>
                <dd>{formatFiniteNumber(state.result.min, 4)}</dd>
                <dt>像元数</dt>
                <dd>{formatFiniteNumber(state.result.count)}</dd>
              </dl>
            </>
          )}
        </div>
      )}
    </section>
  )
}
