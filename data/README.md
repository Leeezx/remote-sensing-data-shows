# Data Directory

Sample data files for the Remote Sensing Data Display Website.

## Directory Structure

```
data/
├── metadata/          # Layer metadata definitions
│   └── layers.json    # All available map layers with legends
├── series/            # Time-series data files
│   ├── *_times.json   # Available time points per layer
│   └── *_series.json  # Mean time-series values per layer
├── stats/             # Area statistics
│   ├── regions.json   # Predefined region boundaries
│   └── area_stats.json# Zonal statistics per region × layer × time
├── tiles/             # Pre-generated raster tiles (not in git)
│   ├── ndvi/
│   ├── precipitation/
│   ├── soil_moisture/
│   └── lst/
├── schema.md          # JSON schema documentation
└── validate_data.py   # Data validation script
```

## Tile Path Convention

Tiles follow the standard TMS (Tile Map Service) directory layout:

```
data/tiles/{layer}/{time}/{z}/{x}/{y}.png
```

- `{layer}` — Layer identifier: `ndvi`, `precipitation`, `soil_moisture`, `lst`
- `{time}` — Time stamp in `YYYY-MM` format (e.g., `2025-01`)
- `{z}` — Zoom level (integer)
- `{x}` — Tile column (integer)
- `{y}` — Tile row (integer, TMS convention)

## Tile Generation

Tiles are **pre-generated** and **not committed to git** due to their size.
They are part of the data package, generated externally or downloaded separately.

### Sample Tile Generation Command

If source GeoTIFF raster files are available, tiles can be generated using
`gdal2tiles.py` (from GDAL):

```bash
# Generate tiles for a single layer and time point
gdal2tiles.py \
  --zoom=0-8 \
  --processes=4 \
  --resampling=average \
  --xyz \
  input_ndvi_2025-01.tif \
  data/tiles/ndvi/2025-01/

# The --xyz flag ensures TMS-compatible Y-axis ordering
```

### Expected Tile Ranges

For each layer × time combination, tiles typically span zoom levels 0-8:
- z=0: 1 tile (global overview)
- z=8: ~65,536 tiles (detailed view)

Each tile is a 256×256 RGBA PNG image.

## Data Validation

Run the validation script to check all data files:

```bash
python data/validate_data.py
```
