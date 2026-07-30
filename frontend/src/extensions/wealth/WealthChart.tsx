import { useMemo, useState } from 'react'

import type { PerformancePoint } from './types'

interface WealthChartProps {
  data: PerformancePoint[]
}

const WIDTH = 960
const HEIGHT = 340
const PADDING = { left: 54, right: 24, top: 28, bottom: 38 }

const percent = (value: number | null | undefined) =>
  value == null ? '—' : `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`

export default function WealthChart({ data }: WealthChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const chart = useMemo(() => {
    if (data.length < 2) return null
    const values = data.flatMap(point =>
      [point.portfolio_return, point.benchmark_return].filter(
        (value): value is number => value != null && Number.isFinite(value),
      ),
    )
    if (!values.length) return null

    let min = Math.min(...values, 0)
    let max = Math.max(...values, 0)
    const rawRange = max - min || 0.1
    min -= rawRange * 0.12
    max += rawRange * 0.12
    const range = max - min
    const innerWidth = WIDTH - PADDING.left - PADDING.right
    const innerHeight = HEIGHT - PADDING.top - PADDING.bottom
    const x = (index: number) => PADDING.left + (index / (data.length - 1)) * innerWidth
    const y = (value: number) => PADDING.top + innerHeight - ((value - min) / range) * innerHeight
    const path = (key: 'portfolio_return' | 'benchmark_return') => {
      let started = false
      return data.map((point, index) => {
        const value = point[key]
        if (value == null || !Number.isFinite(value)) {
          started = false
          return ''
        }
        const command = started ? 'L' : 'M'
        started = true
        return `${command}${x(index).toFixed(2)},${y(value).toFixed(2)}`
      }).join(' ')
    }
    const ticks = Array.from({ length: 5 }, (_, index) => {
      const value = min + (range * index) / 4
      return { value, y: y(value) }
    })
    return {
      min,
      max,
      x,
      y,
      portfolioPath: path('portfolio_return'),
      benchmarkPath: path('benchmark_return'),
      ticks,
    }
  }, [data])

  if (!chart) {
    return (
      <div className="h-[300px] flex items-center justify-center text-[13px] text-muted-foreground">
        至少需要两个交易日快照才能绘制收益曲线
      </div>
    )
  }

  const activeIndex = hoverIndex == null ? data.length - 1 : hoverIndex
  const active = data[activeIndex]
  const activeX = chart.x(activeIndex)
  const activePortfolioY =
    active.portfolio_return == null ? null : chart.y(active.portfolio_return)

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const pointerX = ((event.clientX - rect.left) / rect.width) * WIDTH
    const ratio = (pointerX - PADDING.left) / (WIDTH - PADDING.left - PADDING.right)
    const index = Math.round(Math.max(0, Math.min(1, ratio)) * (data.length - 1))
    setHoverIndex(index)
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
        <div className="flex items-center gap-4 text-[12px]">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-primary" />
            组合 {percent(active.portfolio_return)}
          </span>
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
            沪深300ETF {percent(active.benchmark_return)}
          </span>
        </div>
        <span className="text-[12px] text-muted-foreground">
          {active.snapshot_date} · 超额 {percent(active.excess_return)}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full h-auto select-none touch-pan-y"
        role="img"
        aria-label="组合与沪深300ETF累计收益曲线"
        onPointerMove={onPointerMove}
        onPointerLeave={() => setHoverIndex(null)}
      >
        {chart.ticks.map(tick => (
          <g key={tick.value}>
            <line
              x1={PADDING.left}
              x2={WIDTH - PADDING.right}
              y1={tick.y}
              y2={tick.y}
              stroke="hsl(var(--border))"
              strokeWidth="1"
              strokeDasharray="4 5"
            />
            <text
              x={PADDING.left - 8}
              y={tick.y + 4}
              textAnchor="end"
              fontSize="11"
              fill="hsl(var(--muted-foreground))"
            >
              {(tick.value * 100).toFixed(0)}%
            </text>
          </g>
        ))}
        <path d={chart.benchmarkPath} fill="none" stroke="#f59e0b" strokeWidth="2.25" />
        <path
          d={chart.portfolioPath}
          fill="none"
          stroke="hsl(var(--primary))"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <line
          x1={activeX}
          x2={activeX}
          y1={PADDING.top}
          y2={HEIGHT - PADDING.bottom}
          stroke="hsl(var(--foreground) / 0.25)"
          strokeDasharray="3 4"
        />
        {activePortfolioY != null && (
          <circle
            cx={activeX}
            cy={activePortfolioY}
            r="4.5"
            fill="hsl(var(--card))"
            stroke="hsl(var(--primary))"
            strokeWidth="3"
          />
        )}
        <text
          x={PADDING.left}
          y={HEIGHT - 10}
          textAnchor="start"
          fontSize="11"
          fill="hsl(var(--muted-foreground))"
        >
          {data[0].snapshot_date}
        </text>
        <text
          x={WIDTH - PADDING.right}
          y={HEIGHT - 10}
          textAnchor="end"
          fontSize="11"
          fill="hsl(var(--muted-foreground))"
        >
          {data[data.length - 1].snapshot_date}
        </text>
      </svg>
    </div>
  )
}
