import type {
  WaterDemandClass,
  WaterDemandMetrics,
  WaterDemandPointGrid,
  WaterDemandScenario,
} from '../types'

/** Screen radius bounds for one sampled cell, in pixels. */
export const WATER_DEMAND_MIN_RADIUS_PX = 1.2
export const WATER_DEMAND_MAX_RADIUS_PX = 6
/** Extra screen pixels treated as a hit around a cell centre. */
export const HIT_RADIUS_PX = 6
/**
 * Maximum number of sample circles accumulated in one canvas path.
 *
 * Browsers silently drop `fill()` calls whose path holds hundreds of thousands
 * of arcs, which hid every point at the demo-region fit zoom; flushing the path
 * in bounded chunks keeps each rasterisation request inside engine limits.
 */
export const WATER_DEMAND_FILL_CHUNK = 20000
/** Hard cap on how many rows/columns a single hit test scans. */
export const MAX_HIT_WINDOW = 48

const EARTH_PIXEL_METERS_AT_ZOOM_ZERO = 156543.03392
const METERS_PER_DEGREE = (EARTH_PIXEL_METERS_AT_ZOOM_ZERO * 256) / 360
const FULL_CIRCLE_RADIANS = Math.PI * 2
const METRIC_COUNT = 6
const QUANT_MAX = 65535

export const WATER_DEMAND_CLASSES: WaterDemandClass[] = [1, 2, 3]

/** Column index of each metric inside the transport's six-column block. */
export const WATER_DEMAND_VALUE_INDEX: Record<
  WaterDemandScenario,
  Record<keyof WaterDemandMetrics, number>
> = {
  current: {
    ecologicalWaterConsumption: 0,
    ecologicalWaterDemand: 1,
    ecologicalWaterReplenishment: 2,
  },
  future: {
    ecologicalWaterConsumption: 3,
    ecologicalWaterDemand: 4,
    ecologicalWaterReplenishment: 5,
  },
}

export interface TierIndex {
  /** Source indices of every point in the tier, ascending. */
  1: Uint32Array
  2: Uint32Array
  3: Uint32Array
}

type MetricGrid = Pick<
  WaterDemandPointGrid,
  'values' | 'minimums' | 'maximums' | 'pointCount'
>

/**
 * Reconstruct the six stored values for one point, in transport column order.
 *
 * `values` is column major: a metric lives at `values[column * pointCount + point]`.
 * Each column was quantised against its own observed range, so the absolute error
 * is bounded by `(max - min) / 65535`.
 */
export function decodeColumnValues(grid: MetricGrid, sourceIndex: number): number[] {
  const values: number[] = []
  for (let column = 0; column < METRIC_COUNT; column += 1) {
    const quantised = grid.values[column * grid.pointCount + sourceIndex]
    const span = grid.maximums[column] - grid.minimums[column]
    values.push(grid.minimums[column] + (quantised * span) / QUANT_MAX)
  }
  return values
}

export function scenarioMetrics(
  grid: MetricGrid,
  sourceIndex: number,
  scenario: WaterDemandScenario,
): WaterDemandMetrics {
  const columns = WATER_DEMAND_VALUE_INDEX[scenario]
  const all = decodeColumnValues(grid, sourceIndex)
  return {
    ecologicalWaterConsumption: all[columns.ecologicalWaterConsumption],
    ecologicalWaterDemand: all[columns.ecologicalWaterDemand],
    ecologicalWaterReplenishment: all[columns.ecologicalWaterReplenishment],
  }
}

/** Longitude of a point, resolved through the sampling axis. */
export function pointLongitude(grid: WaterDemandPointGrid, sourceIndex: number): number {
  return grid.lonAxis[grid.gx[sourceIndex]]
}

/** Latitude of a point, resolved through the sampling axis. */
export function pointLatitude(grid: WaterDemandPointGrid, sourceIndex: number): number {
  return grid.latAxis[grid.gy[sourceIndex]]
}

/**
 * Start offset of every latitude row in the row-major transport.
 *
 * `starts[row]` is the first index whose `gy >= row`; empty rows therefore have
 * `starts[row] === starts[row + 1]`.
 */
export function buildRowStarts(gy: Uint16Array, rowCount: number): Uint32Array {
  const starts = new Uint32Array(rowCount + 1)
  let cursor = 0
  for (let row = 0; row < rowCount; row += 1) {
    while (cursor < gy.length && gy[cursor] < row) cursor += 1
    starts[row] = cursor
  }
  starts[rowCount] = gy.length
  return starts
}

/** Group source indices by tier. */
export function buildTierIndex(
  classes: Uint8Array,
  classValues: WaterDemandClass[] = WATER_DEMAND_CLASSES,
): TierIndex {
  const counts = new Map<WaterDemandClass, number>()
  for (const value of classValues) counts.set(value, 0)
  for (let index = 0; index < classes.length; index += 1) {
    const value = classes[index] as WaterDemandClass
    if (counts.has(value)) counts.set(value, (counts.get(value) ?? 0) + 1)
  }

  const tier: TierIndex = {
    1: new Uint32Array(0),
    2: new Uint32Array(0),
    3: new Uint32Array(0),
  }
  for (const value of classValues) tier[value] = new Uint32Array(counts.get(value) ?? 0)

  const cursors = new Map<WaterDemandClass, number>()
  for (const value of classValues) cursors.set(value, 0)
  for (let index = 0; index < classes.length; index += 1) {
    const value = classes[index] as WaterDemandClass
    const cursor = cursors.get(value)
    if (cursor === undefined) continue
    tier[value][cursor] = index
    cursors.set(value, cursor + 1)
  }
  return tier
}

/** Metres spanned by one sampling step at the given latitude. */
export function cellSizeMeters(latitude: number, degrees: number): number {
  return METERS_PER_DEGREE * degrees * Math.cos((latitude * Math.PI) / 180)
}

/** Radius in pixels covering roughly one sampled cell. */
export function circleRadiusPixels(
  latitude: number,
  zoom: number,
  cellMeters: number,
): number {
  const metersPerPixel =
    (EARTH_PIXEL_METERS_AT_ZOOM_ZERO * Math.cos((latitude * Math.PI) / 180)) / 2 ** zoom
  return Math.min(
    WATER_DEMAND_MAX_RADIUS_PX,
    Math.max(WATER_DEMAND_MIN_RADIUS_PX, cellMeters / metersPerPixel / 2),
  )
}

function rgba(hexColor: string, alpha: number): string {
  const normalized = hexColor.replace('#', '')
  const red = Number.parseInt(normalized.slice(0, 2), 16)
  const green = Number.parseInt(normalized.slice(2, 4), 16)
  const blue = Number.parseInt(normalized.slice(4, 6), 16)
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
}

const CLASS_OPACITY: Record<WaterDemandClass, number> = { 1: 0.7, 2: 0.9, 3: 0.9 }

export function classStyle(value: WaterDemandClass, color: string): string {
  return rgba(color, CLASS_OPACITY[value])
}

/**
 * Typical spacing between adjacent axis values, in degrees.
 *
 * The sampling grid is regular apart from a few wider gaps where a study area
 * region was clipped out, so the minimum step describes one cell best.
 */
export function typicalSpacingDegrees(axis: Float64Array): number {
  if (axis.length < 2) return 0
  let smallest = Number.POSITIVE_INFINITY
  for (let index = 1; index < axis.length; index += 1) {
    const gap = axis[index] - axis[index - 1]
    if (gap > 0 && gap < smallest) smallest = gap
  }
  return Number.isFinite(smallest) ? smallest : 0
}

export interface ProjectedPoints {
  /** Interleaved container-space `x, y` per source index. */
  positions: Float32Array
  /** Container-space `y` per latitude row; decreases as the row index grows. */
  rowY: Float64Array
  /** Cell radius per latitude row. */
  rowRadius: Float32Array
  /** Absolute pixel gap between adjacent latitude rows. */
  rowSpacing: number
  /** Absolute pixel gap between adjacent longitude columns. */
  columnSpacing: number
}

/**
 * Project every point into container space.
 *
 * `project` maps a longitude/latitude pair to container `[x, y]`, which keeps this
 * function independent of Leaflet for testing.
 */
export function projectPoints(
  grid: WaterDemandPointGrid,
  project: (longitude: number, latitude: number) => [number, number],
  degrees: number,
  zoom: number,
): ProjectedPoints {
  const positions = new Float32Array(grid.pointCount * 2)
  for (let index = 0; index < grid.pointCount; index += 1) {
    const [x, y] = project(grid.lonAxis[grid.gx[index]], grid.latAxis[grid.gy[index]])
    positions[index * 2] = x
    positions[index * 2 + 1] = y
  }

  const rowY = new Float64Array(grid.latAxis.length)
  const rowRadius = new Float32Array(grid.latAxis.length)
  for (let row = 0; row < grid.latAxis.length; row += 1) {
    const latitude = grid.latAxis[row]
    rowY[row] = project(grid.lonAxis[0], latitude)[1]
    rowRadius[row] = circleRadiusPixels(latitude, zoom, cellSizeMeters(latitude, degrees))
  }

  const rowSpacing = rowY.length > 1 ? Math.abs(rowY[1] - rowY[0]) : 1
  const columnSpacing = grid.lonAxis.length > 1
    ? Math.abs(project(grid.lonAxis[1], grid.latAxis[0])[0] - project(grid.lonAxis[0], grid.latAxis[0])[0])
    : 1

  return { positions, rowY, rowRadius, rowSpacing, columnSpacing }
}

/**
 * Draw all points as batched paths per tier, skipping off-screen samples.
 *
 * Each tier is flushed at most `WATER_DEMAND_FILL_CHUNK` circles at a time:
 * one unbounded path for the whole artifact rasterises to nothing in Chromium
 * whenever the demo region fits the viewport, so points only appeared after
 * zooming in far enough to shrink the visible sample count.
 */
export function drawBasePoints(
  context: CanvasRenderingContext2D,
  grid: WaterDemandPointGrid,
  projected: ProjectedPoints,
  tier: TierIndex,
  colors: Record<WaterDemandClass, string>,
  width: number,
  height: number,
): void {
  const { positions, rowRadius } = projected
  for (const value of WATER_DEMAND_CLASSES) {
    const indices = tier[value]
    context.fillStyle = classStyle(value, colors[value])
    let pending = 0
    for (let cursor = 0; cursor < indices.length; cursor += 1) {
      const index = indices[cursor]
      const x = positions[index * 2]
      const y = positions[index * 2 + 1]
      const radius = rowRadius[grid.gy[index]]
      if (x < -radius || x > width + radius) continue
      if (y < -radius || y > height + radius) continue
      if (pending === 0) context.beginPath()
      context.moveTo(x + radius, y)
      context.arc(x, y, radius, 0, FULL_CIRCLE_RADIANS)
      pending += 1
      if (pending === WATER_DEMAND_FILL_CHUNK) {
        context.fill()
        pending = 0
      }
    }
    if (pending > 0) context.fill()
  }
}

export function drawHoverPoint(
  context: CanvasRenderingContext2D,
  highlighted: { x: number; y: number; radius: number } | null,
  color: string,
  width = context.canvas?.width ?? 0,
  height = context.canvas?.height ?? 0,
): void {
  context.clearRect(0, 0, width, height)
  if (!highlighted) return

  const radius = highlighted.radius + 2
  context.beginPath()
  context.arc(highlighted.x, highlighted.y, radius, 0, FULL_CIRCLE_RADIANS)
  context.strokeStyle = '#FFFFFF'
  context.lineWidth = 3
  context.stroke()

  context.beginPath()
  context.arc(highlighted.x, highlighted.y, radius, 0, FULL_CIRCLE_RADIANS)
  context.strokeStyle = color
  context.lineWidth = 1.25
  context.stroke()
}

export interface HitTestInput {
  grid: WaterDemandPointGrid
  projected: ProjectedPoints
  rowStarts: Uint32Array
  x: number
  y: number
}

/**
 * Find the point nearest a container-space position.
 *
 * Uses the row-major transport: locate the latitude row whose screen `y` is
 * closest to the pointer, then binary-search the longitude axis inside that row
 * and compare a small neighbourhood. Both windows scale with the on-screen sample
 * spacing, so the scan stays bounded from fit zoom to street zoom. No per-point
 * object index is built, which is what keeps 500k samples affordable.
 */
export function hitTestPoint(input: HitTestInput): number | null {
  const { grid, projected, rowStarts, x, y } = input
  if (grid.pointCount === 0) return null
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null

  const { positions, rowY, rowRadius, rowSpacing, columnSpacing } = projected
  const rowCount = grid.latAxis.length
  if (rowCount === 0 || positions.length === 0) return null

  const reach = HIT_RADIUS_PX + WATER_DEMAND_MAX_RADIUS_PX
  const rowWindow = Math.min(MAX_HIT_WINDOW, Math.max(1, Math.ceil(reach / Math.max(rowSpacing, 1e-6))))
  const columnWindow = Math.min(MAX_HIT_WINDOW, Math.max(1, Math.ceil(reach / Math.max(columnSpacing, 1e-6))))

  // `rowY` decreases as the latitude row index grows, so the located row is the
  // first one at or below the pointer; its predecessor is the other candidate.
  const locatedRow = lowerBoundDescending(rowY, y)
  const firstRow = Math.max(0, locatedRow - rowWindow)
  const lastRow = Math.min(rowCount - 1, locatedRow + rowWindow)

  let best = -1
  let bestDistance = Number.POSITIVE_INFINITY

  for (let row = firstRow; row <= lastRow; row += 1) {
    const start = rowStarts[row]
    const end = rowStarts[row + 1]
    if (start >= end) continue

    // Longitude indices ascend inside a row, so binary-search the target x.
    const locatedColumn = lowerBoundRowX(positions, start, end, x)
    const from = Math.max(start, locatedColumn - columnWindow)
    const to = Math.min(end - 1, locatedColumn + columnWindow)
    for (let index = from; index <= to; index += 1) {
      const dx = positions[index * 2] - x
      const dy = positions[index * 2 + 1] - y
      const distance = dx * dx + dy * dy
      if (distance < bestDistance) {
        bestDistance = distance
        best = index
      }
    }
  }

  if (best < 0) return null
  const tolerance = rowRadius[grid.gy[best]] + HIT_RADIUS_PX
  return bestDistance <= tolerance * tolerance ? best : null
}

/** Index of the first entry at or below `target` in a descending array. */
function lowerBoundDescending(sorted: Float64Array, target: number): number {
  let low = 0
  let high = sorted.length
  while (low < high) {
    const middle = (low + high) >> 1
    if (sorted[middle] > target) low = middle + 1
    else high = middle
  }
  return low
}

function lowerBoundRowX(
  positions: Float32Array,
  start: number,
  end: number,
  x: number,
): number {
  let low = start
  let high = end
  while (low < high) {
    const middle = (low + high) >> 1
    if (positions[middle * 2] < x) low = middle + 1
    else high = middle
  }
  return low
}
