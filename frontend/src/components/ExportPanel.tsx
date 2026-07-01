import { useAuth } from '../contexts/AuthContext'
import { getExportCsvUrl } from '../services/api'

interface ExportPanelProps {
  activeLayerId: string | null
  startTime: string
  endTime: string
  hasData: boolean
}

export default function ExportPanel({
  activeLayerId,
  startTime,
  endTime,
  hasData,
}: ExportPanelProps) {
  const { isAuthenticated, user } = useAuth()
  const isResearcher = user?.role === 'researcher'

  if (!isAuthenticated) {
    return (
      <div className="export-panel">
        <p className="hint">登录后可导出数据</p>
      </div>
    )
  }

  if (!isResearcher) {
    return (
      <div className="export-panel">
        <p className="hint">
          当前角色为 viewer，仅研究者可导出数据。
          <br />
          请使用 researcher / researcher123 登录。
        </p>
      </div>
    )
  }

  if (!activeLayerId || !hasData) {
    return (
      <div className="export-panel">
        <p className="hint">选择图层后可导出数据</p>
      </div>
    )
  }

  const csvUrl = getExportCsvUrl(
    activeLayerId,
    startTime,
    endTime,
  )

  return (
    <div className="export-panel">
      <h4>📥 数据导出</h4>
      <a
        href={csvUrl}
        className="btn btn-primary btn-sm"
        download
      >
        📄 导出 CSV
      </a>
    </div>
  )
}
