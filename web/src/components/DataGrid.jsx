import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Pager, { PAGE_SIZES } from './Pager.jsx'
import SortHeader from './SortHeader.jsx'

// THE grid. Every list in TripProof is one of these, styled after the customer grid: a card that
// fills the playground, a deep-teal header band with sortable headings, rows that scroll beneath it
// (the scrollbar belongs to the rows, never the headings), and the pager pinned at the bottom.
//
//   columns   [{ id, label, width?, numeric?, sortable? (default true), firstDir?, className? }]
//             A column without a width takes what's left; give every other column one. The header
//             and the rows are separate boxes, so the widths are what keep them lined up.
//   rows      the page of items; `rowKey(item)` identifies each, `cells(item)` returns one node per column
//   sort/dir/onSort   current sort and the handler (omit onSort for a grid that doesn't sort)
//   onRowClick        optional; makes rows clickable
//   rowClickable      optional; given an item, says whether that one row opens - a row that does
//                     not is shown plainly, without the hand cursor or the hover
//   rowClass  optional; given an item, a class for its row and the line under it - a whole row
//             said in one colour, such as a missed pickup
//   card      optional; given an item, the whole of it as one card. When given, the rows are laid
//             out as cards in the same frame - the sort band above, the pager below - and the
//             band keeps only the headings that sort, since there are no columns under them
//   pager     { total, page, pagesize, noun, onPage, onPageSize } - omit for a grid without paging
//   A column may carry a NODE as its label, which is how a grid holds its own title and its own
//   actions in the header band - see the driver's hours of service grid.
export default function DataGrid({ columns, rows, rowKey, cells, sort, dir, onSort, onRowClick, rowClickable, rowClass, loading, error,
  empty = 'Nothing here yet.', pager, subrow, card: asCard, className = '' }) {
  const card = useRef(null)
  // The header's spacer must be exactly as wide as the rows' scrollbar. Measure this grid's own rows
  // (offsetWidth - clientWidth) rather than trusting a page-wide guess: it varies by browser, zoom
  // and OS, and is 0 where scrollbars float over the content.
  useLayoutEffect(() => {
    const el = card.current
    const body = el?.querySelector('tbody')
    if (!body) return
    const measure = () => el.style.setProperty('--sbw', `${body.offsetWidth - body.clientWidth}px`)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(body)
    return () => ro.disconnect()
  }, [])
  // With no rows the table must stop claiming the height, or it takes the whole card and leaves
  // the message sitting at the bottom of a white expanse - which is where every empty grid on the
  // site was putting it.
  const bare = !rows || rows.length === 0
  if (asCard) {
    const sorts = columns.filter((c) => onSort && c.sortable !== false && c.label)
    return (
      <div ref={card} className={`card gridcard cardview${bare ? ' isbare' : ''} ${className}`}>
        <div className="tablewrap">
          <table className="cardsorts"><thead><tr>
            {sorts.map((c) => (
              <SortHeader key={c.id} id={c.id} label={c.label} sort={sort} dir={dir} onSort={onSort}
                numeric={c.numeric} firstDir={c.firstDir} />
            ))}
            <th />
          </tr></thead></table>
          {rows && rows.length > 0 && (
            <div className="cardgrid">
              {rows.map((item) => (
                <div key={rowKey(item)} className={['gridcarditem', rowClass?.(item)].filter(Boolean).join(' ')}>
                  {asCard(item)}
                </div>
              ))}
            </div>
          )}
          {!rows && <div className="gridempty">{error ? <span className="error">{error}</span> : loading ?? 'Loading…'}</div>}
          {rows && rows.length === 0 && <div className="gridempty">{empty}</div>}
        </div>
        {pager && <Pager {...pager} total={pager.total || 0} />}
      </div>
    )
  }
  return (
    <div ref={card} className={`card gridcard${bare ? ' isbare' : ''} ${className}`}>
      <div className="tablewrap">
        <table>
          <thead><tr>
            {columns.map((c) => {
              const style = c.width ? { width: c.width } : undefined
              const cls = [c.numeric && 'num', c.className].filter(Boolean).join(' ') || undefined
              if (onSort && c.sortable !== false && c.label) {
                return <SortHeader key={c.id} id={c.id} label={c.label} sort={sort} dir={dir} onSort={onSort}
                  numeric={c.numeric} firstDir={c.firstDir} style={style} className={c.className} />
              }
              return <th key={c.id} className={cls} style={style}>{c.label || <span className="sr-only">{c.srLabel || c.id}</span>}</th>
            })}
            {/* As wide as the rows' scrollbar, so each heading stays over its column (styles.css, .gridcard). */}
            <th className="sbgutter" aria-hidden="true" />
          </tr></thead>
          <tbody>{(rows || []).map((item) => {
            const values = cells(item)
            const opens = Boolean(onRowClick) && (!rowClickable || rowClickable(item))
            // A second line under the row, spanning it. For the thing that will not fit in a
            // column and should not be cut to fit one - an address, a route - where squeezing it
            // into a cell means an ellipsis in the middle of a street name.
            const under = subrow?.(item)
            const tone = rowClass?.(item) || null
            return (
              <Fragment key={rowKey(item)}>
                <tr className={[opens ? 'click' : null, under ? 'hassub' : null, tone].filter(Boolean).join(' ') || undefined}
                    onClick={opens ? () => onRowClick(item) : undefined}>
                  {columns.map((c, i) => (
                    <td key={c.id} className={[c.numeric && 'num', c.className].filter(Boolean).join(' ') || undefined}
                      style={c.width ? { width: c.width } : undefined}>{values[i]}</td>
                  ))}
                </tr>
                {under && (
                  <tr className={['subrow', opens ? 'click' : null, tone].filter(Boolean).join(' ')}
                      onClick={opens ? () => onRowClick(item) : undefined}>
                    <td colSpan={columns.length + 1}>{under}</td>
                  </tr>
                )}
              </Fragment>
            )
          })}</tbody>
        </table>
        {!rows && <div className="gridempty">{error ? <span className="error">{error}</span> : loading ?? 'Loading…'}</div>}
        {rows && rows.length === 0 && <div className="gridempty">{empty}</div>}
      </div>
      {pager && <Pager {...pager} total={pager.total || 0} />}
    </div>
  )
}

// A grid's view state - search, filters, sort, page, page size - kept in the URL so a view can be
// linked or reloaded. `filters` names the filter params; `defaultSort` is the column sorted by when
// none is chosen. Search is applied a beat after the last keystroke and starts again at page 1.
export function useGridParams({ filters = [], defaultSort = 'name', defaultDir = 'asc' } = {}) {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const page = Math.max(1, Number(params.get('page') || 1))
  const pagesize = PAGE_SIZES.includes(Number(params.get('size'))) ? Number(params.get('size')) : PAGE_SIZES[0]
  const sort = params.get('sort') || defaultSort
  const dir = params.get('dir') === 'desc' ? 'desc' : params.get('dir') === 'asc' ? 'asc' : defaultDir
  const values = Object.fromEntries(filters.map((f) => [f, params.get(f) || '']))
  const [search, setSearch] = useState(q)

  const update = (changes) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) {
      const isDefault = v === '' || v === null || v === undefined || (k === 'page' && v === 1) ||
        (k === 'sort' && v === defaultSort) || (k === 'dir' && v === defaultDir) || (k === 'size' && v === PAGE_SIZES[0])
      if (isDefault) next.delete(k); else next.set(k, v)
    }
    setParams(next, { replace: true })
  }
  useEffect(() => {
    if (search === q) return
    const t = setTimeout(() => update({ q: search, page: 1 }), 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  const query = new URLSearchParams({ page, pagesize, sort, dir, ...(q && { q }),
    ...Object.fromEntries(Object.entries(values).filter(([, v]) => v)) }).toString()
  const filtered = !!q || Object.values(values).some(Boolean)
  return {
    q, page, pagesize, sort, dir, filters: values, query, filtered, search, setSearch,
    setFilter: (name, value) => update({ [name]: value, page: 1 }),
    clear: () => { setSearch(''); update({ q: '', page: 1, ...Object.fromEntries(filters.map((f) => [f, ''])) }) },
    onSort: (id, next) => update({ sort: id, dir: next, page: 1 }),
    // Stepping past the last page (e.g. after a search narrows the list) snaps back to it.
    fitPage: (total) => { if (total && page > Math.ceil(total / pagesize)) update({ page: Math.ceil(total / pagesize) }) },
    pager: (total, noun) => ({ total, page, pagesize, noun, onPage: (p) => update({ page: p }),
      onPageSize: (n) => update({ size: n, page: 1 }) }),
  }
}
