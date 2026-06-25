import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header className="app-header">
          <h1>遥感数据展示平台</h1>
        </header>
        <main className="app-main">
          <Routes>
            <Route path="/" element={<div>Map View</div>} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
