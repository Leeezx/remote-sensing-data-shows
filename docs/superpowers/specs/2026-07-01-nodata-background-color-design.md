# NoData 半透明遮罩设计

## 背景

SSM 瓦片渲染时，无效像元（mask、NoData、NaN、无穷值、哨兵值 -999）在 `colorize()` 中被设为全透明 `[0,0,0,0]`，底层地图瓦片完全透出，视觉上地图底色喧宾夺主。

## 目标

- NoData 区域用一种半透明颜色填充，遮住底图但保留隐约可见的层次感。
- 每个图层可独立配置 NoData 遮罩颜色和透明度。
- 不配置时使用统一默认值。

## 非目标

- 不改变有效像元的着色逻辑。
- 不改变 `valid_data_mask` 的排除规则。
- 不处理预生成的静态 PNG 瓦片（NDVI、降水等），它们已在生成时固化了透明处理。
- 不影响前端图例或查询逻辑。

## 后端设计

### colorize 参数扩展

`colorize()` 新增可选参数 `nodata_color: tuple | None = None`，一个 `(R, G, B, A)` 四元组。

- 当 `nodata_color is None`（默认）：行为不变，无效像素保持 `[0,0,0,0]`。
- 当 `nodata_color` 传入时：先用该颜色填充整个 RGBA 数组，再对有效像素覆写计算颜色和 alpha=255。无效像素保留填充色。

```python
def colorize(values, legend, source_mask=None, nodata=None, nodata_color=None):
    ...
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    if nodata_color is not None:
        rgba[..., :] = nodata_color
    ...
```

### SSM 瓦片渲染传参

`_render_ssm_tile()` 从图层元数据读取 `nodataColor`（hex 字符串）和 `nodataOpacity`（0~1 浮点数），解析为 RGBA 元组后传入 `colorize()`。

默认值：
- 颜色：`#e8e8e8`
- 透明度：`0.5`

解析逻辑：
```python
nodata_color_hex = layer.get("nodataColor", "#e8e8e8")
nodata_opacity = float(layer.get("nodataOpacity", 0.5))
nodata_rgb = tuple(bytes.fromhex(nodata_color_hex.lstrip("#")))
nodata_color = (*nodata_rgb, int(round(nodata_opacity * 255)))
```

### layers.json 配置

每个图层可选增加两个字段（不配则走默认值）：

```json
{
  "id": "ssm",
  "nodataColor": "#d0d0d0",
  "nodataOpacity": 0.4
}
```

## 错误与回退

- `nodataColor` 非法 hex 或无 `nodataOpacity` 时，回退到默认值 `#e8e8e8` + `0.5`。
- 旧版 `layers.json` 没有这两个字段时，默认行为生效，任何调用不做变更。

## 测试

后端单元测试覆盖：

- `colorize` 传入 `nodata_color` 后无效像素填充该颜色，有效像素不受影响。
- `colorize` 不传 `nodata_color` 时行为不变（无效像素透明）。
- `_render_ssm_tile` 正确解析 `nodataColor`/`nodataOpacity` 并传入 `colorize`。
- 图层不配字段时回退默认值。
- 非法颜色格式时回退默认值。

完成后运行后端全量测试并确认通过。
