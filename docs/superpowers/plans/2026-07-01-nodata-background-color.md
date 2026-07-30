# NoData Semi-Transparent Mask Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill NoData pixels with a configurable semi-transparent color instead of full transparency, so the base map underneath is subdued rather than fully exposed.

**Architecture:** Add an optional `nodata_color` parameter to `colorize()`. When supplied, the entire RGBA array is initialized with that color; valid pixels overwrite it with computed colors and alpha=255. `_render_ssm_tile()` reads optional `nodataColor`/`nodataOpacity` from layer metadata and passes the parsed tuple to `colorize()`. Defaults to `#e8e8e8` at 50% opacity.

**Tech Stack:** Python 3, NumPy, pytest, rasterio, rio-tiler.

---

## File map

- Modify `backend/raster_rendering.py:56-68`: add `nodata_color` parameter to `colorize()`
- Modify `backend/tests/test_raster_rendering.py`: add tests for nodata_color behavior
- Modify `backend/routers/tiles.py:43-55`: read layer config, parse, pass to colorize
- Modify `backend/tests/test_tiles.py`: add test for nodata color parsing and passthrough

---

### Task 1: Add `nodata_color` parameter to `colorize()`

**Files:**
- Modify: `backend/raster_rendering.py:56-68`
- Modify: `backend/tests/test_raster_rendering.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `colorize(values, legend, source_mask=None, nodata=None, nodata_color=None)` — nodata_color is `tuple[R,G,B,A] | None`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_raster_rendering.py`:

```python
def test_colorize_fills_nodata_pixels_with_nodata_color():
    values = np.array([[0.1, 0.5, np.nan]], dtype=float)
    source_mask = np.array([[255, 255, 255]], dtype=np.uint8)
    legend = [
        {"value": 0.0, "color": "#ff0000"},
        {"value": 1.0, "color": "#0000ff"},
    ]
    nodata_color = (100, 150, 200, 80)

    rgba = colorize(values, legend, source_mask=source_mask, nodata_color=nodata_color)

    # Valid pixels get computed color, not nodata_color
    assert tuple(rgba[0, 0]) != nodata_color
    assert rgba[0, 0, 3] == 255
    # Invalid pixel gets nodata_color
    assert tuple(rgba[0, 2]) == nodata_color


def test_colorize_without_nodata_color_keeps_invalid_pixels_transparent():
    values = np.array([[0.1, np.nan]], dtype=float)
    legend = [{"value": 0.0, "color": "#ff0000"}, {"value": 1.0, "color": "#0000ff"}]

    rgba = colorize(values, legend)

    assert tuple(rgba[0, 1]) == (0, 0, 0, 0)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest backend/tests/test_raster_rendering.py::test_colorize_fills_nodata_pixels_with_nodata_color backend/tests/test_raster_rendering.py::test_colorize_without_nodata_color_keeps_invalid_pixels_transparent -v`

Expected: `test_colorize_fills_nodata_pixels_with_nodata_color` FAILS with `TypeError: colorize() got an unexpected keyword argument 'nodata_color'`

- [ ] **Step 3: Implement `nodata_color` in `colorize()`**

In `backend/raster_rendering.py`, change the function signature and rgba initialization (lines 29 and 56-57):

```python
def colorize(values, legend, source_mask=None, nodata=None, nodata_color=None):
    """Colorize one 2D raster band using numeric legend stops."""
    values = np.asarray(values)
    ...
    valid = valid_data_mask(values, source_mask=source_mask, nodata=nodata)
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    if nodata_color is not None:
        rgba[..., :] = nodata_color

    for channel in range(3):
        ...
    rgba[..., 3][valid] = 255
    return rgba
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest backend/tests/test_raster_rendering.py -v`

Expected: All tests PASS (existing 11 + 2 new = 13).

- [ ] **Step 5: Commit**

```bash
git add backend/raster_rendering.py backend/tests/test_raster_rendering.py
git commit -m "feat: add optional nodata_color to colorize for NoData background fill"
```

---

### Task 2: Wire nodata color into SSM tile rendering

**Files:**
- Modify: `backend/routers/tiles.py:43-55`
- Modify: `backend/tests/test_tiles.py`

**Interfaces:**
- Consumes: `colorize(values, legend, source_mask=None, nodata=None, nodata_color=None)` from Task 1
- Produces: `_render_ssm_tile()` passes nodata_color to colorize

- [ ] **Step 1: Write failing tile test**

In `backend/tests/test_tiles.py`, add a test that verifies `colorize` receives `nodata_color` from `_render_ssm_tile`:

```python
def test_render_ssm_tile_passes_nodata_color_to_colorize(tmp_path, monkeypatch):
    """_render_ssm_tile reads nodataColor/nodataOpacity from layer and forwards to colorize."""
    from unittest.mock import patch
    import backend.routers.tiles as tiles_module

    cog_path = tmp_path / "fake.tif"
    cog_path.write_bytes(b"fake")

    fake_legend = [
        {"value": 0.0, "color": "#ff0000", "label": ""},
        {"value": 1.0, "color": "#0000ff", "label": ""},
    ]
    fake_layer = {
        "id": "ssm",
        "legend": fake_legend,
        "unit": "m3/m3",
        "nodataColor": "#aabbcc",
        "nodataOpacity": 0.3,
    }

    colorize_args = {}

    def fake_colorize(values, legend, source_mask=None, nodata=None, nodata_color=None):
        colorize_args["nodata_color"] = nodata_color
        return np.zeros((*values.shape, 4), dtype=np.uint8)

    def fake_cog_tile(path, x, y, z, indexes=1):
        class Image:
            data = [np.zeros((256, 256), dtype=np.float32)]
            mask = np.ones((256, 256), dtype=np.uint8)
        return Image()

    monkeypatch.setattr(tiles_module, "get_layer", lambda _id: fake_layer)
    monkeypatch.setattr(tiles_module, "get_dynamic_legend", lambda p, bl, u: fake_legend)
    monkeypatch.setattr(tiles_module, "colorize", fake_colorize)
    monkeypatch.setattr(tiles_module, "COGReader", lambda path: type(
        "FakeReader", (), {"__enter__": lambda s: s, "__exit__": lambda *a: None,
         "tile": fake_cog_tile}
    )())

    tiles_module._render_ssm_tile(cog_path, 0, 0, 0)

    assert colorize_args["nodata_color"] == (0xaa, 0xbb, 0xcc, 76)
    # 0.3 * 255 = 76.5 → int(round(76.5)) = 76
```

Also add a test for default fallback:

```python
def test_render_ssm_tile_uses_default_nodata_color_when_not_configured(tmp_path, monkeypatch):
    """_render_ssm_tile uses #e8e8e8 at 0.5 opacity when layer has no nodataColor."""
    import backend.routers.tiles as tiles_module

    cog_path = tmp_path / "fake.tif"
    cog_path.write_bytes(b"fake")

    fake_legend = [
        {"value": 0.0, "color": "#ff0000", "label": ""},
        {"value": 1.0, "color": "#0000ff", "label": ""},
    ]
    # Layer WITHOUT nodataColor/nodataOpacity
    fake_layer = {"id": "ssm", "legend": fake_legend, "unit": "m3/m3"}

    colorize_args = {}

    def fake_colorize(values, legend, source_mask=None, nodata=None, nodata_color=None):
        colorize_args["nodata_color"] = nodata_color
        return np.zeros((*values.shape, 4), dtype=np.uint8)

    def fake_cog_tile(path, x, y, z, indexes=1):
        class Image:
            data = [np.zeros((256, 256), dtype=np.float32)]
            mask = np.ones((256, 256), dtype=np.uint8)
        return Image()

    monkeypatch.setattr(tiles_module, "get_layer", lambda _id: fake_layer)
    monkeypatch.setattr(tiles_module, "get_dynamic_legend", lambda p, bl, u: fake_legend)
    monkeypatch.setattr(tiles_module, "colorize", fake_colorize)
    monkeypatch.setattr(tiles_module, "COGReader", lambda path: type(
        "FakeReader", (), {"__enter__": lambda s: s, "__exit__": lambda *a: None,
         "tile": fake_cog_tile}
    )())

    tiles_module._render_ssm_tile(cog_path, 0, 0, 0)

    assert colorize_args["nodata_color"] == (0xe8, 0xe8, 0xe8, 128)
```

- [ ] **Step 2: Run tile tests and verify RED**

Run: `python -m pytest backend/tests/test_tiles.py::test_render_ssm_tile_passes_nodata_color_to_colorize backend/tests/test_tiles.py::test_render_ssm_tile_uses_default_nodata_color_when_not_configured -v`

Expected: FAIL — `colorize_args["nodata_color"]` is `None` (not yet passed).

- [ ] **Step 3: Wire nodata color in `_render_ssm_tile()`**

In `backend/routers/tiles.py`, update `_render_ssm_tile()`:

```python
def _render_ssm_tile(cog_path: Path, x: int, y: int, z: int) -> bytes:
    """Render one SSM COG tile using the shared metadata legend and source mask."""
    layer = get_layer("ssm")
    if layer is None:
        raise RuntimeError("SSM layer metadata is missing")
    base_legend = layer.get("legend")
    if not base_legend:
        raise RuntimeError("SSM layer legend is missing or empty")
    legend = get_dynamic_legend(cog_path, base_legend, layer.get("unit") or "")

    # Parse nodata color from layer config with defaults
    nodata_color_hex = layer.get("nodataColor", "#e8e8e8")
    nodata_opacity = float(layer.get("nodataOpacity", 0.5))
    try:
        nodata_rgb = tuple(bytes.fromhex(nodata_color_hex.lstrip("#")))
        nodata_alpha = int(round(nodata_opacity * 255))
        nodata_color = (*nodata_rgb, nodata_alpha)
    except (ValueError, TypeError):
        nodata_color = (0xe8, 0xe8, 0xe8, 128)

    with COGReader(str(cog_path)) as reader:
        image = reader.tile(x, y, z, indexes=1)
    rgba = colorize(
        image.data[0], legend, source_mask=image.mask, nodata_color=nodata_color
    )
    return render_png(rgba)
```

- [ ] **Step 4: Run tile tests and verify GREEN**

Run: `python -m pytest backend/tests/test_tiles.py -v`

Expected: All tile tests PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add backend/routers/tiles.py backend/tests/test_tiles.py
git commit -m "feat: pass configurable nodata color from layer metadata to tile renderer"
```

---

### Task 3: Full regression and push

**Files:**
- No production changes expected.

- [ ] **Step 1: Run full backend regression**

Run:
```bash
python -m pytest backend/tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Commit and push**

```bash
git push origin main
```
