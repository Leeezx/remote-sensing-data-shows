import { useState } from 'react'
import { useAuth } from '../contexts/AuthContext'

export default function Header() {
  const { user, login, logout, isAuthenticated } = useAuth()
  const [showLogin, setShowLogin] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const handleLogin = async () => {
    setError('')
    try {
      await login(username, password)
      setShowLogin(false)
    } catch {
      setError('Invalid username or password')
    }
  }

  return (
    <header className="app-header">
      <div className="header-left">
        <h1>🌍 遥感数据展示平台</h1>
      </div>
      <div className="header-right">
        {isAuthenticated ? (
          <div className="user-info">
            <span className="user-name">
              {user!.username}
              <span className="user-role">({user!.role})</span>
            </span>
            <button className="btn btn-sm" onClick={logout}>
              退出
            </button>
          </div>
        ) : (
          <div className="login-area">
            {!showLogin ? (
              <button className="btn btn-sm" onClick={() => setShowLogin(true)}>
                登录
              </button>
            ) : (
              <div className="login-form">
                <input
                  type="text"
                  placeholder="用户名"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                />
                <input
                  type="password"
                  placeholder="密码"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                />
                <button className="btn btn-sm btn-primary" onClick={handleLogin}>
                  确认
                </button>
                <button
                  className="btn btn-sm"
                  onClick={() => {
                    setShowLogin(false)
                    setError('')
                  }}
                >
                  取消
                </button>
                {error && <span className="login-error">{error}</span>}
                <span className="login-hint">
                  演示账号: viewer / viewer123 或 researcher / researcher123
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  )
}
