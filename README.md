# 遥感数据展示平台

这是一个面向多源遥感栅格的 Web 展示与空间分析平台。前端使用 React、TypeScript、Vite 和 Leaflet，后端使用 FastAPI、Rasterio、Rio-Tiler 与 TiTiler。

## 当前功能

- 地表土壤湿度（SSM）时序浏览、动态图例、瓦片渲染、点查询和矩形区域统计。
- 蒸散发（ET）与 10 cm、30 cm、60 cm、100 cm 四个土壤深度的数据发现、瓦片渲染和空间查询。
- 年度及 8 天尺度灌溉用水栅格浏览、动态图例和空间查询。
- 县级与乡镇级灌溉行政区下钻、区域平均值着色和预计算时间序列。
- 运行数据就绪探针、超大面积查询保护和可缓存的动态瓦片响应。

## 项目结构

```text
backend/                 FastAPI 应用、路由、栅格服务和 pytest 测试
frontend/                React + TypeScript + Vite 前端和 Vitest 测试
data/metadata/           已跟踪的图层元数据
data/series/             已跟踪的示例/回退时间序列
data/stats/              已跟踪的小型统计种子与单独上传的大型统计文件
data/rasters/            不进入 Git 的运行时栅格
data/vectors/            不进入 Git 的运行时行政区矢量
scripts/                 数据处理及部署数据预检脚本
docs/deployment.md       单服务器上线操作手册
```

## 本地开发

需要 Node.js 22 和 Python 3.12。先复制环境变量示例并安装依赖：

```powershell
Copy-Item .env.example .env
npm run install:all
```

将运行数据放入下文所述目录后，启动前后端：

```powershell
npm run dev
```

前端默认地址为 `http://localhost:5173`，后端默认地址为 `http://localhost:8000`。

## 测试与构建

```powershell
npm test
npm --prefix frontend run lint
npm run build
```

也可以分别运行 `npm run test:backend` 和 `npm run test:frontend`。

## 运行数据不进入 Git

大型栅格、行政区矢量及离线源数据 `data/stats/irrigation_region_series.json` 被明确忽略。栅格和矢量通过 SFTP、rsync 或其他文件传输方式单独上传服务器；大型统计源文件只在构建工作站使用，不需要上传到运行服务器。提交代码前可以确认忽略规则：

```powershell
git check-ignore -v data/stats/irrigation_region_series.json
```

应用需要以下运行时内容：

- `data/rasters/{ssm,et,sm_10cm,sm_30cm,sm_60cm,sm_100cm,irrigation_annual,irrigation_8day}/`
- `data/vectors/irrigation/county/china_county.{shp,shx,dbf}`
- `data/vectors/irrigation/township_by_county/manifest.json` 及县级 GeoJSON 分块
- `data/stats/irrigation_runtime/`（由 Git 跟踪的运行时统计分片）

在拥有大型统计源文件和乡镇矢量分块的构建工作站生成并校验运行时统计：

```powershell
python scripts/build_irrigation_runtime_stats.py
python scripts/build_irrigation_runtime_stats.py --check
```

生成目录 `data/stats/irrigation_runtime/` 随代码发布；服务请求不会读取大型统计源文件。

上传后运行：

```powershell
python scripts/check_deployment_data.py
```

所有必需项有效时命令退出码为 0；缺失时只输出稳定的数据标识，不泄露主机路径。

## 上线

当前配置支持先使用服务器 IP 和 HTTP，之后仅将 `SITE_ADDRESS` 从 `:80` 改为域名即可由 Caddy 自动申请 HTTPS 证书。服务器准备、数据上传、健康检查、备份和回滚步骤见 [部署手册](docs/deployment.md)。

Docker 镜像构建与容器运行验证将在源码和配置确认后单独执行。
