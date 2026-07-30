# Quantile-Based Legend Thresholds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace linear spacing with quantile-based spacing in `build_dynamic_legend` so each of the 6 color bins covers ~20% of valid pixels, maximizing visual differentiation on the map.

**Architecture:** One-line change in `backend/ssm_legend.py` — swap `np.linspace(low, high, 6)` for `np.percentile(valid_values, np.linspace(2, 98, 6))`. Update two affected tests.

**Tech Stack:** Python 3, NumPy, pytest.

---

## File map

- Modify `backend/ssm_legend.py:36`: replace linear stops with quantile stops
- Modify `backend/tests/test_ssm_legend.py:33-65`: update two tests that assert linear spacing

---

### Task 1: Switch to quantile-based threshold spacing

**Files:**
- Modify: `backend/ssm_legend.py:36`
- Modify: `backend/tests/test_ssm_legend.py:33-65`

- [ ] **Step 1: Update the core calculation**

In `backend/ssm_legend.py`, replace line 36:

```python
stops = np.linspace(low, high, 6)
```

With:

```python
stops = np.percentile(valid_values, np.linspace(2, 98, 6))
```

- [ ] **Step 2: Update test `test_build_dynamic_legend_uses_p2_p98_and_six_even_stops`**

Rename and rewrite to use quantile semantics:

```python
def test_build_dynamic_legend_uses_quantile_stops_spanning_p2_to_p98():
    values = np.arange(100, dtype=float)

    result = build_dynamic_legend(values, BASE_LEGEND, "m3/m3")

    expected = np.percentile(values, np.linspace(2, 98, 6))
    np.testing.assert_allclose([item["value"] for item in result], expected)
    assert all(type(item["value"]) is float for item in result)
```

- [ ] **Step 3: Update test `test_build_dynamic_legend_excludes_all_invalid_pixel_types`**

Compute expected quantile stops from the three valid values `[-999, 0, 100]`:

```python
def test_build_dynamic_legend_excludes_all_invalid_pixel_types():
    values = np.array([0.0, 50.0, 100.0, -999.0, -32768.0, np.nan, np.inf, -np.inf])
    source_mask = np.array([255, 0, 255, 255, 255, 255, 255, 255], dtype=np.uint8)

    result = build_dynamic_legend(
        values,
        BASE_LEGEND,
        "",
        source_mask=source_mask,
        nodata=-32768.0,
    )

    # Valid values after filtering: [-999.0, 0.0, 100.0]
    expected = np.percentile(np.array([-999.0, 0.0, 100.0]), np.linspace(2, 98, 6))
    np.testing.assert_allclose([item["value"] for item in result], expected)
    assert result[0]["label"] == f"{expected[0]:.3f}"
```

- [ ] **Step 4: Run backend tests**

Run: `python -m pytest backend/tests/test_ssm_legend.py -v`

Expected: All tests PASS.

- [ ] **Step 5: Run full regression**

Run:

```bash
python -m pytest backend/tests/test_ssm_legend.py backend/tests/test_layers.py backend/tests/test_tiles.py backend/tests/test_raster_rendering.py -v
```

Expected: All PASS.

- [ ] **Step 6: Commit and push**

```bash
git add backend/ssm_legend.py backend/tests/test_ssm_legend.py
git commit -m "fix: use quantile-based legend thresholds for even color distribution"
git push origin main
```
