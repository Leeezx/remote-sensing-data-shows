# 灌溉行政区统计序列缓存 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在同一后端进程中复用已解析的灌溉行政区统计 JSON，并在源文件发生变化时自动刷新。

**Architecture:** 在 `backend.data_loader` 内只为 `get_irrigation_region_series()` 保存模块级数据缓存和文件状态签名。每次调用先比较源文件的 `st_mtime_ns` 与 `st_size`；一致时返回缓存，不一致时在锁内重新读取。现有路由与前端接口不变。

**Tech Stack:** Python 3、FastAPI、pytest、标准库 `threading` 和 `pathlib`。

## Global Constraints

- 保持 `GET /api/irrigation/series` 与 `GET /api/irrigation/regions/averages` 的接口和响应结构不变。
- 仅缓存 `data/stats/irrigation_region_series.json`；通用 `_load_json` 保持每次读取的既有语义。
- 使用文件修改时间（纳秒）和文件大小作为自动失效条件。
- 不引入第三方缓存、数据库或跨进程共享状态。

---

### Task 1: 为灌溉行政区序列加载器增加可自动失效的缓存

**Files:**
- Modify: `backend/data_loader.py:3-5, 29-34, 148-150`
- Modify: `backend/tests/test_irrigation.py:1-8, after test_irrigation_region_catalog_contains_both_supported_levels`

**Interfaces:**
- Consumes: `PROJECT_ROOT: Path` 与 `_load_json(relative_path: str) -> Any`。
- Produces: `get_irrigation_region_series() -> dict`，在源文件未变化时返回同一已解析对象；源文件变化时返回新解析对象。

- [ ] **Step 1: 写入缓存命中的失败测试**

在 `backend/tests/test_irrigation.py` 的已有 `data_loader` 导入后添加测试：

```python
def test_irrigation_region_series_reuses_cached_json(monkeypatch, tmp_path):
    stats_dir = tmp_path / "data" / "stats"
    stats_dir.mkdir(parents=True)
    source_path = stats_dir / "irrigation_region_series.json"
    source_path.write_text('{"version": 1}', encoding="utf-8")
    monkeypatch.setattr(data_loader, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(data_loader, "_IRRIGATION_REGION_SERIES_CACHE", None)
    monkeypatch.setattr(data_loader, "_IRRIGATION_REGION_SERIES_SIGNATURE", None)

    original_load_json = data_loader._load_json
    calls = 0

    def count_loads(relative_path):
        nonlocal calls
        calls += 1
        return original_load_json(relative_path)

    monkeypatch.setattr(data_loader, "_load_json", count_loads)

    first = data_loader.get_irrigation_region_series()
    second = data_loader.get_irrigation_region_series()

    assert first == {"version": 1}
    assert second is first
    assert calls == 1
```

- [ ] **Step 2: 运行测试并确认其因未定义缓存状态而失败**

Run: `pytest backend/tests/test_irrigation.py::test_irrigation_region_series_reuses_cached_json -v`

Expected: FAIL，原因是 `backend.data_loader` 中尚未定义 `_IRRIGATION_REGION_SERIES_CACHE`。

- [ ] **Step 3: 写入源文件变化时刷新的失败测试**

紧接着添加：

```python
def test_irrigation_region_series_refreshes_when_file_changes(monkeypatch, tmp_path):
    stats_dir = tmp_path / "data" / "stats"
    stats_dir.mkdir(parents=True)
    source_path = stats_dir / "irrigation_region_series.json"
    source_path.write_text('{"version": 1}', encoding="utf-8")
    monkeypatch.setattr(data_loader, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(data_loader, "_IRRIGATION_REGION_SERIES_CACHE", None)
    monkeypatch.setattr(data_loader, "_IRRIGATION_REGION_SERIES_SIGNATURE", None)

    assert data_loader.get_irrigation_region_series() == {"version": 1}

    source_path.write_text('{"version": 200}', encoding="utf-8")

    assert data_loader.get_irrigation_region_series() == {"version": 200}
```

- [ ] **Step 4: 运行刷新测试并确认其在现有实现下失败**

Run: `pytest backend/tests/test_irrigation.py::test_irrigation_region_series_refreshes_when_file_changes -v`

Expected: FAIL，原因是缓存状态尚未定义。

- [ ] **Step 5: 实现最小缓存逻辑**

在 `backend/data_loader.py` 的导入区加入：

```python
from threading import Lock
```

在 `_IRRIGATION_8DAY_FILE` 定义之后加入：

```python
_IRRIGATION_REGION_SERIES_PATH = Path("data/stats/irrigation_region_series.json")
_IRRIGATION_REGION_SERIES_CACHE: dict | None = None
_IRRIGATION_REGION_SERIES_SIGNATURE: tuple[int, int] | None = None
_IRRIGATION_REGION_SERIES_LOCK = Lock()
```

将 `get_irrigation_region_series()` 替换为：

```python
def get_irrigation_region_series() -> dict:
    """Return cached precomputed irrigation totals, refreshing after file changes."""
    global _IRRIGATION_REGION_SERIES_CACHE
    global _IRRIGATION_REGION_SERIES_SIGNATURE

    source_path = PROJECT_ROOT / _IRRIGATION_REGION_SERIES_PATH
    stat = source_path.stat()
    signature = (stat.st_mtime_ns, stat.st_size)
    if _IRRIGATION_REGION_SERIES_SIGNATURE == signature:
        return _IRRIGATION_REGION_SERIES_CACHE  # type: ignore[return-value]

    with _IRRIGATION_REGION_SERIES_LOCK:
        stat = source_path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        if _IRRIGATION_REGION_SERIES_SIGNATURE != signature:
            _IRRIGATION_REGION_SERIES_CACHE = _load_json(
                str(_IRRIGATION_REGION_SERIES_PATH)
            )
            _IRRIGATION_REGION_SERIES_SIGNATURE = signature
        return _IRRIGATION_REGION_SERIES_CACHE  # type: ignore[return-value]
```

- [ ] **Step 6: 运行新增缓存测试并确认通过**

Run: `pytest backend/tests/test_irrigation.py::test_irrigation_region_series_reuses_cached_json backend/tests/test_irrigation.py::test_irrigation_region_series_refreshes_when_file_changes -v`

Expected: PASS（2 passed）。

- [ ] **Step 7: 验证通用 JSON 读取器未被缓存行为改变**

添加测试：

```python
def test_load_json_remains_uncached(monkeypatch, tmp_path):
    source_path = tmp_path / "sample.json"
    source_path.write_text('{"version": 1}', encoding="utf-8")
    monkeypatch.setattr(data_loader, "PROJECT_ROOT", tmp_path)

    assert data_loader._load_json("sample.json") == {"version": 1}
    source_path.write_text('{"version": 2}', encoding="utf-8")

    assert data_loader._load_json("sample.json") == {"version": 2}
```

- [ ] **Step 8: 运行针对性测试与完整后端测试**

Run: `pytest backend/tests/test_irrigation.py -v`

Expected: PASS，且现有县级和乡镇级序列接口测试仍通过。

Run: `pytest backend/tests/ -v`

Expected: PASS，未引入回归。

- [ ] **Step 9: 提交实现**

```bash
git add backend/data_loader.py backend/tests/test_irrigation.py
git commit -m "perf: cache irrigation region series"
```
