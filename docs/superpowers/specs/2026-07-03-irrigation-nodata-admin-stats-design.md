# 灌溉用水页面：nodata背景色对齐 & 行政区统计模式

## 背景

1. 灌溉用水瓦片的 nodata 背景色（`_render_irrigation_tile`）硬编码为 `(0xE8,0xE8,0xE8,128)`，而SSM瓦片渲染器从图层元数据读取 `nodataColor` / `nodataOpacity`。虽然默认值相同，但灌溉路径缺乏可配置性，且用户反馈两个页面的中国区域内无数据像元视觉效果不一致。

2. 当前行政区统计模式下，矢量图层仅以半透明蓝色轮廓叠加在栅格之上，不携带数值信息。用户希望进入统计模式时将矢量按区域多年平均值着色（choropleth），隐藏原始栅格瓦片，并暂停像元查询；退出后恢复原状。

## 目标

- 灌溉瓦片 nodata 颜色改为从 `irrigation_layer.json` 元数据读取，与 SSM `_render_ssm_tile` 模式一致。
- 新增后端接口返回所有行政区的多年平均灌溉用水量及对应图例阈值。
- 行政区统计模式下：隐藏栅格瓦片、矢量按年均值着色、图例切换为统计图例、冻结时间轴、禁用像素查询。
- 点击行政区照常显示统计卡片和月度/年度折线图。
- 退出统计模式恢复栅格瓦片显示、像素查询功能、原始图例、时间轴。

## 非目标

- 不改变村级统计功能的现有行为（村级目前无矢量文件，仅保留占位逻辑）。
- 不改变 SSM 或其它图层的渲染逻辑。
- 不改变区域统计数据和折线图的后端计算逻辑。
- 不在瓦片URL中传递 nodata 颜色参数。

## 后端设计

### 1. nodata 颜色改为元数据驱动

修改 `_render_irrigation_tile`（`backend/routers/tiles.py:120`），从 `get_irrigation_layer()` 返回的字典中读取 `nodataColor` 和 `nodataOpacity`，与 `_render_ssm_tile` 逻辑一致：

```python
nodata_color_hex = layer.get("nodataColor", "#e8e8e8")
nodata_opacity = float(layer.get("nodataOpacity", 0.5))
try:
    nodata_rgb = tuple(bytes.fromhex(nodata_color_hex.lstrip("#")))
    nodata_alpha = int(round(nodata_opacity * 255))
    nodata_color = (*nodata_rgb, nodata_alpha)
except (ValueError, TypeError):
    nodata_color = (0xE8, 0xE8, 0xE8, 128)
```

### 2. 区域多年平均值接口

新增 `GET /irrigation/regions/averages?level=county`

**计算逻辑：**

1. 获取指定级别的行政区列表（从 `irrigation_regions.json`）。
2. 对每个区域，从 `irrigation_region_series.json` 读取 `annual` 时间序列。
3. 计算多年平均值：`sum(annual_series.values) / len(annual_series.values)`。
4. 若某区域无预计算数据，记录为 `null`。
5. 收集所有非 `null` 的平均值，调用 `build_irrigation_dynamic_legend`（复用 `backend/irrigation_legend.py` 或 `backend/ssm_legend.py` 的 `build_dynamic_legend`）生成 6 档动态图例。
6. 图例基础颜色和标签格式取自 `irrigation_layer.json` 的 `legend` 字段。

**实现位置：** 新增函数 `get_irrigation_region_averages` 在 `backend/irrigation_stats.py`，路由在 `backend/routers/irrigation.py`。

**响应格式：**

```json
{
  "level": "county",
  "unit": "万m³",
  "averages": [
    {"regionId": "156420704", "name": "鄂城区", "average": 1234.5},
    {"regionId": "156522730", "name": "龙里县", "average": 567.8}
  ],
  "legend": [
    {"value": 100, "color": "#eff3ff", "label": "100 万m³"},
    {"value": 300, "color": "#bdd7e7", "label": "300 万m³"},
    {"value": 600, "color": "#6baed6", "label": "600 万m³"},
    {"value": 900, "color": "#3182bd", "label": "900 万m³"},
    {"value": 1200, "color": "#08519c", "label": "1200 万m³"},
    {"value": 1500, "color": "#042d60", "label": "1500 万m³"}
  ]
}
```

**图例阈值生成：** 将 `build_dynamic_legend` 抽取为独立可复用函数（接受 numpy 数组而非 raster 文件路径），或直接复用 `build_irrigation_dynamic_legend` 的百分位数逻辑。将所有区域年均值组成的 numpy 数组传入，取 2%-98% 范围的 6 个等距百分位数，配对基础图例颜色。

### 3. 后端文件变更汇总

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/routers/tiles.py` | 修改 | `_render_irrigation_tile` 从 layer 元数据读取 nodata 颜色 |
| `backend/routers/irrigation.py` | 修改 | 新增 `/irrigation/regions/averages` 端点 |
| `backend/irrigation_stats.py` | 修改 | 新增 `get_irrigation_region_averages` 函数 |
| `backend/ssm_legend.py` 或 `backend/irrigation_legend.py` | 修改 | 如有必要，抽取 `build_dynamic_legend` 使其可接受裸 numpy 数组 |

## 前端设计

### 1. 新增类型定义

`frontend/src/types/index.ts`:

```typescript
export interface IrrigationRegionAverage {
  regionId: string
  name: string
  average: number | null
}

export interface IrrigationRegionAveragesResponse {
  level: IrrigationRegionLevel
  unit: string
  averages: IrrigationRegionAverage[]
  legend: LegendItem[]
}
```

### 2. 新增 API 调用

`frontend/src/services/api.ts`:

```typescript
export async function getIrrigationRegionAverages(
  level: IrrigationRegionLevel,
): Promise<IrrigationRegionAveragesResponse> {
  const { data } = await client.get('/irrigation/regions/averages', {
    params: { level },
  })
  return data
}
```

### 3. IrrigationPage 状态变更

新增状态：
- `adminAverages: Map<string, number>` — regionId → 年均值映射（用于快速查找）
- `adminLegend: LegendItem[]` — 统计模式图例
- `adminStatsLoading: boolean` — 统计数据加载状态
- `isAdminStatsMode` — 派生自 `regionLevel !== null && adminAverages.size > 0`

**进入统计模式流程（regionLevel 变化 effect）：**

1. 清除现有矢量/选中/系列状态（保持现有逻辑）。
2. 获取矢量状态 → 获取 GeoJSON → 获取区域年均值。
3. 年均值成功 → `adminAverages` 和 `adminLegend` 填充。
4. 年均值失败 → 回退到现有轮廓显示模式（无着色）。

**退出统计模式（regionLevel 设为 null）：**

1. 清除 `adminAverages`、`adminLegend`。
2. 清除矢量、选中区域、系列数据。
3. 恢复原始栅格显示和图例。

### 4. MapView 改动

**新增 props：**

```typescript
interface MapViewProps {
  // ... existing props ...
  disableQuery?: boolean          // 统计模式下禁用像素查询
  hideRaster?: boolean            // 统计模式下隐藏栅格瓦片
  regionColorMap?: Map<string, string> | null  // regionId → fillColor 映射
}
```

**MapEvents 改动（line 312-316）：**

```tsx
<MapEvents
  enabled={Boolean(activeLayerId && currentTime && !disableQuery)}
  // ...
/>
```

**TileOverlay 改动：** 增加 `visible` prop，为 false 时不添加瓦片图层。

**RegionOverlay 改动：** 增加 `colorMap` prop。当提供时，每个 feature 的 `fillColor` 从 `colorMap` 查找（按 feature id），替代默认蓝色。`fillOpacity` 提升至 0.65（使着色可见）。

### 5. RegionOverlay 颜色插值

前端需实现 JS 版的颜色插值函数（模拟 Python `np.interp` + `colorize` 逻辑）：

```typescript
function interpolateColor(value: number, legend: LegendItem[]): string {
  // 按 value 升序排列 legend stops
  // 对 R、G、B 三个通道分别做线性插值
  // 返回 "#rrggbb" 格式颜色
}
```

在 `IrrigationPage` 中：
1. 获取 `adminAverages` 和 `adminLegend` 后。
2. 遍历所有 region，用 `interpolateColor(average, adminLegend)` 计算每个区域的填充色。
3. 构建 `Map<string, string>` 传给 `MapView.regionColorMap`。

### 6. 时间轴冻结

当 `isAdminStatsMode` 为 true 时：
- 时间显示文本保持不变（显示最后选择的时间）。
- 上一个/下一个按钮禁用（`disabled` prop）。
- 年度/月度切换按钮禁用。

### 7. 图例切换

当 `isAdminStatsMode` 为 true 时，`Legend` 组件使用 `adminLegend`（统计图例），而非 `legendState.items`（栅格图例）。

```tsx
<Legend
  layer={layer}
  items={isAdminStatsMode ? adminLegend : legendState.items}
  status={isAdminStatsMode ? 'ready' : legendState.status}
/>
```

### 8. 前端文件变更汇总

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/types/index.ts` | 修改 | 新增 `IrrigationRegionAverage`、`IrrigationRegionAveragesResponse` |
| `frontend/src/services/api.ts` | 修改 | 新增 `getIrrigationRegionAverages` |
| `frontend/src/pages/IrrigationPage.tsx` | 修改 | 新增年均值状态管理、颜色映射计算、图例切换、时间轴冻结 |
| `frontend/src/components/MapView.tsx` | 修改 | TileOverlay 增加 visible、MapEvents 增加 disableQuery、RegionOverlay 增加 colorMap |
| `frontend/src/components/Legend.tsx` | 无需修改 | 已通过 props 接受任意 `LegendItem[]` |

## 数据流

```
用户点击"县级统计"
  → setRegionLevel('county')
  → useEffect:
      GET /irrigation/vectors?level=county → vectorStatus
      GET /irrigation/vectors/county → regionVector (GeoJSON)
      GET /irrigation/regions/averages?level=county → {averages, legend}
  → 计算 colorMap: Map<regionId, interpolatedColor>
  → MapView: hideRaster=true, disableQuery=true, regionColorMap={colorMap}
  → Legend: 显示 adminLegend
  → 时间轴: 冻结

用户点击某行政区
  → RegionOverlay click (stopPropagation, disableQuery=true 时像素查询已停)
  → onRegionSelect({id, name})
  → useEffect: GET /irrigation/series (monthly + annual)
  → 右侧面板显示统计卡片和折线图

用户再次点击"县级统计"
  → setRegionLevel(null)
  → 清除 adminAverages, adminLegend, regionVector, selectedRegion, series
  → MapView: hideRaster=false, disableQuery=false, regionColorMap=null
  → Legend: 恢复栅格图例
  → 时间轴: 解冻
```

## 错误处理

- 区域年均值接口失败：回退到轮廓显示（当前行为），`adminLegend` 为空时图例使用栅格图例。
- 单个区域无年均值数据（average 为 null）：不计算颜色，使用默认轮廓颜色。
- 图例插值边界：区域年均值低于最小 legend stop 时使用第一个颜色，高于最大 stop 时使用最后一个颜色。
- 矢量 GeoJSON 加载失败：状态栏显示错误信息，不进入统计模式。

## 测试

### 后端

- `GET /irrigation/regions/averages?level=county` 返回正确的年均值和图例。
- 图例阈值从区域年均值百分位数计算，与栅格动态图例计算方法一致。
- 无预计算数据的区域 average 为 null，不影响其他区域。
- `_render_irrigation_tile` 从 layer metadata 读取 nodata 颜色，默认值与之前硬编码值一致。

### 前端

- 进入统计模式：栅格隐藏、矢量着色、像素查询禁用、图例切换、时间轴冻结。
- 退出统计模式：栅格恢复、像素查询恢复、图例恢复、时间轴解冻。
- 颜色插值函数：边界值和外推值正确处理。
- 点击着色矢量区域：照常显示统计卡片和折线图。
- 统计模式下地图空白处点击：不触发像素查询。
- 年均值接口失败的优雅降级。

## 验证

1. `python -m pytest backend/tests/ -v`
2. `cd frontend && npx vitest run`
3. `cd frontend && npm run build`
4. 浏览器验证：切换到灌溉用水页面 → 切换年度/月度 → 点击"县级统计" → 观察矢量着色和图例 → 点击一个县 → 查看统计图表 → 再次点击"县级统计"退出 → 确认恢复。
