# 基础数据展示页视频入口设计规格

## 目标

在基础数据展示页面（`/base`）左侧功能栏新增一个视频入口，点击后弹出模态窗口播放一段介绍视频。视频文件不进入 Docker 镜像，由宿主机目录挂载提供，更换视频无需重新构建。

## 设计

### 存储与分发

- 宿主机路径 `data/videos/demo.mp4`，沿用仓库既有 `data/` 约定，不新增顶层目录。
- `data/videos/` 加入 `.gitignore`，与 `data/rasters/` 等需单独上传的大数据目录一致。
- `docker-compose.yml` 的 `frontend` 服务增加只读 bind mount：`./data/videos` → `/usr/share/nginx/html/videos`，沿用 `backend` 服务已有的 `read_only: true` + `create_host_path: false` 写法。
- `nginx.conf` 新增 location（置于 `location /assets/` 之后）：

```nginx
location /videos/ {
    root /usr/share/nginx/html;
    try_files $uri =404;
    add_header Cache-Control "public, max-age=86400";
    add_header X-Content-Type-Options "nosniff" always;
}
```

`try_files $uri =404` 是必需的：`location /` 的 `try_files ... /index.html` 会把缺失的视频请求也回退成 HTML，`<video>` 收到 HTML 后静默失败，用户只看到黑框，难以排查。

进度条拖拽依赖 HTTP Range（206），nginx 对静态文件原生支持，无需额外配置。Caddy 与后端不改动。

### 部署前提

以下两条不满足会导致功能整体不可用，在部署时人工确认，不写入代码、不增加启动检查脚本。

1. **文件权限**：frontend 容器镜像为 `nginxinc/nginx-unprivileged`，以 uid 101 运行。宿主机 `data/videos` 需 `755`、mp4 文件需 `644`，否则 nginx 返回 403。rsync 上传时使用 `--chmod=D755,F644`。
2. **编码**：视频必须是 H.264 视频轨 + AAC 音频轨的 mp4。H.265/HEVC 虽扩展名同为 `.mp4`，但 Chrome/Firefox/Edge 默认无法解码。必要时转码：

```bash
ffmpeg -i in.mp4 -c:v libx264 -crf 23 -preset medium -pix_fmt yuv420p \
       -c:a aac -b:a 128k -movflags +faststart out.mp4
```

### 前端组件

- `frontend/src/components/Sidebar.tsx`：新增一个 `sidebar-section`，标题 `🎬 视频演示`，内含一个按钮；props 增加 `onOpenVideo: () => void`，与既有 `onPlayToggle` 同风格。
- `frontend/src/components/VideoModal.tsx`（新增）：原生 `<dialog>` + `<video controls preload="metadata" src="/videos/demo.mp4">`。
- `frontend/src/App.tsx`：`useState` 控制开关，把 `onOpenVideo` 传给 `Sidebar`，在 `MainPage` 内条件渲染 `<VideoModal>`。
- `frontend/src/App.css`：新增 `.video-modal`（宽 `min(80vw, 1100px)`）与 `dialog::backdrop` 半透明黑，沿用既有 overlay 的视觉语言。

选择原生 `<dialog>` 而非 `position: fixed` 自绘浮层，原因是它自带 ESC 关闭、`::backdrop` 遮罩、焦点锁定，以及 top-layer 渲染——后者是硬需求，普通 fixed 层可能被 Leaflet 地图层级覆盖。不引入 react-player / video.js：原生 `<video controls>` 已提供播放、进度、音量、全屏与倍速。

`<dialog>` 原生只提供 ESC 关闭，遮罩点击与关闭按钮需自行补：点击遮罩时事件目标就是 dialog 元素本身，用 `onClick={(e) => e.target === e.currentTarget && onClose()}` 一行处理；关闭按钮调用 `dialog.close()`。`close` 事件统一回调 `onClose`，使 `App.tsx` 的开关状态与 dialog 实际状态保持同步。

视频地址写死为常量 `/videos/demo.mp4`。更换视频需保持文件名不变，否则要改常量并重新构建前端。

### 关闭与错误处理

- 采用条件渲染 `{open && <VideoModal ... />}`，关闭时 `<video>` 从 DOM 移除，立即停止播放与后台缓冲。仅调用 `pause()` 而不卸载元素，浏览器会继续下载剩余内容。
- 监听 `<video>` 的 `error` 事件，显示"视频加载失败，请确认视频文件已正确挂载"。缺少该提示时，权限或编码问题只会表现为一个黑框。

## 测试

- `frontend/src/test/VideoModal.test.tsx`（新增）：验证点击侧边栏入口后 dialog 打开且 `<video>` 存在；关闭后 `<video>` 从文档移除。
- 验证 `<video>` 触发 error 事件时渲染失败提示文案。
- 如 jsdom 29 未实现 `HTMLDialogElement.showModal()`，在 `src/test/setup.ts` 补充最小 polyfill（仅测试夹具，不影响生产代码）。
- 完成后运行前端测试、构建与 lint。

## 验收标准

1. 基础数据展示页左侧功能栏出现"视频演示"入口。
2. 点击后弹出播放窗口，视频可播放、可拖拽进度条。
3. 按 ESC、点击遮罩或关闭按钮均可关闭，且关闭后视频停止播放与下载。
4. 视频文件缺失或无权限时，窗口内显示明确失败提示，而非空白黑框。
5. 更换宿主机 `data/videos/demo.mp4` 后重启容器即生效，无需重新构建镜像。
6. 现有图层切换、透明度、时间轴、空间查询行为不变。
