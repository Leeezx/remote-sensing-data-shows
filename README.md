# 遥感数据展示平台

基于 Web 的遥感数据展示与分析平台，支持多源遥感数据（NDVI、降水、土壤湿度、LST）的可视化浏览、时间序列分析和空间查询。

## 技术栈

- **前端**: React + TypeScript + Vite + Leaflet + ECharts
- **后端**: FastAPI (Python)
- **数据**: 预处理 JSON 元数据 + PNG 瓦片

## 快速启动

### 前置条件

- Node.js >= 18
- Python >= 3.10

### 1. 启动后端

```bash
cd backend
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

后端运行在 <http://localhost:8000>。

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端运行在 <http://localhost:5173>。

开发模式下，Vite 自动代理 `/api` 和 `/data` 请求到后端。

### 3. 访问

打开浏览器访问 <http://localhost:5173>。

## 样例账号

| 用户名 | 密码 | 角色 | 权限 |
|--------|------|------|------|
| `viewer` | `viewer123` | 浏览者 | 浏览图层、空间查询、查看图表 |
| `researcher` | `researcher123` | 研究者 | 上述全部 + 导出 CSV |

## 功能概览

### 地图浏览
- 底图 (OpenStreetMap) + 遥感图层叠加
- 4 个数据图层: NDVI, 降水, 土壤湿度, LST
- 透明度调节和图例自动生成
- 缩放、拖拽、边界限制

### 时间控制
- 月份粒度时间滑块
- 播放/暂停动画功能
- 按时间切换遥感图层

### 空间查询
- 点击地图查询像元值
- Shift + 拖拽框选区域，获取均值/最大/最小统计

### 图表分析
- 时间序列折线图 / 柱状图
- 区域筛选过滤
- 图表 PNG 导出

### 数据导出
- CSV 导出（需研究者权限）
- 图表 PNG 下载

### 权限控制
- JWT 登录认证
- viewer: 浏览 + 查询
- researcher: 浏览 + 查询 + 导出

## 项目结构

```
├── frontend/                # React 前端
│   ├── src/
│   │   ├── components/      # UI 组件
│   │   │   ├── Header.tsx       # 顶部导航栏 + 登录
│   │   │   ├── Sidebar.tsx      # 侧边栏 (图层/时间/区域)
│   │   │   ├── MapView.tsx      # Leaflet 地图
│   │   │   ├── Legend.tsx       # 图例
│   │   │   ├── QueryPanel.tsx   # 空间查询结果
│   │   │   ├── ChartPanel.tsx   # ECharts 图表
│   │   │   └── ExportPanel.tsx  # CSV 导出
│   │   ├── contexts/        # React Context
│   │   │   └── AuthContext.tsx  # 认证状态管理
│   │   ├── services/        # API 服务
│   │   │   └── api.ts           # 后端接口调用
│   │   ├── types/           # TypeScript 类型
│   │   │   └── index.ts
│   │   ├── App.tsx          # 主组件
│   │   └── main.tsx         # 入口
│   └── vite.config.ts       # Vite 配置 (含代理)
├── backend/                 # FastAPI 后端
│   ├── routers/             # 路由模块
│   │   ├── auth.py              # 认证 (POST /api/auth/login)
│   │   ├── layers.py            # 图层 (GET /api/layers, /layers/{id}/times)
│   │   ├── query.py             # 空间查询 (GET /query/point, POST /query/area)
│   │   ├── series.py            # 时间序列 (GET /api/series)
│   │   ├── export.py            # CSV 导出 (GET /api/export/csv)
│   │   ├── tiles.py             # 瓦片服务 (GET /data/tiles/...)
│   │   ├── regions.py           # 区域列表 (GET /api/regions)
│   │   └── health.py            # 健康检查
│   ├── services/
│   ├── models/
│   ├── auth.py              # JWT 认证逻辑
│   ├── data_loader.py       # JSON 数据加载
│   ├── main.py              # 应用入口
│   └── tests/               # 后端测试 (29 tests)
├── data/                    # 示例数据
│   ├── metadata/layers.json     # 图层元数据
│   ├── series/                  # 时间序列 JSON
│   ├── stats/                   # 区域统计数据
│   │   ├── regions.json             # 区域定义
│   │   └── area_stats.json          # 区域统计值
│   └── tiles/                   # 瓦片图片 (占位)
└── docs/                    # 文档
    ├── 需求.md
    └── implementation-plan.md
```

## API 接口

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 用户登录，返回 JWT |

请求体: `{ "username": "...", "password": "..." }`

### 图层

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/layers` | 图层列表 (含元数据、图例) |
| GET | `/api/layers/{layerId}/times` | 图层可用时间点 |

### 空间查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/query/point?layerId=&time=&lng=&lat=` | 点查询 |
| POST | `/api/query/area` | 区域统计查询 |

### 时间序列

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/series?layerId=&regionId=&start=&end=` | 时间序列数据 |

### 导出

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/export/csv?layerId=&regionId=&start=&end=` | CSV 导出 (需 researcher) |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/regions` | 区域列表 |
| GET | `/api/health` | 健康检查 |

## 数据目录格式

### 图层元数据 (`data/metadata/layers.json`)

每个图层包含 id, name, type, unit, range, timeRange, tileTemplate, legend 等字段。

### 时间序列 (`data/series/{layerId}_series.json`)

```json
[{ "time": "2025-01", "value": 0.42 }, ...]
```

### 区域统计 (`data/stats/area_stats.json`)

```json
{
  "region_id": {
    "layer_id": {
      "time": { "mean": 0.62, "max": 0.86, "min": 0.21, "count": 1280 }
    }
  }
}
```

### 瓦片目录 (`data/tiles/{layer}/{time}/{z}/{x}/{y}.png`)

预处理 256×256 PNG 瓦片，按 XYZ 切片方案组织。

## 后续扩展方向

- GeoTIFF / NetCDF 上传与处理
- 管理后台 (数据管理、图层配置)
- 用户注册与管理
- 更多遥感数据类型支持
- 日粒度和年粒度时间分析
- 多边形自定义区域查询
- WebGL 渲染加速

## 兼容性

- Chrome / Edge / Firefox (最新版)
- 移动端基础浏览 (响应式布局)

## License

MIT
