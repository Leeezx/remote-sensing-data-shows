# 使用阿里云 ACR 部署网站

本方案由 GitHub Actions 构建镜像，轻量应用服务器只从阿里云 ACR 拉取镜像。服务器不在本地构建，也不需要访问 Docker Hub。

## 1. 发布镜像

1. 打开 GitHub 仓库的 **Actions** 页面。
2. 选择 **Publish images to ACR**。
3. 点击 **Run workflow**，分支选择 `main`，再次点击 **Run workflow**。
4. 等待所有步骤成功，记录这次提交对应的不可变标签。标签格式为 `sha-` 加提交 SHA 的前 12 位，例如：

```dotenv
IMAGE_TAG=sha-0123456789ab
```

工作流同时发布 `latest`，但生产部署应优先使用上述不可变标签，便于精确回滚。

## 2. 更新服务器代码并确认数据盘

登录服务器后执行：

```bash
cd /opt/remote-sensing
git status --short
git pull --ff-only origin main
findmnt /opt/remote-sensing/data
```

执行 `git pull` 前，`git status --short` 应无输出。数据目录应继续指向 `/dev/vdb1[/remote-sensing/data]`。

## 3. 登录 ACR

使用 ACR 的登录用户名；密码只在 Docker 的交互式提示中输入，不要写进命令或 `.env`：

```bash
read -rp 'ACR username: ' ACR_USERNAME
sudo docker login \
  crpi-ax05xaa8wxdezs5y.cn-beijing.personal.cr.aliyuncs.com \
  --username "$ACR_USERNAME"
unset ACR_USERNAME
```

看到 `Login Succeeded` 后继续。因为后续 Docker 命令使用 `sudo`，这里也必须使用 `sudo docker login`，以便 root 用户保存拉取凭据。

## 4. 配置镜像坐标

编辑 `/opt/remote-sensing/.env`，保留原有运行参数，并加入以下三行。将示例标签替换成第 1 步记录的实际标签：

```dotenv
ACR_REGISTRY=crpi-ax05xaa8wxdezs5y.cn-beijing.personal.cr.aliyuncs.com
ACR_NAMESPACE=rs-data-show
IMAGE_TAG=sha-0123456789ab
```

`.env` 中不保存 ACR 密码。继续保持权限为仅当前用户可读写：

```bash
chmod 600 /opt/remote-sensing/.env
```

## 5. 创建服务器专用 Compose 覆盖文件

创建 `/opt/remote-sensing/docker-compose.acr.yml`：

```yaml
services:
  edge:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/edge:${IMAGE_TAG:-latest}
  frontend:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/frontend:${IMAGE_TAG:-latest}
  backend:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/backend:${IMAGE_TAG:-latest}
```

这个文件只改变三个服务的镜像地址；端口、健康检查、数据挂载和依赖关系仍来自原来的 `docker-compose.yml`。它已被 Git 忽略，可用下面的命令确认：

```bash
cd /opt/remote-sensing
git status --short
git check-ignore -v docker-compose.acr.yml
```

## 6. 验证、拉取并启动

以后所有 Compose 命令都必须同时指定基础文件和 ACR 覆盖文件：

```bash
cd /opt/remote-sensing

sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  config --quiet

sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  config --images

sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  pull

sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  up -d --no-build --pull never
```

`config --images` 输出的三个地址都应以 ACR 登录域名开头。`--no-build --pull never` 保证启动阶段只使用刚刚拉取的镜像。

不要只运行基础 `docker-compose.yml`，否则 Compose 会重新使用其中的上游镜像或本地构建配置。

## 7. 验证服务

```bash
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  ps

sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  logs --tail=100 backend frontend edge

curl -fsS http://127.0.0.1/api/ready
curl -I http://127.0.0.1/
```

再确认服务器数据未受影响：

```bash
findmnt /opt/remote-sensing/data
du -sh /opt/remote-sensing/data/rasters
test -f /opt/remote-sensing/data/vectors/irrigation/county/china_county.shp \
  && echo 'county vector OK'
```

预期结果：三个容器均运行或健康，`/api/ready` 成功，首页返回 HTTP 响应，栅格目录仍约为 45 GB。

## 8. 更新与回滚

发布新版本后，将 `.env` 中的 `IMAGE_TAG` 改成新的 `sha-<12>` 标签，然后重复第 6 节的 `pull` 和 `up` 命令。

回滚时，将 `IMAGE_TAG` 恢复为上一个已验证的标签，再重复相同命令。不可变标签不会随新的发布而改变，因此回滚不需要重新构建镜像。

## 9. 公网访问

在轻量应用服务器控制台的防火墙中放行入方向 TCP `80`。配置域名和 HTTPS 后再放行 TCP `443`。不要向公网开放后端 `8000` 或前端内部端口 `8080`。

最后从服务器之外访问公网 IP 或域名，确认首页、API 和至少一个栅格请求均正常。
