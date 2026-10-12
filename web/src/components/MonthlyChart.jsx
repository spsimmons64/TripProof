import { useState } from 'react'
import { count, money, money0 } from '../lib/format.js'

// Billed dollars per month, stacked: at risk (orange, on the baseline - the part that matters) under
// covered (light teal). Two series, so a legend names them; hover a column for the exact figures; the
// visually hidden table carries the same numbers for screen readers and print.
const W = 640, H = 230, PAD = { t: 12, r: 8, b: 26, l: 60 }
const GAP = 2   // surface gap between the stacked segments

function niceMax(v) {
  if (v <= 0) return 100
  const p = 10 ** Math.floor(Math.log10(v))
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((x) => x >= v)
}

// A column segment with an optional 4px rounded top; the bottom stays square on the baseline.
function segment(x, top, w, bottom, rounded) {
  const h = bottom - top
  if (h <= 0) return ''
  const r = rounded ? Math.min(4, h, w / 2) : 0
  return `M${x},${bottom} V${top + r} Q${x},${top} ${x + r},${top} H${x + w - r} Q${x + w},${top} ${x + w},${top + r} V${bottom} Z`
}

export default function MonthlyChart({ data }) {
  const [hover, setHover] = useState(null)
  if (!data?.length) return <div className="muted">No trips imported yet.</div>
  const max = niceMax(Math.max(...data.map((d) => Number(d.billed))))
  const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b
  const band = iw / data.length
  const bw = Math.min(24, band * 0.6)
  const y = (v) => PAD.t + ih - (Number(v) / max) * ih
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max)
  const label = (m) => {
    const [yy, mm] = m.split('-')
    return new Date(Number(yy), Number(mm) - 1, 1).toLocaleString('en-US', { month: 'short', year: '2-digit' })
  }
  const hd = hover !== null ? data[hover] : null

  return (
    <div className="chart">
      <div className="legend" aria-hidden="true">
        <span><span className="key" style={{ background: 'var(--orange)' }} />At risk</span>
        <span><span className="key" style={{ background: 'var(--teal-300)' }} />Covered</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Billed dollars by month, at risk and covered">
        {ticks.map((t) => (
          <g key={t}>
            <line className="gridline" x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} />
            <text className="tick" x={PAD.l - 8} y={y(t) + 4} textAnchor="end">{money0(t)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const x = PAD.l + band * i + band / 2 - bw / 2
          const risk = Number(d.atrisk), billed = Number(d.billed)
          const riskTop = y(risk)
          const coveredBottom = risk > 0 ? riskTop - GAP : y(0)
          return (
            <g key={d.month} className={hover === i ? 'hover' : ''} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect className="hit" x={PAD.l + band * i} y={PAD.t} width={band} height={ih} />
              <path className="seg-risk" d={segment(x, riskTop, bw, y(0), billed <= risk)} style={{ pointerEvents: 'none' }} />
              <path className="seg-covered" d={segment(x, y(billed), bw, coveredBottom, true)} style={{ pointerEvents: 'none' }} />
              {(data.length <= 12 || i % Math.ceil(data.length / 12) === 0) && (
                <text className="tick" x={x + bw / 2} y={H - 8} textAnchor="middle">{label(d.month)}</text>
              )}
            </g>
          )
        })}
      </svg>
      {hd && (
        <div className="tooltip" style={{ left: `${((PAD.l + band * hover + band / 2) / W) * 100}%`, top: `${(y(hd.billed) / H) * 100}%` }}>
          <div className="muted">{label(hd.month)}</div>
          <div>At risk <b>{money(hd.atrisk)}</b> ({count(hd.risktrips)} trips)</div>
          <div>Covered <b>{money(Number(hd.billed) - Number(hd.atrisk))}</b></div>
          <div className="muted">Billed {money(hd.billed)} across {count(hd.trips)} trips</div>
        </div>
      )}
      <table className="sr-only">
        <caption>Billed dollars by month</caption>
        <thead><tr><th>Month</th><th>At risk</th><th>Trips at risk</th><th>Covered</th><th>Billed</th></tr></thead>
        <tbody>{data.map((d) => (
          <tr key={d.month}><td>{d.month}</td><td>{money(d.atrisk)}</td><td>{d.risktrips}</td>
            <td>{money(Number(d.billed) - Number(d.atrisk))}</td><td>{money(d.billed)}</td></tr>
        ))}</tbody>
      </table>
    </div>
  )
}
