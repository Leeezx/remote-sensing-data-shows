---
date: 2026-06-27
topic: SSM 动态数据管线改造
status: approved
---

## 一、目标

将 SSM（表层土壤水分）数据流从"预生成静态 PNG 瓦片 + JSON 统计"改造为"COG + TiTiler 动态瓦片 + rasterio 实时查询"，实现真正的实时遥感数据展示。

其他 4 个图层（NDVI、降水、土壤湿度、LST）暂保持不变。

## 二、架构变化

**改造前**：
```
前端 MapView → /data/tiles/ssm/{time}/{z}/{x}/{y}.png → 读预生成 PNG → 返回
点查询 → /api/query/point → 查 JSON stats 文件 → 返回
面积查询 → /api/query/area → 查 JSON stats 文件 → 返回
```

**改造后**：
```
前端 MapView → /cog/tiles/{z}/{x}/{y}.png?url=...&colormap=...&rescale=...
                     → TiTiler TilerFactory → rasterio 读 COG → 渲染 PNG → 返回
点查询 → /api/query/point → rasterio 从 COG 读单个像元 → 返回精确值
面积查询 → /api/query/area → rasterio 从 COG 读取矩形内所有像元 → 统计并返回
```

## 三、核心改动文件

| 文件 | 改动 |
|------|------|
| `scripts/convert_to_cog.py` | **新增** — 批量 COG 转换脚本 |
| `backend/routers/tiles.py` | **重写** — TiTiler TilerFactory 动态瓦片 |
| `backend/routers/query.py` | **重写** — rasterio 实时点查询和面积查询 |
| `backend/main.py` | TiTiler 路由注册 + COG 目录配置 |
| `frontend/src/components/MapView.tsx` | 瓦片 URL 改为 TiTiler 格式 |
| `frontend/src/App.tsx` | 图层切换 loading 骨架屏 |
| `frontend/src/components/Sidebar.tsx` | 时间滑块改为可视化时间轴 |
| `data/metadata/layers.json` | SSM 图层 tileTemplate 更新 |
| `backend/requirements.txt` | 添加 titiler.core |

## 四、COG 转换

源数据：`F:\全国灌溉用水反演\数据2010-2013\SSM预测结果\YYYY_NN.tif`
- 4 年 × 46 期/年 ≈ 184 个文件，每个 18MB
- CRS: EPSG:4326, float32, 1 band, 13341×7667 像素
- 有效值范围: 0.09–0.39 m³/m³，NaN 为无效区域

转换流程：
1. `rio cogeo create <src>.tif <dst>_cog.tif --cog-profile deflate`
2. 目标路径: `data/rasters/ssm/YYYY_NN_cog.tif`

命名规则：文件名即时间标识（如 `2010_05`），映射到 8 天合成周期。

## 五、后端 API 变化

### TiTiler 瓦片端点（替代原 tiles.py）
```
GET /cog/tiles/{z}/{x}/{y}.png
  ?url=data/rasters/ssm/2010_05_cog.tif
  &colormap_name=rdylgn
  &rescale=0.09,0.39
  &nodata=nan
```
直接由 `titiler.core.factory.TilerFactory` 提供。

### 点查询（重写）
```
GET /api/query/point?layerId=ssm&time=2010_05&lng=116.4&lat=39.9
  → rasterio.open(COG) → src.index(lng, lat) → 读取像素值 → 返回
```
对于非 SSM 图层仍用原 JSON stats 逻辑。

### 面积查询（重写）
```
POST /api/query/area { layerId, time, geometry }
  → rasterio 读取矩形内所有像素 → { mean, max, min, count }
```
同上，SSM 用 rasterio，其他图层保留原逻辑。

## 六、前端变化

1. **MapView.tsx**: SSM 图层 tileUrl 使用 TiTiler 格式，colormap 选择 `rdylgn`（红-黄-绿，与 current legend 匹配）
2. **App.tsx**: 图层切换时添加 loading 骨架屏（半透明遮罩 + spinner）
3. **Sidebar.tsx**: 时间控制从简单 slider 改为可视化时间轴（横向 timeline，标记数据覆盖点）
4. **layers.json**: SSM tileTemplate 更新

## 七、测试变化

- 添加 rasterio 点查询和面积查询的单元测试
- 更新现有 test_query.py 中的 SSM 相关测试（从 JSON 验证改为 rasterio 验证）
- TiTiler 瓦片端点测试（是否返回有效 PNG）

## 八、不影响的部分

- 前端组件：Header, Legend, QueryPanel, ChartPanel, ExportPanel 无需改动
- 后端：auth, export, health, regions, series, layers 路由保持不变
- data_loader.py 保持不变（SSM 的 JSON series 仍用于时间序列图表）
- 现有静态瓦片路由 `/data/tiles/` 保持可用（供其他 4 个图层使用）
