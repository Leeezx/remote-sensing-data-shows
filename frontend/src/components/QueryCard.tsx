import type { Layer, MapQueryState } from '../types'

interface QueryCardProps {
  state: MapQueryState
  activeLayer: Layer | null
  onClose: () => void
}

export default function QueryCard({ state, activeLayer, onClose }: QueryCardProps) {
  if (state.status === 'idle') return null

  return (
    <section className="query-card">
      <button
        type="button"
        className="query-card-close"
        aria-label="关闭查询结果"
        onClick={onClose}
      >
        ×
      </button>

      <div role="status" aria-live="polite">
        {state.status === 'loading' && (
          <p className="query-card-message">
            {state.kind === 'point' ? '正在查询点位…' : '正在统计框选区域…'}
          </p>
        )}

        {state.status === 'error' && (
          <p className="query-card-message query-card-error">{state.message}</p>
        )}

        {state.status === 'point' && (
          <>
            <h3>点查询结果</h3>
            <dl>
              <dt>经度</dt>
              <dd>{state.result.lng}</dd>
              <dt>纬度</dt>
              <dd>{state.result.lat}</dd>
              <dt>图层</dt>
              <dd>{activeLayer?.name ?? state.result.layerId}</dd>
              <dt>时间</dt>
              <dd>{state.result.time}</dd>
              <dt>数值</dt>
              <dd>{state.result.value.toFixed(4)} {state.result.unit}</dd>
            </dl>
          </>
        )}

        {state.status === 'area' && (
          <>
            <h3>框选区域统计</h3>
            <dl>
              <dt>平均值</dt>
              <dd>{state.result.mean.toFixed(4)}</dd>
              <dt>最大值</dt>
              <dd>{state.result.max.toFixed(4)}</dd>
              <dt>最小值</dt>
              <dd>{state.result.min.toFixed(4)}</dd>
              <dt>像元数</dt>
              <dd>{state.result.count}</dd>
            </dl>
          </>
        )}
      </div>
    </section>
  )
}
