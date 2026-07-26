import { describe, expect, it, vi } from 'vitest'
import {
  buildScreenIndex,
  circleRadiusPixels,
  classifyReclamationValue,
  drawBasePoints,
  drawHoverPoint,
  hitTestScreenIndex,
  isReclaimable,
  RECLAMATION_RADIUS_METERS,
  reclamationValueStyle,
  scenarioMetrics,
  type ScreenPoint,
} from '../components/reclamationCanvas'
import type { ReclamationMetrics, ReclamationPoint } from '../types'

const nodataMetrics: ReclamationMetrics = {
  reclamationValue: -999,
  waterConsumption: -999,
  yieldValue: -999,
  soilCarbonValue: -999,
}

const finiteMetrics: ReclamationMetrics = {
  reclamationValue: 1,
  waterConsumption: 2,
  yieldValue: 3,
  soilCarbonValue: 4,
}

function screenPoint(
  sourceIndex: number,
  x: number,
  y: number,
  reclaimable: boolean,
): ScreenPoint {
  return {
    sourceIndex,
    x,
    y,
    radius: 4,
    reclaimable,
    reclamationValueClass: reclaimable ? 'general' : 'non-reclaimable',
  }
}

function fakeCanvasContext(): CanvasRenderingContext2D {
  return {
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    clearRect: vi.fn(),
  } as unknown as CanvasRenderingContext2D
}

const projectedFixture: ScreenPoint[] = [
  screenPoint(0, 12, 20, true),
  screenPoint(1, 24, 20, false),
]

describe('reclamation Canvas engine', () => {
  it('selects metrics for the requested scenario', () => {
    const point: ReclamationPoint = {
      id: 'point-1',
      longitude: 100,
      latitude: 40,
      current: finiteMetrics,
      future: nodataMetrics,
    }

    expect(scenarioMetrics(point, 'current')).toBe(finiteMetrics)
    expect(scenarioMetrics(point, 'future')).toBe(nodataMetrics)
  })

  it('treats only four -999 metrics as non-reclaimable', () => {
    expect(isReclaimable(nodataMetrics)).toBe(false)
    expect(isReclaimable(finiteMetrics)).toBe(true)
    expect(isReclaimable({ ...nodataMetrics, yieldValue: 0 })).toBe(true)
  })

  it('classifies valid reclamation values for the legend', () => {
    expect(classifyReclamationValue(nodataMetrics)).toBe('non-reclaimable')
    expect(classifyReclamationValue({ ...finiteMetrics, reclamationValue: 0 })).toBe('general')
    expect(classifyReclamationValue({ ...finiteMetrics, reclamationValue: 5 })).toBe('recommended')
    expect(classifyReclamationValue({ ...finiteMetrics, reclamationValue: 10 })).toBe('recommended')
    expect(classifyReclamationValue({ ...finiteMetrics, reclamationValue: 10.1 })).toBe('priority')
  })

  it('uses a 450 m radius with a 3 px minimum', () => {
    expect(RECLAMATION_RADIUS_METERS).toBe(450)
    expect(circleRadiusPixels(40, 12)).toBeGreaterThan(3)
    expect(circleRadiusPixels(40, 4)).toBe(3)
  })

  it('finds the nearest reclaimable point in the current and adjacent 32 px buckets', () => {
    const index = buildScreenIndex([
      screenPoint(0, 31, 31, true),
      screenPoint(1, 34, 31, true),
      screenPoint(2, 32, 32, false),
    ])

    expect(hitTestScreenIndex(index, 33, 31)).toBe(1)
    expect(hitTestScreenIndex(index, 32, 32, { reclaimableOnly: true })).not.toBe(2)
  })

  it('finds a visible high-zoom circle beyond adjacent buckets', () => {
    const index = buildScreenIndex([{
      ...screenPoint(0, 0, 32, true),
      radius: 80,
    }])

    expect(hitTestScreenIndex(index, 79, 32)).toBe(0)
  })

  it('skips a nearer non-reclaimable point when a valid point is also hittable', () => {
    const index = buildScreenIndex([
      screenPoint(0, 32, 32, false),
      screenPoint(1, 34, 32, true),
    ])

    expect(hitTestScreenIndex(index, 32, 32)).toBe(1)
  })

  it('returns null when an index contains only non-reclaimable hits', () => {
    const index = buildScreenIndex([screenPoint(0, 32, 32, false)])

    expect(hitTestScreenIndex(index, 32, 32)).toBeNull()
  })

  it('breaks equal-distance hits by lower source index', () => {
    const index = buildScreenIndex([
      screenPoint(4, 30, 32, true),
      screenPoint(3, 34, 32, true),
    ])

    expect(hitTestScreenIndex(index, 32, 32)).toBe(3)
  })

  it('draws current valid points filled green and nodata points hollow', () => {
    const context = fakeCanvasContext()

    drawBasePoints(context, projectedFixture, 'current', '#16A34A')

    expect(context.fill).toHaveBeenCalledTimes(1)
    expect(context.stroke).toHaveBeenCalledTimes(2)
    expect(context.fillStyle).toBe('rgba(22, 163, 74, 0.4)')
    expect(context.strokeStyle).toBe('rgba(22, 163, 74, 0.95)')
    expect(context.lineWidth).toBe(1.25)
  })

  it('maps valid value classes to distinguishable opacity while retaining the scenario hue', () => {
    expect(reclamationValueStyle('non-reclaimable', '#16A34A')).toEqual({
      fill: null,
      stroke: 'rgba(22, 163, 74, 0.95)',
    })
    expect(reclamationValueStyle('general', '#16A34A').fill).toBe('rgba(22, 163, 74, 0.4)')
    expect(reclamationValueStyle('recommended', '#16A34A').fill).toBe('rgba(22, 163, 74, 0.64)')
    expect(reclamationValueStyle('priority', '#2563EB').fill).toBe('rgba(37, 99, 235, 0.82)')
  })

  it('clears and outlines a reclaimable hover point', () => {
    const context = fakeCanvasContext()
    const point = screenPoint(0, 12, 20, true)

    drawHoverPoint(context, point, 'future', '#2563EB', 100, 50)

    expect(context.clearRect).toHaveBeenCalledWith(0, 0, 100, 50)
    expect(context.arc).toHaveBeenCalledWith(12, 20, 6, 0, Math.PI * 2)
    expect(context.stroke).toHaveBeenCalledTimes(2)
    expect(context.lineWidth).toBe(1.25)
    expect(context.strokeStyle).toBe('#2563EB')
  })
})
