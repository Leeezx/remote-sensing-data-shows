import type {
  ReclamationMetrics,
  ReclamationPoint,
  ReclamationScenario,
} from '../types'

export const RECLAMATION_RADIUS_METERS = 400
export const MIN_RADIUS_PX = 3
export const SCREEN_BUCKET_PX = 32
export const CURRENT_SCENARIO_COLOR = '#16A34A'
export const FUTURE_SCENARIO_COLOR = '#2563EB'
export const NON_RECLAIMABLE_COLOR = '#64748B'

const EARTH_PIXEL_METERS_AT_ZOOM_ZERO = 156543.03392
const FULL_CIRCLE_RADIANS = Math.PI * 2

export interface ScreenPoint {
  sourceIndex: number
  x: number
  y: number
  radius: number
  reclaimable: boolean
  reclamationValueClass: ReclamationValueClass
}

export interface ScreenIndex {
  buckets: Map<string, ScreenPoint[]>
  maxHitRadius: number
}

export interface HitTestOptions {
  reclaimableOnly?: boolean
}

export type ReclamationValueClass =
  | 'non-reclaimable'
  | 'general'
  | 'recommended'
  | 'priority'

const RECLAMATION_CLASS_COLORS: Partial<Record<ReclamationValueClass, string>> = {
  general: '#22C55E',
  recommended: '#F59E0B',
  priority: '#DC2626',
}

export function scenarioMetrics(
  point: ReclamationPoint,
  scenario: ReclamationScenario,
): ReclamationMetrics {
  return point[scenario]
}

export function isReclaimable(metrics: ReclamationMetrics): boolean {
  return !Object.values(metrics).every((value) => value === -999)
}

export function classifyReclamationValue(
  metrics: ReclamationMetrics,
): ReclamationValueClass {
  if (!isReclaimable(metrics)) return 'non-reclaimable'
  if (metrics.reclamationValue < 5) return 'general'
  if (metrics.reclamationValue <= 10) return 'recommended'
  return 'priority'
}

export function metersPerPixel(latitude: number, zoom: number): number {
  return EARTH_PIXEL_METERS_AT_ZOOM_ZERO
    * Math.cos(latitude * Math.PI / 180)
    / 2 ** zoom
}

export function circleRadiusPixels(latitude: number, zoom: number): number {
  return Math.max(
    MIN_RADIUS_PX,
    RECLAMATION_RADIUS_METERS / metersPerPixel(latitude, zoom),
  )
}

function bucketKey(x: number, y: number): string {
  return `${Math.floor(x / SCREEN_BUCKET_PX)},${Math.floor(y / SCREEN_BUCKET_PX)}`
}

export function buildScreenIndex(points: ScreenPoint[]): ScreenIndex {
  const buckets = new Map<string, ScreenPoint[]>()
  let maxHitRadius = 5

  for (const point of points) {
    maxHitRadius = Math.max(maxHitRadius, point.radius)
    const key = bucketKey(point.x, point.y)
    const bucket = buckets.get(key)
    if (bucket) bucket.push(point)
    else buckets.set(key, [point])
  }

  return { buckets, maxHitRadius }
}

export function hitTestScreenIndex(
  index: ScreenIndex,
  x: number,
  y: number,
  _options: HitTestOptions = {},
): number | null {
  const bucketX = Math.floor(x / SCREEN_BUCKET_PX)
  const bucketY = Math.floor(y / SCREEN_BUCKET_PX)
  let nearest: ScreenPoint | null = null
  let nearestDistanceSquared = Number.POSITIVE_INFINITY

  const bucketRadius = Math.ceil(index.maxHitRadius / SCREEN_BUCKET_PX)

  for (let offsetY = -bucketRadius; offsetY <= bucketRadius; offsetY += 1) {
    for (let offsetX = -bucketRadius; offsetX <= bucketRadius; offsetX += 1) {
      const bucket = index.buckets.get(`${bucketX + offsetX},${bucketY + offsetY}`)
      if (!bucket) continue

      for (const candidate of bucket) {
        if (!candidate.reclaimable) continue

        const distanceX = candidate.x - x
        const distanceY = candidate.y - y
        const distanceSquared = distanceX ** 2 + distanceY ** 2
        const hitRadius = Math.max(candidate.radius, 5)
        const isNearer = distanceSquared < nearestDistanceSquared
        const breaksTie = distanceSquared === nearestDistanceSquared
          && (!nearest || candidate.sourceIndex < nearest.sourceIndex)

        if (distanceSquared <= hitRadius ** 2 && (isNearer || breaksTie)) {
          nearest = candidate
          nearestDistanceSquared = distanceSquared
        }
      }
    }
  }

  return nearest?.sourceIndex ?? null
}

function rgba(hexColor: string, alpha: number): string {
  const normalized = hexColor.replace('#', '')
  const red = Number.parseInt(normalized.slice(0, 2), 16)
  const green = Number.parseInt(normalized.slice(2, 4), 16)
  const blue = Number.parseInt(normalized.slice(4, 6), 16)

  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
}

export function reclamationValueStyle(
  valueClass: ReclamationValueClass,
  _color: string,
): { fill: string | null; stroke: string } {
  const opacityByValueClass: Partial<Record<ReclamationValueClass, number>> = {
    general: 0.4,
    recommended: 0.64,
    priority: 0.82,
  }
  const opacity = opacityByValueClass[valueClass]
  const classColor = RECLAMATION_CLASS_COLORS[valueClass] ?? NON_RECLAIMABLE_COLOR

  return {
    fill: opacity === undefined ? null : rgba(classColor, opacity),
    stroke: valueClass === 'non-reclaimable'
      ? NON_RECLAIMABLE_COLOR
      : rgba(classColor, 0.95),
  }
}

export function drawBasePoints(
  context: CanvasRenderingContext2D,
  points: ScreenPoint[],
  _scenario: ReclamationScenario,
  color: string,
): void {
  context.lineWidth = 1.25

  for (const point of points) {
    const style = reclamationValueStyle(point.reclamationValueClass, color)
    context.strokeStyle = style.stroke
    context.beginPath()
    context.arc(point.x, point.y, point.radius, 0, FULL_CIRCLE_RADIANS)
    if (style.fill) {
      context.fillStyle = style.fill
      context.fill()
    }
    context.stroke()
  }
}

export function drawHoverPoint(
  context: CanvasRenderingContext2D,
  point: ScreenPoint | null,
  _scenario: ReclamationScenario,
  color: string,
  width = context.canvas?.width ?? 0,
  height = context.canvas?.height ?? 0,
): void {
  context.clearRect(0, 0, width, height)
  if (!point?.reclaimable) return

  const radius = point.radius + 2
  context.beginPath()
  context.arc(point.x, point.y, radius, 0, FULL_CIRCLE_RADIANS)
  context.strokeStyle = '#FFFFFF'
  context.lineWidth = 3
  context.stroke()

  context.beginPath()
  context.arc(point.x, point.y, radius, 0, FULL_CIRCLE_RADIANS)
  context.strokeStyle = color
  context.lineWidth = 1.25
  context.stroke()
}
