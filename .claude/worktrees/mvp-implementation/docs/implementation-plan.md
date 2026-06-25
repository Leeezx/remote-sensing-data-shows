# 遥感数据展示网站 MVP 实现计划

## Summary

基于 `需求.md`，第一版实现一个 React + FastAPI 的前后端分离 MVP：支持遥感图层浏览、时间切换、基础空间查询、图表分析、CSV/图表导出和轻量登录权限。数据采用“预处理样例数据”方式：前端加载瓦片、元数据与统计 JSON，暂不在 MVP 中实现 GeoTIFF/NetCDF 上传处理和完整管理后台。

## Key Changes

- 新建项目结构：
  - `frontend/`：React + TypeScript + Vite，地图使用 Leaflet 或 MapLibre，图表使用 ECharts。
  - `backend/`：FastAPI，提供图层目录、时间序列、空间查询、导出和登录接口。
  - `data/`：存放预处理样例瓦片、图层元数据、时间序列 JSON、区域统计 JSON。
- MVP 页面：
  - 地图主界面：底图、遥感图层叠加、透明度、图例、缩放拖拽。
  - 时间控制：day / month / year 粒度切换、时间滑块、播放暂停。
  - 查询分析：点选像元值、矩形/多边形框选、均值/最大/最小统计。
  - 数据检索：按时间、数据类型、区域筛选。
  - 图表区：时间序列折线图、分布直方图、区域对比图。
  - 导出：CSV 导出、图表 PNG 导出；GeoTIFF 下载标记为后续增强。
- 轻量权限：
  - 实现登录接口和 JWT。
  - 角色包含 `viewer` 与 `researcher`。
  - `viewer` 可浏览和查询；`researcher` 额外可导出数据。
  - 管理员后台、上传处理、用户管理放入后续阶段。

## Public Interfaces

### `POST /api/auth/login`

输入：

```json
{ "username": "researcher", "password": "demo123" }
```

输出：

```json
{
  "access_token": "jwt-token",
  "user": {
    "username": "researcher",
    "role": "researcher"
  }
}
```

### `GET /api/layers`

输出图层列表：

```json
[
  {
    "id": "ndvi",
    "name": "NDVI",
    "type": "vegetation",
    "unit": "index",
    "timeRange": {
      "start": "2025-01",
      "end": "2025-12",
      "step": "month"
    },
    "tileTemplate": "/data/tiles/ndvi/{time}/{z}/{x}/{y}.png",
    "legend": [
      { "color": "#d73027", "label": "low" },
      { "color": "#1a9850", "label": "high" }
    ]
  }
]
```

### `GET /api/layers/{layerId}/times`

输出该图层可用时间点：

```json
["2025-01", "2025-02", "2025-03"]
```

### `GET /api/query/point?layerId=&time=&lng=&lat=`

输出点位像元值、单位、坐标和时间：

```json
{
  "layerId": "ndvi",
  "time": "2025-06",
  "lng": 116.39,
  "lat": 39.9,
  "value": 0.68,
  "unit": "index"
}
```

### `POST /api/query/area`

输入：

```json
{
  "layerId": "ndvi",
  "time": "2025-06",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[116.1, 39.7], [116.7, 39.7], [116.7, 40.1], [116.1, 40.1], [116.1, 39.7]]]
  }
}
```

输出：

```json
{
  "mean": 0.62,
  "max": 0.86,
  "min": 0.21,
  "count": 1280
}
```

### `GET /api/series?layerId=&regionId=&start=&end=`

输出时间序列图表数据：

```json
[
  { "time": "2025-01", "value": 0.42 },
  { "time": "2025-02", "value": 0.48 }
]
```

### `GET /api/export/csv?...`

仅 `researcher` 可用，输出 CSV 文件。

## Implementation Steps

1. 初始化项目骨架：创建 `frontend/`、`backend/`、`data/`，配置开发启动脚本和环境变量。
2. 准备样例数据规范：定义图层元数据 JSON、时间序列 JSON、区域统计 JSON、瓦片 URL 目录约定。
3. 实现 FastAPI 后端：先写接口测试，再实现认证、图层、查询、时间序列和 CSV 导出接口。
4. 实现 React 前端布局：地图为主视图，左侧/顶部提供图层、时间、筛选和导出控制，右侧或底部展示查询结果和图表。
5. 接入地图能力：加载底图和遥感瓦片，支持图层切换、透明度、图例、时间滑块和播放。
6. 接入空间查询：实现点选、矩形框选、多边形绘制，并调用后端统计接口。
7. 接入图表和导出：展示折线图、直方图、区域对比图，支持 CSV 和图表 PNG 导出。
8. 完善权限控制：前端按角色隐藏导出入口，后端校验 JWT 和角色权限。
9. 做基础响应式适配：保证 Chrome、Edge、Firefox 和移动端基础浏览可用。
10. 编写 README：说明本地启动、样例账号、数据目录格式、接口说明和后续扩展方向。

## Test Plan

### 后端测试

- 登录成功/失败。
- 无 token 访问受保护接口返回 401。
- `viewer` 访问 CSV 导出返回 403。
- 图层列表、时间点、点查询、区域统计返回结构正确。
- 空区域或无数据时间点返回明确空结果。

### 前端测试

- 页面可启动并加载地图。
- 图层切换、透明度、图例、时间滑块、播放按钮可用。
- 点选和框选后能显示统计结果。
- 图表随筛选条件更新。
- `viewer` 看不到导出或导出不可用，`researcher` 可导出。

### 验收场景

- 用户登录后选择 NDVI 图层，切换月份并播放变化。
- 用户点选地图位置查看像元值。
- 研究人员框选区域，查看均值/最大/最小并导出 CSV。
- 用户切换到降水或土壤湿度图层，图例和单位正确更新。

## Assumptions

- MVP 使用预处理样例数据，不实现在线 GeoTIFF/NetCDF 解析。
- 管理后台、数据上传、处理状态监控、完整用户注册和管理员权限作为第二阶段。
- 地图性能目标按样例瓦片验证：常规图层首次加载目标小于 3 秒。
- 当前目录不是 git 仓库，且 CodeGraph 尚未初始化；实现阶段可先初始化项目，再按需要建立代码索引。
