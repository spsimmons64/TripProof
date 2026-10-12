import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'
import { count } from '../lib/format.js'

export const PAGE_SIZES = [25, 50, 100]

// Page numbers to show: always first and last, a window around the current page, gaps as "…".
function pages(current, last) {
  const out = []
  for (let p = 1; p <= last; p++) {
    if (p === 1 || p === last || Math.abs(p - current) <= 1) out.push(p)
    else if (out[out.length - 1] !== '…') out.push('…')
  }
  return out
}

// Grid footer: "Showing 26-50 of 312", rows-per-page, and first/prev/numbers/next/last.
// `small` is the same pager in a panel rather than under a grid: no rows-per-page, tighter type.
// A second pager written from scratch for small spaces is how two pagers end up behaving
// differently, so this is a size rather than a component.
export default function Pager({ total, page, pagesize, onPage, onPageSize, noun = 'rows',
                                small }) {
  const last = Math.max(1, Math.ceil(total / pagesize))
  const from = total ? (page - 1) * pagesize + 1 : 0
  const to = Math.min(total, page * pagesize)
  return (
    <div className={`pager${small ? ' pagersm' : ''}`}>
      <div className="muted small">
        {total ? <>Showing <b>{count(from)}-{count(to)}</b> of <b>{count(total)}</b> {noun}</> : `No ${noun}`}
      </div>
      <div className="row">
        {onPageSize && (
          <label className="small muted row" style={{ gap: 6 }}>
            Rows per page
            <select value={pagesize} onChange={(e) => onPageSize(Number(e.target.value))}>
              {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        )}
        <nav className="pages" aria-label="Pages">
          <button className="pg" onClick={() => onPage(1)} disabled={page <= 1} aria-label="First page"><ChevronsLeft size={14} /></button>
          <button className="pg" onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="Previous page"><ChevronLeft size={14} /></button>
          {pages(page, last).map((p, i) => p === '…'
            ? <span key={`gap${i}`} className="gap">…</span>
            : <button key={p} className={`pg${p === page ? ' on' : ''}`} onClick={() => onPage(p)} aria-current={p === page ? 'page' : undefined}>{p}</button>)}
          <button className="pg" onClick={() => onPage(page + 1)} disabled={page >= last} aria-label="Next page"><ChevronRight size={14} /></button>
          <button className="pg" onClick={() => onPage(last)} disabled={page >= last} aria-label="Last page"><ChevronsRight size={14} /></button>
        </nav>
      </div>
    </div>
  )
}
