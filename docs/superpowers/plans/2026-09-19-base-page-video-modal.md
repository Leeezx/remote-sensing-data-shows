# 基础数据展示页视频入口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在基础数据展示页面（`/base`）左侧功能栏增加一个视频入口，点击后弹出模态窗口播放一段由宿主机目录挂载提供的视频。

**Architecture:** 前端用原生 `<dialog>` + `<video controls>` 实现播放窗口，不引入播放器库；视频文件由 `docker-compose.yml` 只读 bind mount 进 frontend 容器的 `/usr/share/nginx/html/videos`，由 nginx 新增的 `location /videos/` 直接提供服务（Range 请求由 nginx 原生支持）。后端与 Caddy 不参与。

**Tech Stack:** React 19 + TypeScript、vitest + @testing-library/react + jsdom、nginx 1.28（`nginxinc/nginx-unprivileged`）、Docker Compose、pytest + PyYAML。

设计依据：`docs/superpowers/specs/2026-09-19-base-page-video-modal-design.md`

## Global Constraints

- 不引入任何新依赖（不加 react-player / video.js 等播放器库）。
- 视频地址为常量 `/videos/demo.mp4`。
- frontend 容器镜像为 `nginxinc/nginx-unprivileged:1.28-alpine`，以 uid 101 运行。
- `nginx.conf` 中 `add_header X-Content-Type-Options "nosniff" always;` 等三条安全头各出现 **5 次**，`src/test/` 现有部署测试对此有断言，不得改变该计数。
- `tsconfig.app.json` 启用了 `noUnusedLocals` 与 `noUnusedParameters`，`npm run build` 会因未使用的变量/导入失败。
- 前端测试基线：11 个文件、121 个测试全部通过；后端 `test_deployment_config.py` 15 个测试全部通过。

---

### Task 1: VideoModal 组件与 jsdom dialog polyfill

**Files:**
- Create: `frontend/src/components/VideoModal.tsx`
- Create: `frontend/src/test/VideoModal.test.tsx`
- Modify: `frontend/src/test/setup.ts`
- Modify: `frontend/src/App.css`（在 `/* ===== Responsive ===== */` 之前插入）

**Interfaces:**
- Consumes: 无（本任务是起点）
- Produces:
  - `frontend/src/components/VideoModal.tsx` 默认导出 `VideoModal`，props 为 `{ onClose: () => void }`。挂载时调用 `dialog.showModal()`；遮罩点击、关闭按钮、ESC 三种路径最终都会调用 `onClose`。
  - 常量 `VIDEO_SRC = '/videos/demo.mp4'`（同文件命名导出，供后续任务与测试引用）。

- [ ] **Step 1: 在 `frontend/src/test/setup.ts` 补 dialog polyfill**

jsdom 29.1.1 的 `HTMLDialogElement.prototype.showModal` 与 `close` 均为 `undefined`（已实测），不补则组件测试无法运行。

```ts
import '@testing-library/jest-dom'

// jsdom 29 提供 HTMLDialogElement 但不实现 showModal/close，
// 这里补上被测组件依赖的最小行为。仅测试夹具，不影响生产代码。
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute('open')
    this.dispatchEvent(new Event('close'))
  }
}
```

- [ ] **Step 2: 写失败的测试**

创建 `frontend/src/test/VideoModal.test.tsx`：

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import VideoModal, { VIDEO_SRC } from '../components/VideoModal'

function dialog(): HTMLDialogElement {
  return document.querySelector('dialog') as HTMLDialogElement
}

describe('VideoModal', () => {
  it('opens as a modal dialog and renders the player', () => {
    render(<VideoModal onClose={vi.fn()} />)

    expect(dialog()).toHaveAttribute('open')
    expect(dialog()).toHaveAttribute('aria-label', '视频演示')
    const player = dialog().querySelector('video') as HTMLVideoElement
    expect(player).toHaveAttribute('src', VIDEO_SRC)
    expect(player).toHaveAttribute('controls')
    expect(player).toHaveAttribute('preload', 'metadata')
  })

  it('calls onClose when the close button is clicked', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<VideoModal onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: '关闭' }))

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when the backdrop is clicked', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<VideoModal onClose={onClose} />)

    await user.click(dialog())

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('stays open when the dialog content is clicked', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<VideoModal onClose={onClose} />)

    await user.click(screen.getByRole('heading', { name: '视频演示' }))

    expect(onClose).not.toHaveBeenCalled()
  })

  it('shows a failure message instead of the player when the video errors', () => {
    render(<VideoModal onClose={vi.fn()} />)

    fireEvent.error(dialog().querySelector('video') as HTMLVideoElement)

    expect(screen.getByRole('alert')).toHaveTextContent('视频加载失败')
    expect(dialog().querySelector('video')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/test/VideoModal.test.tsx`
Expected: FAIL —— `Failed to resolve import "../components/VideoModal"`。

- [ ] **Step 4: 实现组件**

创建 `frontend/src/components/VideoModal.tsx`：

```tsx
import { useEffect, useRef, useState } from 'react'

export const VIDEO_SRC = '/videos/demo.mp4'

interface VideoModalProps {
  onClose: () => void
}

export default function VideoModal({ onClose }: VideoModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    dialogRef.current?.showModal()
  }, [])

  return (
    <dialog
      ref={dialogRef}
      className="video-modal"
      aria-label="视频演示"
      onClose={onClose}
      onClick={(e) => {
        // 点击遮罩时事件目标就是 dialog 自身，点击内容区则是子元素。
        if (e.target === e.currentTarget) dialogRef.current?.close()
      }}
    >
      <div className="video-modal-head">
        <h2>视频演示</h2>
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => dialogRef.current?.close()}
        >
          关闭
        </button>
      </div>
      {failed ? (
        <p role="alert" className="video-modal-error">
          视频加载失败，请确认视频文件已正确挂载。
        </p>
      ) : (
        <video
          className="video-modal-player"
          src={VIDEO_SRC}
          controls
          preload="metadata"
          onError={() => setFailed(true)}
        />
      )}
    </dialog>
  )
}
```

说明：ESC 触发的原生 `cancel`/`close` 最终会触发 dialog 的 `close` 事件，React 19 已支持 `<dialog onClose>`（已验证运行时会触发），因此三条关闭路径统一收敛到 `onClose` 一个回调，`App.tsx` 的状态不会与 dialog 实际状态脱节。

- [ ] **Step 5: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/test/VideoModal.test.tsx`
Expected: PASS，5 个测试通过。

- [ ] **Step 6: 加样式**

在 `frontend/src/App.css` 的 `/* ===== Responsive ===== */` 之前插入：

```css
/* ===== Video Modal ===== */

.video-modal {
  padding: 0;
  border: none;
  border-radius: 6px;
  width: min(80vw, 1100px);
  max-width: 1100px;
  background: #fff;
}

.video-modal::backdrop {
  background: rgba(0, 0, 0, 0.6);
}

.video-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid #e0e0e0;
}

.video-modal-head h2 {
  font-size: 14px;
  margin: 0;
}

.video-modal-player {
  display: block;
  width: 100%;
  max-height: 70vh;
  background: #000;
}

.video-modal-error {
  padding: 32px 16px;
  text-align: center;
  color: #c5221f;
  font-size: 14px;
  margin: 0;
}
```

`padding: 0` 是功能性的，不只是外观：若保留 UA 默认 padding，点击 padding 区域的事件目标会是 dialog 自身，会误触发遮罩关闭逻辑。

- [ ] **Step 7: 运行完整前端测试与构建**

Run: `cd frontend && npm test && npm run build`
Expected: 12 个测试文件、126 个测试通过；`tsc -b && vite build` 无错误。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/components/VideoModal.tsx frontend/src/test/VideoModal.test.tsx frontend/src/test/setup.ts frontend/src/App.css
git commit -m "feat: add video modal player component"
```

---

### Task 2: 侧边栏视频入口与 App 接线

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/test/App.test.tsx`

**Interfaces:**
- Consumes: Task 1 的 `VideoModal`（默认导出，props `{ onClose: () => void }`）与 `VIDEO_SRC`。
- Produces: `Sidebar` 新增必需 prop `onOpenVideo: () => void`；侧边栏出现一个可访问名为 `播放介绍视频` 的按钮。

- [ ] **Step 1: 写失败的测试**

在 `frontend/src/test/App.test.tsx` 的 `describe('App', () => { ... })` 内、最后一个 `it(...)` 之后，追加两个测试：

```tsx
  it('opens the video modal from the sidebar entry', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '播放介绍视频' }))

    const dialog = document.querySelector('dialog')
    expect(dialog).toHaveAttribute('open')
    expect(dialog?.querySelector('video')).toHaveAttribute('src', '/videos/demo.mp4')
  })

  it('removes the video modal from the DOM when it closes', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '播放介绍视频' }))
    await user.click(screen.getByRole('button', { name: '关闭' }))

    expect(document.querySelector('dialog')).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/test/App.test.tsx`
Expected: FAIL —— `Unable to find role="button" and name "播放介绍视频"`。

- [ ] **Step 3: 给 Sidebar 加入口**

在 `frontend/src/components/Sidebar.tsx` 中：

(a) 在 `SidebarProps` 接口里，`onPlayToggle: () => void` 之后加一行：

```ts
  onOpenVideo: () => void
```

(b) 在函数参数解构中，`onPlayToggle,` 之后加一行：

```ts
  onOpenVideo,
```

(c) 在「空间查询」section 结束之后、「图层信息」条件块之前插入：

```tsx
      {/* Video */}
      <section className="sidebar-section">
        <h3>🎬 视频演示</h3>
        <button className="btn" onClick={onOpenVideo}>
          播放介绍视频
        </button>
      </section>
```

- [ ] **Step 4: 在 App 中接线**

在 `frontend/src/App.tsx` 中：

(a) 顶部 import 区，`import Legend from './components/Legend'` 之后加（与其它 components 导入成组）：

```tsx
import VideoModal from './components/VideoModal'
```

(b) 在 `MainPage` 里，`const [tileLoading, setTileLoading] = useState(false)` 之后加：

```tsx
  // Video modal
  const [videoOpen, setVideoOpen] = useState(false)
```

(c) 给 `<Sidebar ... />` 传参，在 `onPlayToggle={handlePlayToggle}` 之后加一行：

```tsx
            onOpenVideo={() => setVideoOpen(true)}
```

(d) 在 `MainPage` 返回的 `<main className="app-main">` 内、`</main>` 之前加：

```tsx
        {videoOpen && <VideoModal onClose={() => setVideoOpen(false)} />}
```

条件渲染是刻意的：关闭时 `<video>` 整个从 DOM 移除，立即停止播放与后台缓冲；只调 `pause()` 不卸载元素，浏览器会继续下载剩余内容。

- [ ] **Step 5: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/test/App.test.tsx`
Expected: PASS，原有测试与新增 2 个测试全部通过。

- [ ] **Step 6: 运行完整前端测试与构建**

Run: `cd frontend && npm test && npm run build`
Expected: 12 个测试文件、128 个测试通过；构建无错误。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/Sidebar.tsx frontend/src/App.tsx frontend/src/test/App.test.tsx
git commit -m "feat: add video entry to base page sidebar"
```

---

### Task 3: nginx 视频路由与 Docker 挂载

**Files:**
- Modify: `backend/tests/test_deployment_config.py`
- Modify: `nginx.conf`
- Modify: `docker-compose.yml`
- Modify: `.gitignore`
- Modify: `docs/deployment.md`

**Interfaces:**
- Consumes: Task 1 中约定的 URL 路径 `/videos/demo.mp4`。
- Produces: `/videos/<file>` 由 nginx 从挂载目录提供，文件缺失时返回 404 而非 SPA 首页。

- [ ] **Step 1: 写失败的测试**

在 `backend/tests/test_deployment_config.py` 末尾追加。注意 `nginx_location_block` 已在该文件顶部定义，直接复用：

```python
def test_frontend_serves_videos_from_a_read_only_bind_mount():
    frontend_volumes = compose()["services"]["frontend"]["volumes"]

    assert {
        "type": "bind",
        "source": "./data/videos",
        "target": "/usr/share/nginx/html/videos",
        "read_only": True,
        "bind": {"create_host_path": False},
    } in frontend_volumes


def test_nginx_serves_videos_without_the_spa_fallback():
    nginx = (ROOT / "nginx.conf").read_text(encoding="utf-8")

    block = nginx_location_block(nginx, "/videos/")

    assert "root /usr/share/nginx/html;" in block
    assert "try_files $uri =404;" in block
    assert "index.html" not in block
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest backend/tests/test_deployment_config.py -q`
Expected: FAIL —— 2 个新测试失败（`ValueError: substring not found` 与断言失败），原有 15 个仍通过。

- [ ] **Step 3: 改 `nginx.conf`**

在 `location /assets/ { ... }` 块之后插入：

```nginx
    location /videos/ {
        root /usr/share/nginx/html;
        try_files $uri =404;
    }
```

`try_files $uri =404` 是必需的：`location /` 的 `try_files ... /index.html` 会把缺失的视频请求回退成 HTML，`<video>` 收到 HTML 后静默失败，只显示黑框。

该块刻意不写 `add_header`：nginx 的 `add_header` 一旦在某一层出现，上一层的全部不再继承。加了缓存头就必须重复服务级的 `X-Frame-Options`、`X-Content-Type-Options`、`Referrer-Policy` 三条，会让现有测试的计数断言（各 5 次）失败；而 nginx 对静态文件默认发送 `Last-Modified`/`ETag` 并支持协商缓存，对会被替换的视频文件正是合适的策略。

- [ ] **Step 4: 改 `docker-compose.yml`**

在 `frontend` 服务的 `volumes` 列表中，`nginx_tile_cache` 那一项之后追加：

```yaml
      - type: bind
        source: ./data/videos
        target: /usr/share/nginx/html/videos
        read_only: true
        bind:
          create_host_path: false
```

`create_host_path: false` 与 `backend` 服务的写法一致：宿主机目录必须预先存在，避免路径拼写错误时静默创建空目录。

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest backend/tests/test_deployment_config.py -q`
Expected: PASS，17 个测试通过。

- [ ] **Step 6: 忽略大数据目录**

在 `.gitignore` 的 `# Large data files (local only)` 段落中，`data/rasters/` 之前加一行：

```
data/videos/
```

- [ ] **Step 7: 更新部署手册**

在 `docs/deployment.md` 第 2 节的 `mkdir -p` 列表中，`data/stats` 之前加一行 `  data/videos \`，使该段成为：

```bash
mkdir -p \
  data/rasters/{ssm,et,sm_10cm,sm_30cm,sm_60cm,sm_100cm,irrigation_annual,irrigation_8day} \
  data/vectors/irrigation/county \
  data/vectors/irrigation/township_by_county \
  data/videos \
  data/stats
```

并在第 3 节「单独上传运行数据」的 rsync 示例之后追加一段：

````markdown
### 视频文件

基础数据展示页的视频入口读取 `data/videos/demo.mp4`。上传时注意两点：

```bash
rsync -av --chmod=D755,F644 data/videos/ user@server:/opt/remote-sensing/app/data/videos/
```

1. **权限**：frontend 容器以 uid 101（`nginx-unprivileged`）运行。目录需为 `755`、文件需为 `644`，否则 nginx 返回 403。用 rsync 时带上 `--chmod=D755,F644`。
2. **编码**：必须是 H.264 视频轨 + AAC 音频轨的 mp4。H.265/HEVC 的文件扩展名同样是 `.mp4`，但 Chrome/Firefox/Edge 默认无法解码。用 `ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=nw=1 demo.mp4` 确认；需要转码时：

```bash
ffmpeg -i in.mp4 -c:v libx264 -crf 23 -preset medium -pix_fmt yuv420p \
       -c:a aac -b:a 128k -movflags +faststart data/videos/demo.mp4
```

验证服务是否正常（应返回 200，403 表示权限问题，404 表示文件未挂载到位）：

```bash
docker compose exec frontend wget -S -O /dev/null http://127.0.0.1:8080/videos/demo.mp4
```
````

- [ ] **Step 8: 运行完整后端测试**

Run: `python -m pytest backend/tests/ -q`
Expected: 全部通过（视频相关改动只影响 `test_deployment_config.py`，其余测试不应回归）。

- [ ] **Step 9: 提交**

```bash
git add backend/tests/test_deployment_config.py nginx.conf docker-compose.yml .gitignore docs/deployment.md
git commit -m "feat: serve base page video from a mounted directory"
```

---

## 人工验收（需真实视频文件，本计划不自动化）

以下步骤需要一份满足 H.264 + AAC 且体积合适的 mp4，且需要 Docker 环境：

1. 将视频放到宿主机 `data/videos/demo.mp4`，确认权限为 `644`、目录为 `755`。
2. `docker compose up -d --build frontend`。
3. 执行 `docker compose exec frontend wget -S -O /dev/null http://127.0.0.1:8080/videos/demo.mp4`，确认返回 `200`。
4. 浏览器打开基础数据展示页，点击左侧「🎬 视频演示」→「播放介绍视频」。
5. 确认视频可播放，且**拖动进度条能跳转**（这验证 Range/206 生效）。
6. 按 ESC、点击遮罩、点击「关闭」三种方式各关闭一次，确认每次都彻底关闭且声音停止。
7. 打开浏览器开发者工具 Network 面板，关闭窗口后确认没有持续的视频分段下载请求。
8. 临时把 `data/videos/demo.mp4` 改名为其他名字并重启 frontend 容器，确认窗口内显示「视频加载失败，请确认视频文件已正确挂载。」而不是空白黑框；验证后改回。
