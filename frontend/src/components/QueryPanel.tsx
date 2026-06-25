import { useState } from 'react'
import type { PointQueryResult, AreaQueryResult, Layer } from '../types'
import { queryArea } from '../services/api'

interface QueryPanelProps {
  pointResult: PointQueryResult | null
  areaCoords: [number, number][] | null
  activeLayerId: string | null
  currentTime: string
  layers: Layer[]
}

export default function QueryPanel({
  pointResult,
  areaCoords,
  activeLayerId,
  currentTime,
  layers,
}: QueryPanelProps) {
  const [areaResult, setAreaResult] = useState<AreaQueryResult | null>(null)
  const [areaLoading, setAreaLoading] = useState(false)
  const [areaError, setAreaError] = useState('')

  const activeLayer = layers.find((l) => l.id === activeLayerId)

  // Run area query when coords change
  const handleQueryArea = async () => {
    if (!areaCoords || !activeLayerId) return
    setAreaLoading(true)
    setAreaError('')
    try {
      const [p1, p2] = areaCoords
      const result = await queryArea({
        layerId: activeLayerId,
        time: currentTime,
        geometry: {
          type: 'Polygon',
          coordinates: [
            [
              [p1[1], p1[0]],
              [p2[1], p1[0]],
              [p2[1], p2[0]],
              [p1[1], p2[0]],
              [p1[1], p1[0]],
            ],
          ],
        },
      })
      setAreaResult(result)
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : '区域查询失败'
      setAreaError(msg)
      setAreaResult(null)
    } finally {
      setAreaLoading(false)
    }
  }

  return (
    <div className="query-panel">
      {/* Point Query Result */}
      {pointResult && (
        <div className="query-result point-result">
          <h4>📌 点查询结果</h4>
          <table>
            <tbody>
              <tr>
                <td>坐标</td>
                <td>
                  {pointResult.lat}, {pointResult.lng}
                </td>
              </tr>
              <tr>
                <td>图层</td>
                <td>
                  {activeLayer?.name} ({pointResult.layerId})
                </td>
              </tr>
              <tr>
                <td>时间</td>
                <td>{pointResult.time}</td>
              </tr>
              <tr>
                <td>数值</td>
                <td className="value">
                  {typeof pointResult.value === 'number'
                    ? pointResult.value.toFixed(4)
                    : pointResult.value}{' '}
                  {pointResult.unit}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Area Query */}
      {areaCoords && (
        <div className="query-result area-result">
          <h4>📐 区域统计</h4>
          <button
            className="btn btn-sm btn-primary"
            onClick={handleQueryArea}
            disabled={areaLoading}
          >
            {areaLoading ? '查询中...' : '查询框选区域'}
          </button>
          {areaError && <p className="error">{areaError}</p>}
          {areaResult && (
            <table>
              <tbody>
                <tr>
                  <td>平均值</td>
                  <td className="value">{areaResult.mean.toFixed(4)}</td>
                </tr>
                <tr>
                  <td>最大值</td>
                  <td className="value">{areaResult.max.toFixed(4)}</td>
                </tr>
                <tr>
                  <td>最小值</td>
                  <td className="value">{areaResult.min.toFixed(4)}</td>
                </tr>
                <tr>
                  <td>像元数</td>
                  <td>{areaResult.count}</td>
                </tr>
              </tbody>
            </table>
          )}
        </div>
      )}

      {!pointResult && !areaCoords && (
        <p className="hint">点击地图查询点位，或按住 Shift 拖拽框选区域</p>
      )}
    </div>
  )
}
