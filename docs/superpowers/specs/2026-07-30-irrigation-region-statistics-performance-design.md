# 灌溉区域统计运行时分片与缓存设计

## 背景

灌溉用水页面进入行政区统计模式时，会并发请求县级矢量和县级多年
平均值。当前平均值端点先在请求线程中完整解析
`data/stats/irrigation_region_series.json`，再从全国县级、乡镇级、
年度和月度序列中筛选县级数据。

当前源文件为 241,105,174 bytes，约 229.94 MiB。本机真实 HTTP
基准中，县级平均值冷请求约 1.99 秒，缓存命中后约 0.06 秒；首次
解析使单个 Python worker 工作集增加约 845.7 MiB。生产镜像默认使用
两个 Uvicorn worker，因此两个进程会分别保留一份膨胀对象。

实际县级平均值响应只有约 178.9 KiB。性能问题的根因是运行时加载
边界过大，而不是平均值计算、响应序列化、县级矢量或浏览器渲染。

## 目标

1. 保持现有 `/api/irrigation/regions/averages` 和
   `/api/irrigation/series` 请求与响应契约。
2. 运行时不再读取全国 230 MiB 序列文件。
3. 离线发布县级和按县乡镇的平均值、图例与明细序列小产物。
4. 保留全国文件作为离线构建与回滚源，不将其复制进生产镜像。
5. 为只读统计响应增加进程内缓存、HTTP 条件缓存和 Nginx 防击穿缓存。
6. 让县界先于平均值着色显示，避免较慢的着色数据阻塞整个统计模式。
7. 在当前真实数据和本机基准环境达到：
   - 县级平均值冷请求不超过 300 ms；
   - 缓存命中请求不超过 100 ms；
   - 单个 worker 的统计运行时数据内存增量低于 100 MiB。

## 不在范围内

- 不删除或重算现有全国区域序列源文件。
- 不修改年度和月度统计值、区域编码、单位、六级图例算法或色带。
- 不引入 SQLite、Redis、DuckDB 或新的运行时依赖。
- 不改变县级、乡镇级矢量分片格式。
- 不改变 Uvicorn worker 数量。
- 不以启动预热或增加 worker 作为主要优化。
- 不在运行时缺少新产物时回退读取旧大文件或现场扫描栅格。

## 方案选择

### 采用方案：JSON 运行时分片

从现有大文件离线派生运行时专用的小型 JSON。县级数据规模可控，
乡镇数据按父县分片。该方案沿用仓库既有的 JSON、原子写入和按县
分片模式，无需新增数据库和生产依赖。

### 未采用方案：SQLite 索引

SQLite 同样可以避免全量反序列化，但会增加数据库构建、完整性检查、
连接管理和部署迁移路径。当前数据只读、父子层级固定，JSON 分片已经
能满足延迟和内存目标。

### 未采用方案：仅缓存和预热

Nginx 缓存和部署后预热可以隐藏部分首次等待，但不能消除每个 worker
约 846 MiB 的内存对象，也无法阻止缓存失效后的冷解析。

## 文件布局

新增运行时根目录：

```text
data/stats/irrigation_runtime/
  manifest.json
  averages/
    county.json
    township_by_county/
      110101.json
      110102.json
  series/
    county.json
    township_index.json
    township_by_source_code/
      110101.json
      110102.json
      misc.json
```

averages 的县代码使用现有
`backend.township_chunks.county_code_from_id` 规则，并以已发布乡镇
矢量分片中的县-乡镇关系为准。series 分片使用十二位乡镇源 ID 的
前六位；非十二位历史 ID 写入 `misc.json`。目录名称和值排序必须
稳定，相同输入重复构建得到相同业务内容。

现有 `.dockerignore` 已排除
`data/stats/irrigation_region_series.json`。后端镜像继续复制
`data/stats/`，因此只包含新的运行时产物和其他小型统计文件。

## 产物契约

### Manifest

`manifest.json` 包含：

```json
{
  "schemaVersion": 1,
  "unit": "万m³",
  "sourceSha256": "<64 位十六进制摘要>",
  "countyCount": 2893,
  "sourceTownshipCount": 43726,
  "mappedTownshipCount": 43669,
  "mappedTownshipPairCount": 46021,
  "crossCountyTownshipCount": 2308,
  "unmappedTownshipCount": 57,
  "averageShardCount": 2865,
  "seriesShardCount": 2862,
  "artifacts": {
    "countyAverages": "averages/county.json",
    "countySeries": "series/county.json",
    "townshipIndex": "series/township_index.json"
  }
}
```

所有数量取真实构建结果，不硬编码为示例值。`seriesShardCount` 包含
`misc.json`。Manifest 不写入当前时间，避免相同输入生成不必要的
差异。

### 县级平均值

`averages/county.json` 的结构直接等于当前县级 averages API 响应：

```json
{
  "level": "county",
  "unit": "万m³",
  "averages": [
    {
      "regionId": "156110101",
      "name": "示例县",
      "average": 123.4
    }
  ],
  "legend": []
}
```

实际 `legend` 必须有六项，并使用当前动态分位数算法和基础色带。

### 乡镇平均值分片

每个 `averages/township_by_county/<县代码>.json` 直接等于该县的
乡镇 averages API 响应。区域集合取同名乡镇矢量分片中唯一的
`properties.id`，因此空间重分配后的乡镇与地图可见要素一致。同一
乡镇 ID 可以因跨县几何出现在多个县分片；各县图例只使用本县可见的
唯一乡镇 ID。

当前真实数据包含 43,669 个可见唯一乡镇 ID、46,021 个县-乡镇唯一
对和 2,308 个跨县乡镇 ID。另有 57 个序列 ID 没有可选矢量，不加入
averages 分片，但仍保留在 series 产物中。

### 县级明细

`series/county.json` 包含单位和全部县级条目：

```json
{
  "unit": "万m³",
  "regions": {
    "156110101": {
      "name": "示例县",
      "parentId": null,
      "annual": [],
      "monthly": []
    }
  }
}
```

县级文件使用紧凑 JSON，真实数据预计约 6 MiB。

### 乡镇明细索引与分片

`series/township_index.json` 将每个乡镇 `regionId` 映射到唯一的
series 分片名。标准十二位数字 ID 使用前六位，例如
`130521001000 -> 130521.json`；其他历史 ID 使用 `misc.json`。

每个 `series/township_by_source_code/<分片名>` 使用与县级文件相同
的结构，每个源序列 ID 在全部 series 分片中恰好出现一次。条目的
`parentId` 保留区域目录中的原值；当前真实目录没有可靠的单一
`parentId`，不得从跨县矢量关系中随意选择一个父县。

## 构建器

新增 `scripts/build_irrigation_runtime_stats.py`。默认输入：

- `data/stats/irrigation_region_series.json`
- `data/stats/irrigation_regions.json`
- `data/metadata/irrigation_layer.json`
- `data/vectors/irrigation/township_by_county/manifest.json`
- `data/vectors/irrigation/township_by_county/*.geojson`

默认输出为 `data/stats/irrigation_runtime/`。

构建流程：

1. 流程开始时读取并校验源序列、区域目录和基础图例。
2. 计算源序列文件 SHA-256。
3. 使用区域目录补充每个条目的稳定名称，并保留目录 `parentId`。
4. 逐个读取乡镇矢量分片，建立 46,021 个县-乡镇唯一对；同一县内
   的重复几何只计一个 ID，跨县 ID 在各县分别保留。
5. 生成县级平均值、按可见矢量关系分组的乡镇平均值和六级图例。
6. 生成县级 series、按源 ID 前六位分组的乡镇 series 和全量索引。
7. 在同级临时目录写入全部紧凑 JSON 和 manifest。
8. 重新读取临时产物并执行完整审计。
9. 审计全部通过后，复用乡镇矢量构建器的备份/替换模式事务式发布。
10. 发布失败时恢复旧目录；不留下半套正式产物。

构建器必须拒绝：

- 不受支持的 schema 或非对象顶层；
- 缺少 `unit`、县级或乡镇级数据；
- 区域 ID 重复或序列条目不是对象；
- 年度/月度序列不是数组，或点缺少有限数值；
- 矢量分片引用不存在的乡镇序列，或要素声明的 `parentId` 与分片县
  代码不一致；
- 同一乡镇在同一 averages 县分片重复计数；
- 同一序列 ID 在多个 series 分片出现，或索引与分片不一致；
- 图例不是六项、阈值非有限数或颜色顺序与基础图例不同；
- 生成数量与源数据、区域目录、矢量 manifest 不一致。

跨县出现的同一乡镇 ID 是经空间对齐后的允许情况，不属于重复错误。
没有矢量的 57 个当前源序列写入 series 并在 manifest 计为 unmapped，
不阻止发布。

旧大文件继续由 `backend/precompute_irrigation.py` 生成。该脚本在完成
大文件和区域目录发布后调用运行时构建器；也允许单独运行新构建器，
用于从已完成的离线源重建小产物。

`scripts/build_township_chunks.py` 在本次仍可读取旧大文件作为离线
构建输入；生产运行时不导入或调用该脚本。

## 后端运行时加载

新增专用加载模块，职责限定为：

- 校验并缓存 manifest；
- 读取县级 averages；
- 根据 `countyId` 读取乡镇 averages 分片；
- 读取县级 series；
- 根据 `township_index.json` 定位乡镇 series 分片。

缓存版本使用规范化路径、`mtime_ns` 和文件大小。文件被原子替换后，
下一次请求自动加载新版本。

缓存边界：

- manifest、县级 averages 和县级 series 各缓存一份；
- 乡镇 averages 与源代码 series 分片分别使用最多 64 项的 LRU；
- 返回给调用方的数据不得允许修改共享缓存。

运行时模块不得导入旧大文件路径，也不得调用
`get_irrigation_region_series()`。

## API 行为

### 平均值端点

`GET /api/irrigation/regions/averages`

- `level=county`：直接返回县级 averages 产物。
- `level=township&countyId=...`：规范化县代码并返回对应乡镇分片。
- 缺少乡镇 `countyId` 继续返回 422。

### 明细端点

`GET /api/irrigation/series`

- `level=county`：从县级 series 缓存取目标区域。
- `level=township`：从小型全量索引取得分片名，再读取目标源代码分片。
- summary 继续在请求时按目标 period 计算，舍入和空序列语义不变。
- 不存在的区域或 period 继续返回 404。

### 服务错误

manifest、县级产物或目录损坏时返回 503。区域目录中存在的乡镇缺少
应有分片时也返回 503。错误日志记录相对产物和错误原因，不向客户端
暴露服务器绝对路径。

运行时不回退旧大文件或栅格计算。

## HTTP 与 Nginx 缓存

averages 和 series 的 200 响应增加：

- `Cache-Control: public, max-age=300, stale-while-revalidate=3600`
- 基于产物签名和查询参数的强 `ETag`

收到匹配的 `If-None-Match` 时返回 304，不重新序列化响应体。

Nginx 在通用 `/api/` location 之前增加两个精确匹配 location：

- `/api/irrigation/regions/averages`
- `/api/irrigation/series`

两个 location 复用现有 `tile_cache` zone，并配置：

- 只缓存 GET 和 HEAD；
- 缓存键包含完整请求 URI；
- 只为 200 响应缓存一小时；
- `proxy_cache_lock on`；
- 后端错误不写入缓存；
- 返回 `X-Stats-Cache` 便于生产验收。

422、404 和 503 不缓存。

## 前端加载状态

进入行政统计模式后，县级矢量状态和县级 averages 状态独立：

1. 两个请求仍然并发发起。
2. 县级矢量先完成时立即写入 `countyVector` 并显示县界。
3. averages 完成后写入均值和图例，县界再应用分区颜色。
4. averages 失败时保留县界、统计模式和可重试状态。
5. 退出统计模式时同时清理两类状态。

乡镇下钻继续先确认当前县乡镇矢量可用，再读取该县 averages 分片。
加载提示区分“正在加载行政区边界”和“正在加载统计着色”，不再用
一个全局 Promise 完成状态阻塞地图。

现有请求序号、卸载取消和跨县切换保护保持不变，旧响应不得覆盖新的
县域状态。

## 测试策略

### 构建器测试

- 小型县/乡镇夹具生成预期目录、manifest、均值和明细。
- 相同输入重复生成得到相同业务内容和 SHA。
- 平均值和六级图例与当前算法一致。
- 矢量引用未知序列、同县重复计数、series 重复、损坏序列和数量
  不一致阻止发布。
- 跨县乡镇 ID 可进入多个 averages 分片，但在 series 中只出现一次。
- 无矢量序列进入 series 和 unmapped 审计，不进入 averages。
- 临时目录校验或替换失败时旧正式目录保持可用。

### 后端测试

- averages 和 series 的正常响应、summary、404 与 422 契约不变。
- 运行时测试替换旧大文件读取函数为失败桩，证明请求不会调用它。
- 县级缓存复用，文件替换后自动刷新。
- 乡镇 LRU 不超过 64 个县。
- manifest、县级产物和应存在的乡镇分片缺失或损坏时返回 503。
- `ETag`、304 和 `Cache-Control` 行为正确。
- Nginx 精确 location、缓存键、缓存时长、cache lock 和错误不缓存
  均有配置回归测试。

### 前端测试

- averages 未完成时，已返回的县界立即显示。
- averages 失败时县界和行政统计模式保留。
- averages 成功后应用分区着色和图例。
- 快速切换或退出时旧响应不覆盖新状态。

## 真实数据验收

构建完成后执行独立审计：

1. 新旧数据逐区域比较名称、年度序列和月度序列。
2. 重新计算并比较县级和每县可见乡镇平均值及图例。
3. 校验 2,893 个县和 43,726 个乡镇源序列，最终以真实源计数为准。
4. 校验 43,669 个可见唯一乡镇、46,021 个县-乡镇对、2,308 个跨县
   ID 和 57 个无矢量 ID；最终数量由真实矢量 manifest 与分片审计
   共同确认。
5. 校验每个源序列在 series 中恰好出现一次，每个可见县-乡镇对在
   对应 averages 中恰好出现一次。
6. 校验后端镜像构建上下文不包含旧大文件。

性能验收从新的 Python 进程启动真实 FastAPI TestClient，分别测量：

- 首个县级 averages HTTP 请求；
- 同进程第二次请求；
- 请求前后工作集差值。

验收阈值为冷请求不超过 300 ms、热请求不超过 100 ms、统计数据
工作集增量低于 100 MiB。性能基准作为显式验收命令运行，不放入默认
单元测试，以避免共享 CI 机器的时序波动造成普通测试不稳定。

最后运行后端全量 pytest、前端 Vitest、Oxlint 和生产构建。

## 部署与回滚

部署顺序：

1. 从已校验的大文件生成并审计 `irrigation_runtime/`。
2. 提交运行时产物、构建器、代码和配置。
3. 构建后端镜像并验证旧大文件未进入镜像。
4. 部署新镜像。
5. 请求县级 averages、一个县级 series 和一个乡镇 series。
6. 连续请求同一 averages URL，检查 `X-Stats-Cache` 和延迟。

运行时产物与代码必须在同一镜像版本发布。回滚时整体回滚到上一镜像，
不在新代码中启用旧大文件回退。
