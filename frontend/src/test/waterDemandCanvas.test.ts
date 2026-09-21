import { describe, expect, it } from 'vitest'
import {
  HIT_RADIUS_PX,
  buildRowStarts,
  buildTierIndex,
  cellSizeMeters,
  circleRadiusPixels,
  classStyle,
  decodeColumnValues,
  drawBasePoints,
  drawHoverPoint,
  hitTestPoint,
  projectPoints,
  scenarioMetrics,
  typicalSpacingDegrees,
  WATER_DEMAND_MAX_RADIUS_PX,
  WATER_DEMAND_MIN_RADIUS_PX,
} from '../components/waterDemandCanvas'
import type { WaterDemandPointGrid } from '../types'

const DEGREES = 0.01

/**
 * Build a small but realistic transport: a 4x4 grid, row-major, with each metric
 * column quantised against its own range.
 */
function makeGrid(): WaterDemandPointGrid {
  const lonAxis = new Float64Array([100, 100.01, 100.02, 100.03])
  const latAxis = new Float64Array([30, 30.01, 30.02, 30.03])
  const gx: number[] = []
  const gy: number[] = []
  const classes: number[] = []
  // fraction[point][metric], chosen so every decoded value is exactly predictable
  const fractions: number[][] = []
  let sequence = 0
  for (let row = 0; row < 4; row += 1) {
    for (let column = 0; column < 4; column += 1) {
      gx.push(column)
      gy.push(row)
      classes.push((sequence % 3) + 1)
      fractions.push(
        Array.from({ length: 6 }, (_unused, metric) => ((sequence + metric) % 10) / 10),
      )
      sequence += 1
    }
  }

  const minimums = new Float64Array([0, 10, 20, 30, 40, 50])
  const maximums = new Float64Array([1000, 1010, 1020, 1030, 1040, 1050])
  const values = new Uint16Array(6 * fractions.length)
  for (let point = 0; point < fractions.length; point += 1) {
    for (let metric = 0; metric < 6; metric += 1) {
      values[metric * fractions.length + point] = Math.round(fractions[point][metric] * 65535)
    }
  }

  return {
    pointCount: gx.length,
    lonAxis,
    latAxis,
    gx: Uint16Array.from(gx),
    gy: Uint16Array.from(gy),
    values,
    classes: Uint8Array.from(classes),
    minimums,
    maximums,
  }
}

function projectToPlane(longitude: number, latitude: number): [number, number] {
  // Screen y decreases as latitude increases, matching Leaflet.
  return [(longitude - 100) * 1000, (30.03 - latitude) * 1000]
}

describe('decodeColumnValues', () => {
  it('restores each metric against its own quantisation range', () => {
    const grid = makeGrid()
    const values = decodeColumnValues(grid, 0)
    expect(values).toHaveLength(6)
    // point 0, metric m -> fraction m/10 between that column's min and max.
    // Each expected value sits within one quantisation step of the true value.
    const step = (metric: number) => (grid.maximums[metric] - grid.minimums[metric]) / 65535
    expect(values[0]).toBeCloseTo(0, 4)
    expect(Math.abs(values[1] - 110)).toBeLessThan(step(1))
    expect(Math.abs(values[5] - 550)).toBeLessThan(step(5))

    const values3 = decodeColumnValues(grid, 3)
    expect(Math.abs(values3[0] - 300)).toBeLessThan(step(0))
    expect(Math.abs(values3[5] - 850)).toBeLessThan(step(5))
  })

  it('keeps every metric inside its declared range', () => {
    const grid = makeGrid()
    for (let index = 0; index < grid.pointCount; index += 1) {
      const values = decodeColumnValues(grid, index)
      values.forEach((value, metric) => {
        expect(value).toBeGreaterThanOrEqual(grid.minimums[metric])
        expect(value).toBeLessThanOrEqual(grid.maximums[metric] + 1e-9)
      })
    }
  })
})

describe('scenarioMetrics', () => {
  it('maps current and future scenarios onto the right transport columns', () => {
    const grid = makeGrid()

    const current = scenarioMetrics(grid, 5, 'current')
    const future = scenarioMetrics(grid, 5, 'future')
    const all = decodeColumnValues(grid, 5)

    expect(current.ecologicalWaterConsumption).toBeCloseTo(all[0], 6)
    expect(current.ecologicalWaterDemand).toBeCloseTo(all[1], 6)
    expect(current.ecologicalWaterReplenishment).toBeCloseTo(all[2], 6)
    expect(future.ecologicalWaterConsumption).toBeCloseTo(all[3], 6)
    expect(future.ecologicalWaterDemand).toBeCloseTo(all[4], 6)
    expect(future.ecologicalWaterReplenishment).toBeCloseTo(all[5], 6)
  })
})

describe('buildRowStarts', () => {
  it('records the first index of every latitude row, including empty rows', () => {
    const gy = Uint16Array.from([0, 0, 2, 2, 2])
    const starts = buildRowStarts(gy, 4)

    expect(Array.from(starts)).toEqual([0, 2, 2, 5, 5])
  })
})

describe('buildTierIndex', () => {
  it('groups every point index by its tier and preserves ascending order', () => {
    const classes = Uint8Array.from([2, 1, 3, 1, 2, 1])
    const tier = buildTierIndex(classes)

    expect(Array.from(tier[1])).toEqual([1, 3, 5])
    expect(Array.from(tier[2])).toEqual([0, 4])
    expect(Array.from(tier[3])).toEqual([2])
  })

  it('ignores unknown tier codes instead of creating bogus groups', () => {
    const classes = Uint8Array.from([1, 9, 3])
    const tier = buildTierIndex(classes)

    expect(Array.from(tier[1])).toEqual([0])
    expect(Array.from(tier[2])).toEqual([])
    expect(Array.from(tier[3])).toEqual([2])
  })
})

describe('typicalSpacingDegrees', () => {
  it('returns the smallest gap so clipped gaps do not inflate the cell size', () => {
    // The real axis is regular except where study regions were clipped out.
    const axis = new Float64Array([100, 100.01, 100.02, 100.2, 100.21])
    expect(typicalSpacingDegrees(axis)).toBeCloseTo(0.01, 9)
  })

  it('returns zero for degenerate axes rather than dividing by nothing', () => {
    expect(typicalSpacingDegrees(new Float64Array([]))).toBe(0)
    expect(typicalSpacingDegrees(new Float64Array([5]))).toBe(0)
  })
})

describe('cell sizing', () => {
  it('spans fewer metres as latitude increases', () => {
    expect(cellSizeMeters(30, DEGREES)).toBeGreaterThan(cellSizeMeters(60, DEGREES))
    expect(cellSizeMeters(0, DEGREES)).toBeGreaterThan(cellSizeMeters(80, DEGREES))
  })

  it('draws a fixed cell larger as the map zooms in, up to the cap', () => {
    // 500 m cells stay inside the clamp window between zoom 9 and zoom 12.
    expect(circleRadiusPixels(30, 9, 500)).toBeLessThan(circleRadiusPixels(30, 11, 500))
    // zooming out below the floor and in above the cap both saturate
    expect(circleRadiusPixels(30, 1, 500)).toBe(WATER_DEMAND_MIN_RADIUS_PX)
    expect(circleRadiusPixels(30, 16, 500)).toBe(WATER_DEMAND_MAX_RADIUS_PX)
  })

  it('clamps the radius so tiny and huge cells stay legible', () => {
    expect(circleRadiusPixels(30, 3, 0.001)).toBe(WATER_DEMAND_MIN_RADIUS_PX)
    expect(circleRadiusPixels(30, 18, 100_000)).toBe(WATER_DEMAND_MAX_RADIUS_PX)
  })
})

describe('classStyle', () => {
  it('renders each tier as a translucent fill of its legend colour', () => {
    expect(classStyle(1, '#F08A85')).toBe('rgba(240, 138, 133, 0.7)')
    expect(classStyle(3, '#7BC47F')).toBe('rgba(123, 196, 127, 0.9)')
  })
})

describe('projectPoints', () => {
  it('projects every point and derives row spacing from the axis', () => {
    const grid = makeGrid()
    const projected = projectPoints(grid, projectToPlane, DEGREES, 10)

    expect(projected.positions).toHaveLength(grid.pointCount * 2)
    expect(projected.rowY).toHaveLength(4)
    // Screen y decreases as the latitude row index grows.
    expect(projected.rowY[0]).toBeGreaterThan(projected.rowY[3])
    expect(projected.columnSpacing).toBeCloseTo(10, 5)
    expect(projected.rowSpacing).toBeCloseTo(10, 5)
  })
})

describe('hitTestPoint', () => {
  function setup(zoom = 10) {
    const grid = makeGrid()
    const projected = projectPoints(grid, projectToPlane, DEGREES, zoom)
    const rowStarts = buildRowStarts(grid.gy, grid.latAxis.length)
    return { grid, projected, rowStarts }
  }

  it('returns the point drawn under the pointer', () => {
    const { grid, projected, rowStarts } = setup()
    const target = 5
    const x = projected.positions[target * 2]
    const y = projected.positions[target * 2 + 1]

    expect(hitTestPoint({ grid, projected, rowStarts, x, y })).toBe(target)
  })

  it('finds a point from a nearby pointer position within the hit radius', () => {
    const { grid, projected, rowStarts } = setup()
    const target = 6
    const x = projected.positions[target * 2] + HIT_RADIUS_PX / 2
    const y = projected.positions[target * 2 + 1] - HIT_RADIUS_PX / 2

    expect(hitTestPoint({ grid, projected, rowStarts, x, y })).toBe(target)
  })

  it('returns null when the pointer is far from every sample', () => {
    const { grid, projected, rowStarts } = setup()

    expect(hitTestPoint({ grid, projected, rowStarts, x: -500, y: -500 })).toBeNull()
  })

  it('returns null for an empty artifact or a non-finite pointer position', () => {
    const grid = makeGrid()
    const empty: WaterDemandPointGrid = { ...grid, pointCount: 0 }
    const projected = projectPoints(empty, projectToPlane, DEGREES, 10)
    const rowStarts = buildRowStarts(empty.gy, empty.latAxis.length)

    expect(hitTestPoint({ grid: empty, projected, rowStarts, x: 0, y: 0 })).toBeNull()
    expect(hitTestPoint({ grid, projected, rowStarts, x: Number.NaN, y: 0 })).toBeNull()
  })
})

describe('drawing', () => {
  function recordingContext() {
    const calls: string[] = []
    const context = {
      canvas: { width: 400, height: 300 },
      beginPath: () => calls.push('beginPath'),
      arc: (x: number, y: number) => calls.push(`arc:${x},${y}`),
      moveTo: () => calls.push('moveTo'),
      fill: function fill(this: { fillStyle?: string }) { calls.push(`fill:${this.fillStyle}`) },
      stroke: () => calls.push('stroke'),
      clearRect: () => calls.push('clearRect'),
      fillStyle: '' as string,
      strokeStyle: '' as string,
      lineWidth: 0 as number,
    }
    return { context: context as unknown as CanvasRenderingContext2D, calls }
  }

  it('batches each tier into a single fill call', () => {
    const grid = makeGrid()
    const projected = projectPoints(grid, projectToPlane, DEGREES, 10)
    const tier = buildTierIndex(grid.classes)
    const { context, calls } = recordingContext()

    drawBasePoints(
      context,
      grid,
      projected,
      tier,
      { 1: '#F08A85', 2: '#F2C744', 3: '#7BC47F' },
      400,
      300,
    )

    const fills = calls.filter((call) => call.startsWith('fill:'))
    expect(fills).toEqual([
      'fill:rgba(240, 138, 133, 0.7)',
      'fill:rgba(242, 199, 68, 0.9)',
      'fill:rgba(123, 196, 127, 0.9)',
    ])
    // 16 points, so 16 arcs and moveTo pairs across the three tiers.
    expect(calls.filter((call) => call.startsWith('arc:'))).toHaveLength(16)
  })

  it('skips off-screen points instead of drawing them', () => {
    const grid = makeGrid()
    const projected = projectPoints(grid, projectToPlane, DEGREES, 10)
    const tier = buildTierIndex(grid.classes)
    const { context, calls } = recordingContext()

    drawBasePoints(
      context,
      grid,
      projected,
      tier,
      { 1: '#F08A85', 2: '#F2C744', 3: '#7BC47F' },
      -100,
      -100,
    )

    expect(calls.filter((call) => call.startsWith('arc:'))).toHaveLength(0)
    expect(calls.filter((call) => call.startsWith('fill:'))).toHaveLength(0)
  })

  it('clears the hover canvas and outlines the highlighted point in two passes', () => {
    const { context, calls } = recordingContext()

    drawHoverPoint(context, { x: 10, y: 20, radius: 3 }, '#F08A85', 400, 300)
    expect(calls[0]).toBe('clearRect')
    expect(calls.filter((call) => call === 'stroke')).toHaveLength(2)

    calls.length = 0
    drawHoverPoint(context, null, '#F08A85', 400, 300)
    expect(calls).toEqual(['clearRect'])
  })
})
