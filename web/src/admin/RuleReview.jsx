import { useEffect, useState } from 'react'
import { Search, SlidersHorizontal, X } from 'lucide-react'
import { api } from '../lib/api.js'
import { date } from '../lib/format.js'
import { useLoad } from '../components/ui.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'
import { useCanEdit } from './common.jsx'

// Every platform rule, by the qualification it proves, and whether somebody qualified has signed it
// off as a correct statement of what it cites. Only an approved rule may ever be enforced against
// a trip; a draft is recorded in shadow and nothing more. Each decision is kept as a new version.
const CATEGORY = { FEDERAL_GENERAL: 'Federal General', STATE_GENERAL: 'State General',
  FEDERAL_MEDICAID: 'Federal Medicaid', STATE_MEDICAID: 'State Medicaid',
  CONTRACT_COMPANY: 'Contract / Company' }
const LABEL = { draft: 'Draft', reviewed: 'Reviewed', approved: 'Approved', retired: 'Retired' }

const COLUMNS = [
  { id: 'code', label: 'Code', width: 110, firstDir: 'asc' },
  { id: 'qualification', label: 'Qualification', firstDir: 'asc' },
  { id: 'state', label: 'State', width: 90, className: 'center', firstDir: 'asc' },
  { id: 'category', label: 'Category', width: 170, firstDir: 'asc' },
  { id: 'version', label: 'Version', width: 110, className: 'center' },
  { id: 'reviewed', label: 'Reviewed', width: 120, className: 'center' },
  { id: 'status', label: 'Status', width: 140, firstDir: 'asc' },
]

export default function RuleReview() {
  const g = useGridParams({ filters: ['status', 'category', 'state'], defaultSort: 'code',
    defaultDir: 'asc' })
  const [data, error, reload] = useLoad(() => api.get(`/admin/rules?${g.query}`), [g.query])
  const editable = useCanEdit()
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (data) g.fitPage(data.total) }, [data])
  const { status, category, state } = g.filters

  const review = async (code, legalreview) => {
    setBusy(code); setErr(null)
    try { await api.put(`/admin/rules/${code}/review`, { legalreview }); await reload() }
    catch (e) { setErr(e.message) } finally { setBusy(null) }
  }

  return (
    <div className="fill">
      <div className="pagehead">
        <div>
          <h1>Rule Review</h1>
          {data && <div className="small muted">
            {data.states.map((s) => `${LABEL[s]} ${data.counts[s] || 0}`).join(' · ')}
          </div>}
        </div>
        <div className="row">
          <div className="searchbox"><Search size={14} />
            <input placeholder="Search Rules" value={g.search} onChange={(e) => g.setSearch(e.target.value)} />
          </div>
        </div>
      </div>
      {err && <div className="notice bad">{err}</div>}

      <div className="filterbar">
        <span className="filtertitle"><SlidersHorizontal size={15} /> Filters</span>
        <label className="filter">Status
          <select value={status} onChange={(e) => g.setFilter('status', e.target.value)}>
            <option value="">All</option>
            {Object.entries(LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        <label className="filter">Category
          <select value={category} onChange={(e) => g.setFilter('category', e.target.value)}>
            <option value="">All</option>
            {Object.entries(CATEGORY).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        <label className="filter">State
          <select value={state} onChange={(e) => g.setFilter('state', e.target.value)}>
            <option value="">All</option>
            {(data?.jurisdictions || []).map((j) => <option key={j} value={j}>{j}</option>)}
          </select>
        </label>
        {g.filtered && (
          <button className="linkbtn" onClick={g.clear}><X size={14} /> Clear filters</button>
        )}
      </div>

      <DataGrid columns={COLUMNS} rows={data?.items} rowKey={(r) => r.code} error={error}
        sort={g.sort} dir={g.dir} onSort={g.onSort}
        empty={g.filtered ? 'No rules match these filters.' : 'No rules.'}
        pager={g.pager(data?.total, 'rules')}
        cells={(r) => [
          r.qualificationcode || '-',
          // The source under the name: who asks, and each part of what they cite, opening the
          // text itself so the rule can be checked against it.
          <>{r.qualification || '-'}
            <span className="rowemail keepcase rowsource">
              {(() => {
                // The whole source is the link - who asks and what they cite - opening the first
                // part of it that has a page to read.
                const text = [r.authority, r.links.map((l) => l.text).join('; ')]
                  .filter(Boolean).join(' - ')
                const url = r.links.find((l) => l.url)?.url
                return url
                  ? <a href={url} target="_blank" rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}>{text}</a>
                  : text
              })()}
            </span></>,
          r.jurisdiction || '-',
          CATEGORY[r.authoritycategory] || '-',
          r.version ?? '-',
          // Yes or No; when and by whom on hover.
          r.legalreviewedon
            ? <span className="hashelp" title={[date(r.legalreviewedon), r.legalreviewedby].filter(Boolean).join(' · ')}>Yes</span>
            : 'No',
          editable ? (
            <select value={r.legalreview} disabled={busy === r.code}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => review(r.code, e.target.value)}>
              {Object.entries(LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          ) : LABEL[r.legalreview],
        ]} />
    </div>
  )
}
