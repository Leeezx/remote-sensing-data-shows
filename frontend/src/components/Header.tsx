import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/base', label: '基础数据展示' },
  { to: '/irrigation', label: '灌溉用水数据展示' },
  { to: '/reclamation', label: '复耕潜力评估' },
  { to: '/water-demand', label: '需水补水计算与评估' },
]

export default function Header() {
  return (
    <header className="app-header">
      <div className="header-left">
        <h1>遥感数据展示平台</h1>
        <nav className="app-nav" aria-label="主导航">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}
