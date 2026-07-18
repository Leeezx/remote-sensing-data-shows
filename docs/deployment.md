# 单服务器部署手册

本文档适用于一台 Linux 服务器上的 Caddy、Nginx 前端和 FastAPI 后端。当前没有域名时先使用 IP + HTTP；域名解析完成后再启用自动 HTTPS。

## 1. 服务器与端口准备

建议使用 64 位 Linux、Docker Engine 与 Docker Compose v2。防火墙和云安全组先开放 TCP 80；准备启用域名后再开放 TCP 443。后端 8000 和前端 8080 不应对公网开放。

```bash
docker --version
docker compose version
sudo ss -lntp | grep -E ':(80|443)\b' || true
```

只有 Caddy 服务发布主机端口。Nginx 与 FastAPI 仅在 Compose 内部网络通信。

## 2. 获取代码与创建数据目录

```bash
sudo mkdir -p /opt/remote-sensing
sudo chown "$USER":"$USER" /opt/remote-sensing
git clone <repository-url> /opt/remote-sensing/app
cd /opt/remote-sensing/app

mkdir -p \
  data/rasters/{ssm,et,sm_10cm,sm_30cm,sm_60cm,sm_100cm,irrigation_annual,irrigation_8day} \
  data/vectors/irrigation/county \
  data/vectors/irrigation/township_by_county \
  data/stats
```

Compose 使用 `create_host_path: false`，因此这些目录必须在启动前存在；这可以防止路径拼写错误时静默创建空目录。

## 3. 单独上传运行数据

大型数据不存放在 Git。可以从本地通过 rsync 上传：

```bash
rsync -av --info=progress2 data/rasters/ user@server:/opt/remote-sensing/app/data/rasters/
rsync -av --info=progress2 data/vectors/ user@server:/opt/remote-sensing/app/data/vectors/
rsync -av --info=progress2 data/stats/irrigation_region_series.json \
  user@server:/opt/remote-sensing/app/data/stats/
```

Windows 环境也可以使用 SFTP 客户端，目标目录保持一致。县级 Shapefile 至少要同时上传 `.shp`、`.shx` 和 `.dbf`；乡镇分块目录必须包含 `manifest.json`。

## 4. 配置与数据预检

Windows 本地可执行：

```powershell
Copy-Item .env.example .env
python scripts/check_deployment_data.py
```

Linux 服务器执行：

```bash
cp .env.example .env
python3 scripts/check_deployment_data.py
```

看到 `Deployment data ready` 后再启动。没有域名时保持：

```dotenv
SITE_ADDRESS=:80
UVICORN_WORKERS=1
GDAL_CACHEMAX=256
MAX_AREA_QUERY_PIXELS=4000000
ENABLE_API_DOCS=false
```

单工作进程是有意的默认值：栅格目录和行政统计会占用较多内存。不要在没有观测实际内存峰值前增加工作进程。

## 5. 启动与检查

首次启动命令将在单独的 Docker 验证阶段确认。确认后使用：

```bash
docker compose up -d --build
docker compose ps
```

后端就绪检查有 120 秒启动宽限期。通过服务器 IP 验证：

```bash
curl -fsS http://SERVER_IP/api/health
curl -fsS http://SERVER_IP/api/ready
curl -fsS http://SERVER_IP/api/layers
curl -fsS 'http://SERVER_IP/api/irrigation/regions/averages?level=county'
```

预期 `/api/health` 返回 `status=ok`，`/api/ready` 返回 `status=ready`。县级平均值响应应包含 `averages` 和 6 个 `legend` 色阶。

## 6. 日志与资源观察

```bash
docker compose logs --tail=200 edge frontend backend
docker compose logs -f backend
docker stats
```

若后端接近内存上限，优先保持 `UVICORN_WORKERS=1`，并逐步降低 `GDAL_CACHEMAX`。只有在代表性查询压测后仍有足够余量时，才逐个增加工作进程。

## 7. 数据与缓存备份

运行数据目录必须纳入服务器备份；`backend_cache` 是可再生成缓存，但备份可以缩短恢复时间。Caddy 卷保存证书与配置状态。

```bash
tar -C /opt/remote-sensing/app -czf remote-sensing-data-$(date +%F).tgz \
  data/rasters data/vectors data/stats

docker run --rm -v remote-sensing_backend_cache:/source:ro \
  -v "$PWD":/backup alpine \
  tar -C /source -czf /backup/backend-cache-$(date +%F).tgz .
```

实际 Compose 卷名前缀由项目目录或 `COMPOSE_PROJECT_NAME` 决定，可先用 `docker volume ls` 确认。

## 8. 代码更新与回滚

更新前记录当前提交：

```bash
git rev-parse HEAD
git fetch origin
git switch main
git pull --ff-only
python3 scripts/check_deployment_data.py
docker compose up -d --build
```

若新版本异常，切回已记录的提交并重建；数据目录和命名卷不会随 Git 切换删除：

```bash
git switch --detach <known-good-commit>
docker compose up -d --build
curl -fsS http://SERVER_IP/api/ready
```

不要使用 `docker compose down -v`，除非明确要删除缓存和 Caddy 状态卷。

## 9. 域名与自动 HTTPS

域名购买并完成 DNS A/AAAA 记录后，确认 80 和 443 都可从公网访问，将 `.env` 改为：

```dotenv
SITE_ADDRESS=maps.example.com
```

然后重新加载边缘服务：

```bash
docker compose up -d edge
docker compose logs --tail=100 edge
curl -I https://maps.example.com/api/health
```

Caddy 会自动申请和续期证书。不要删除 `caddy_data` 卷，否则证书状态会丢失。
