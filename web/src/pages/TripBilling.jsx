import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Download, Loader2, Search } from 'lucide-react'
import { api } from '../lib/api.js'
import { date, money, tzDateTime } from '../lib/format.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'

// Every finished trip priced on its own: the clean ones Ready To Bill, the rest Exceptions with the
// reason. One button bills what is ticked, each trip the way its payer is billed.
const TILES = [['ready', 'Ready To Bill'], ['submitted', 'Submitted'], ['exceptions', 'Exceptions'], ['outstanding', 'Outstanding'], ['paid', 'Paid']]
const AGES = [['current', '0-30 Days'], ['over30', '31-60 Days'], ['over60', '61-90 Days'], ['over90', 'Over 90 Days']]
const NONE = { ready: 'No Trips Ready To Bill', submitted: 'Nothing Awaiting Payment', exceptions: 'No Exceptions', outstanding: 'Nothing Outstanding', paid: 'No Payments Yet' }

export default function TripBilling() {
  const g = useGridParams({ filters: ['state', 'payer'], defaultSort: 'tripdate', defaultDir: 'asc' })
  const state = g.filters.state || 'ready'
  const [data, error, reload] = useLoad(() => api.get(`/trip-billing?${g.query}&state=${state}`), [g.query, state])
  const [open, setOpen] = useState(null)
  const [ticked, setTicked] = useState(new Set())
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [billed, setBilled] = useState(null)
  const [posting, setPosting] = useState(null)      // the batch whose payment is being posted
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (data) g.fitPage(data.total) }, [data])
  const items = data?.items || []
  const allOn = items.length > 0 && items.every((t) => ticked.has(t.recordid))
  const flip = (id) => { const n = new Set(ticked); if (n.has(id)) n.delete(id); else n.add(id); setTicked(n) }
  const bill = async () => {
    setBusy(true); setErr(null)
    try { setBilled(await api.post('/trip-billing/bill', { tripids: [...ticked] })); setTicked(new Set()); reload() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const t = data?.tiles
  const columns = {
    ready: [{ id: 'tick', label: '', srLabel: 'Choose', width: 50, sortable: false }, { id: 'tripdate', label: 'Date', width: 120 }, { id: 'externalid', label: 'Trip', width: 210 },
            { id: 'passenger', label: 'Passenger' }, { id: 'payer', label: 'Payer', width: 170 }, { id: 'miles', label: 'Miles', width: 90, numeric: true },
            { id: 'amount', label: 'Amount', width: 120, numeric: true }, { id: 'sends', label: 'Sends As', width: 170, sortable: false }],
    submitted: [{ id: 'tripdate', label: 'Date', width: 120 }, { id: 'externalid', label: 'Trip', width: 210 }, { id: 'passenger', label: 'Passenger' },
                { id: 'payer', label: 'Payer', width: 170 }, { id: 'amount', label: 'Amount', width: 120, numeric: true }, { id: 'batchnumber', label: 'Batch / Invoice', width: 150 }],
    exceptions: [{ id: 'tripdate', label: 'Date', width: 120 }, { id: 'externalid', label: 'Trip', width: 210 }, { id: 'passenger', label: 'Passenger', width: 220 },
                 { id: 'payer', label: 'Payer', width: 150 }, { id: 'amount', label: 'Amount', width: 110, numeric: true }, { id: 'reason', label: 'Reason' }],
    outstanding: [{ id: 'tripdate', label: 'Date', width: 120 }, { id: 'externalid', label: 'Trip', width: 210 }, { id: 'passenger', label: 'Passenger' }, { id: 'payer', label: 'Payer', width: 170 },
                  { id: 'amount', label: 'Billed', width: 110, numeric: true }, { id: 'owing', label: 'Balance', width: 110, numeric: true }, { id: 'age', label: 'Days', width: 80, numeric: true }],
    paid: [{ id: 'tripdate', label: 'Date', width: 120 }, { id: 'externalid', label: 'Trip', width: 210 }, { id: 'passenger', label: 'Passenger' }, { id: 'payer', label: 'Payer', width: 170 },
           { id: 'amount', label: 'Billed', width: 120, numeric: true }, { id: 'paid', label: 'Paid', width: 120, numeric: true }, { id: 'stands', label: 'Status', width: 150, sortable: false }],
  }[state]
  const cells = (x) => {
    const base = [date(x.tripdate), x.externalid, <b>{x.passenger}</b>, x.payer]
    if (state === 'ready') {
      return [<input type="checkbox" checked={ticked.has(x.recordid)} aria-label={`Choose ${x.externalid}`}
        onClick={(e) => e.stopPropagation()} onChange={() => flip(x.recordid)} />, ...base, x.miles?.toFixed(1), money(x.amount),
        x.brokerid ? `${x.payer} Batch` : 'Invoice']
    }
    if (state === 'submitted') return [...base, money(x.amount), x.batchnumber || `Invoice ${x.invoicenumber}`]
    if (state === 'exceptions') return [...base, money(x.amount), <span className="st-expired">{x.reason}{x.more ? ` (+${x.more} more)` : ''}</span>]
    if (state === 'outstanding') return [...base, money(x.amount), money(x.owing), x.age]
    const short = x.amount - x.paid - x.writedown - x.refunded
    return [...base, money(x.amount), money(x.paid), short > 0.004 ? <span className="st-expired">Short {money(short)}</span>
      : x.refunded > 0 ? `Refunded ${money(x.refunded)}` : x.writedown > 0 ? `Written Down ${money(x.writedown)}` : <span className="st-active">Paid In Full</span>]
  }
  return (
    <div className="fill billingpage">
      <div className="pagehead">
        <h1>Billing</h1>
        <div className="row">
          <div className="searchbox"><Search size={14} /><input placeholder="Search Trips" value={g.search} onChange={(e) => g.setSearch(e.target.value)} /></div>
          <select aria-label="Payer" value={g.filters.payer} onChange={(e) => g.setFilter('payer', e.target.value)}>
            <option value="">All Payers</option>
            {(data?.payers || []).map((p) => <option key={p}>{p}</option>)}
          </select>
          {state === 'submitted' && (data?.batches || []).length > 0 && (
            <select aria-label="Post Batch Payment" value="" onChange={(e) => setPosting(e.target.value)}>
              <option value="">Post Batch Payment</option>
              {data.batches.map((b) => <option key={b.batchid} value={b.batchid}>Batch {b.number} - {b.payer} ({b.trips})</option>)}
            </select>
          )}
          {state === 'ready' && <button type="button" onClick={() => setTicked(allOn ? new Set() : new Set(items.map((x) => x.recordid)))}>{allOn ? 'Untick All' : 'Tick All'}</button>}
          {state === 'ready' && (
            <button type="button" className="primary" disabled={busy || !ticked.size} onClick={bill}>
              {busy ? <Loader2 size={15} className="spin" /> : `Bill ${ticked.size || ''} Trip${ticked.size === 1 ? '' : 's'}`}
            </button>
          )}
        </div>
      </div>
      {err && <div className="notice bad">{err}</div>}
      <div className="billtiles">
        {TILES.map(([k, label]) => (
          <button key={k} type="button" className={`${state === k ? 'on' : ''}${k === 'exceptions' && t?.exceptions.count ? ' alert' : ''}`}
            onClick={() => { setTicked(new Set()); g.setFilter('state', k) }}>
            <span>{label}</span>
            <b>{!t ? '-' : k === 'exceptions' ? t.exceptions.count : money(t[k].amount)}</b>
            <small>{!t ? '' : k === 'exceptions' ? 'Need Someone To Look' : k === 'paid' ? 'Received This Month' : `${t[k].count} Trip${t[k].count === 1 ? '' : 's'}`}</small>
          </button>
        ))}
      </div>
      {state === 'outstanding' && data && (
        <div className="wcstats agestrip">
          {AGES.map(([k, l]) => <span key={k} className={k !== 'current' && data.aging[k] > 0 ? 'bad' : ''}><b>{money(data.aging[k])}</b> {l}</span>)}
        </div>
      )}
      <DataGrid rows={data?.items} rowKey={(x) => x.recordid} error={error} columns={columns} sort={g.sort} dir={g.dir} onSort={g.onSort}
        onRowClick={(x) => setOpen(x.recordid)} pager={data && g.pager(data.total, 'trip')} empty={NONE[state]} cells={cells} />
      {open && <TripDialog tripid={open} onClose={() => setOpen(null)} onDone={() => { setOpen(null); reload() }} />}
      {posting && <BatchPayment batchid={posting} onClose={() => setPosting(null)} onDone={() => { setPosting(null); reload() }} />}
      {billed && (
        <Modal title="Billed" width={600} onClose={() => setBilled(null)}
          footer={<button type="button" className="primary" onClick={() => setBilled(null)}>OK</button>}>
          <div className="stack">
            {billed.batches.map((b) => (
              <div key={b.batchid} className="billedline">
                <span>{b.payer}: Batch {b.number}, {b.trips} trip{b.trips === 1 ? '' : 's'}, {money(b.amount)}</span>
                <button type="button" onClick={() => api.download(`/trip-billing/batches/${b.batchid}/export`, `batch-${b.number}.csv`)}><Download size={13} /> Download</button>
              </div>
            ))}
            {billed.invoices.length > 0 && (
              <div className="billedline">
                <span>Private Pay: {billed.invoices.length} invoice{billed.invoices.length === 1 ? '' : 's'}, {money(billed.invoices.reduce((a, i) => a + i.amount, 0))}.
                  {' '}{billed.invoices.filter((i) => i.email).length} emailed, {billed.invoices.filter((i) => !i.email).length} to print.</span>
                <button type="button" onClick={() => api.download(`/trip-billing/invoices/pdf?ids=${billed.invoices.map((i) => i.invoiceid).join(',')}`, 'invoices.pdf')}><Download size={13} /> Download</button>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}

// What a broker paid against a batch: every trip paid in full to start with; change the ones that
// were short, or tick those denied, with why.
function BatchPayment({ batchid, onClose, onDone }) {
  const [b, error] = useLoad(() => api.get(`/trip-billing/batches/${batchid}`), [batchid])
  const [edits, setEdits] = useState({})
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  if (!b) return <Modal title="Post Batch Payment" onClose={onClose}><Loading error={error} /></Modal>
  const line = (x) => ({ amount: x.owing.toFixed(2), denied: false, note: '', ...edits[x.recordid] })
  const put = (x, patch) => setEdits({ ...edits, [x.recordid]: { ...line(x), ...patch } })
  const total = b.trips.reduce((a, x) => a + (line(x).denied ? 0 : Number(line(x).amount) || 0), 0)
  const ready = b.trips.every((x) => { const l = line(x); return l.denied ? l.note.trim() : l.amount !== '' })
  const post = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/trip-billing/batches/${batchid}/payment`, { lines: b.trips.map((x) => {
        const l = line(x)
        return { tripid: x.recordid, denied: l.denied, note: l.note || null, amount: l.denied ? null : l.amount }
      }) })
      onDone()
    } catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <Modal title={`Post Batch Payment - Batch ${b.number}`} width={1000} onClose={onClose}
      footer={<>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy || !ready || !b.trips.length} onClick={post}>
          {busy ? <Loader2 size={15} className="spin" /> : `Post ${money(total)}`}</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="billscroll batchscroll">
          <table className="residencetable recordtable reviewtable batchtable">
            <thead><tr><th>Trip</th><th>Passenger</th><th>Balance</th><th>Amount Paid</th><th>Denied</th><th>Note</th></tr></thead>
            <tbody>{b.trips.map((x) => {
              const l = line(x)
              return (
                <tr key={x.recordid}>
                  <td>{x.externalid}</td><td>{x.passenger}</td><td>{money(x.owing)}</td>
                  <td><input type="number" min="0" step="0.01" disabled={l.denied} value={l.denied ? '' : l.amount} onChange={(e) => put(x, { amount: e.target.value })} /></td>
                  <td><input type="checkbox" checked={l.denied} onChange={(e) => put(x, { denied: e.target.checked })} /></td>
                  <td><textarea rows={1} className="upper" value={l.note} onChange={(e) => put(x, { note: e.target.value.toUpperCase() })} /></td>
                </tr>
              )
            })}</tbody>
          </table>
        </div>
      </div>
    </Modal>
  )
}

function TripDialog({ tripid, onClose, onDone }) {
  const navigate = useNavigate()
  const [t, error] = useLoad(() => api.get(`/trip-billing/${tripid}`), [tripid])
  const [form, setForm] = useState(null)     // 'hold' | 'denied' | 'writedown' | 'refund' | 'undo' | 'miles'
  const [how, setHow] = useState('')         // the amount or miles that form is asking for
  const [target, setTarget] = useState(null) // the payment being undone, or the leg being corrected
  const [note, setNote] = useState('')
  const [paid, setPaid] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const act = async (path, body = {}) => {
    setBusy(true); setErr(null)
    try { await api.post(`/trip-billing/${tripid}/${path}`, body); onDone() } catch (e) { setErr(e.message); setBusy(false) }
  }
  const act2 = async (path, body = {}) => { setBusy(true); setErr(null); try { await api.post(path, body); onDone() } catch (e) { setErr(e.message); setBusy(false) } }
  if (!t) return <Modal title="Trip" onClose={onClose}><Loading error={error} /></Modal>
  if (form) {
    const FORMS = {
      hold: ['Hold Trip', 'Reason', null], denied: ['Payment Denied', 'Note', null], undo: ['Undo Entry', 'Reason', null],
      writedown: ['Write Down', 'Note', 'Amount To Write Down'], refund: ['Record Refund', 'Note', 'Amount Refunded'], miles: ['Correct Miles', 'Reason', 'Miles'],
    }
    const [title, noteLabel, howLabel] = FORMS[form]
    const save = () => {
      if (form === 'hold') return act('hold', { reason: note })
      if (form === 'denied') return act('payment', { denied: true, note })
      if (form === 'writedown') return act('payment', { writedown: how, note })
      if (form === 'refund') return act('refund', { amount: how, note })
      if (form === 'undo') return act2(`/trip-billing/payments/${target}/undo`, { note })
      return act2(`/trip-billing/legs/${target}/miles`, { miles: how, reason: note })
    }
    return (
      <Modal title={`${title} - ${t.externalid}`} width={560} onClose={() => setForm(null)}
        footer={<>
          <button type="button" onClick={() => setForm(null)}>Cancel</button>
          <button type="button" className="primary" disabled={busy || !note.trim() || (howLabel && how === '')} onClick={save}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          {howLabel && <label className="field">{howLabel} *<input type="number" min="0" step="0.01" value={how} onChange={(e) => setHow(e.target.value)} /></label>}
          <label className="field">{noteLabel} *<textarea value={note} className="upper" rows={3} onChange={(e) => setNote(e.target.value.toUpperCase())} /></label>
        </div>
      </Modal>
    )
  }
  const open_ = (kind, value = '', which = null) => { setNote(''); setErr(null); setHow(value); setTarget(which); setForm(kind) }
  const unbilled = ['unbilled', 'held'].includes(t.billingstatus)
  const excepted = t.stops.length > 0 || t.reasons.length > 0
  const amountPaid = paid ?? t.owing.toFixed(2)
  const settling = ['billed', 'paid'].includes(t.billingstatus) && t.owing > 0
  return (
    <Modal title={`Trip - ${t.externalid}`} width={1040} onClose={onClose}
      footer={<>
        <div className="footactions">
          <button type="button" onClick={() => navigate(`/trips/${tripid}`)}>View Trip</button>
          {t.billinvoiceid && <button type="button" onClick={() => api.download(`/trip-billing/invoices/pdf?ids=${t.billinvoiceid}`, `invoice-${t.invoicenumber}.pdf`)}><Download size={13} /> Download Invoice</button>}
          {t.billinvoiceid && t.billtoemail && <button type="button" disabled={busy} onClick={() => act2(`/trip-billing/invoices/${t.billinvoiceid}/email`)}>Resend Email</button>}
          {t.billbatchid && <button type="button" onClick={() => api.download(`/trip-billing/batches/${t.billbatchid}/export`, `batch-${t.batchnumber}.csv`)}><Download size={13} /> Download Batch</button>}
        </div>
        <button type="button" onClick={onClose}>Close</button>
        {unbilled && t.billingstatus !== 'held' && <button type="button" disabled={busy} onClick={() => open_('hold')}>Hold</button>}
        {unbilled && excepted && <button type="button" className="primary" disabled={busy || t.stops.length > 0} onClick={() => act('clear')}>Clear To Bill</button>}
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {(t.stops.length > 0 || t.reasons.length > 0) && (
          <div className="notice bad"><div>{[...t.stops, ...t.reasons].map((s) => <div key={s}>{s}</div>)}</div></div>
        )}
        <div className="kv">
          <dt>Passenger</dt><dd>{t.passenger}</dd>
          <dt>Date</dt><dd>{date(t.tripdate)}</dd>
          <dt>Payer</dt><dd>{t.payer}</dd>
          <dt>Service</dt><dd className="capital">{t.servicelevel}</dd>
          {t.batchnumber && <><dt>Batch</dt><dd>{t.batchnumber}</dd></>}
          {t.invoicenumber && <><dt>Invoice</dt><dd>{t.invoicenumber}</dd></>}
          {t.invoicenumber && <><dt>Emailed</dt><dd>{t.emailedon ? `${tzDateTime(t.emailedon)} to ${t.billtoemail}` : t.emailerror || (t.billtoemail ? 'Sending' : 'No Email On File')}</dd></>}
        </div>
        <div className="billscroll">
        <table className="residencetable recordtable reviewtable">
          <thead><tr><th>Leg</th><th>Driver</th><th>Aboard</th><th>Dropped Off</th><th>Miles</th><th>Waiting</th><th>Signature</th><th>Status</th></tr></thead>
          <tbody>{t.legs.map((l) => (
            <tr key={l.legid}>
              <td>{l.legnumber}</td>
              <td>{l.drivername || 'None'}{l.vehiclename ? ` · ${l.vehiclename}` : ''}</td>
              <td>{l.aboardat ? tzDateTime(l.aboardat) : '-'}</td>
              <td>{l.droppedat ? tzDateTime(l.droppedat) : '-'}</td>
              <td title={l.milesreason || undefined}>{l.miles === null ? '-' : `${(Math.round(l.miles * 10 + 1e-6) / 10).toFixed(1)} (${l.milessource})`}
                {unbilled && <button type="button" className="milesbtn" onClick={() => open_('miles', l.miles === null ? '' : String(l.miles), l.legid)}>Correct Miles</button>}</td>
              <td>{l.waitminutes ? `${l.waitminutes} min` : '-'}</td>
              <td>{l.signature ? 'Yes' : 'No'}</td>
              <td>{l.state}</td>
            </tr>
          ))}</tbody>
        </table>
        <table className="residencetable recordtable reviewtable chargetable">
          <thead><tr><th>Charge</th><th>Code</th><th>Units</th><th>Rate</th><th>Amount</th></tr></thead>
          <tbody>
            {t.lines.map((x) => <tr key={x.label}><td>{x.label}</td><td>{x.code || '-'}</td><td>{x.units}</td><td>{money(x.rate)}</td><td>{money(x.amount)}</td></tr>)}
            <tr className="chargetotal"><td>Total</td><td /><td /><td /><td>{money(t.amount)}</td></tr>
          </tbody>
        </table>
        </div>
        {t.payments.length > 0 && (
          <table className="residencetable recordtable reviewtable paymenttable">
            <thead><tr><th>Recorded</th><th>What</th><th>Amount</th><th>Note</th><th /></tr></thead>
            <tbody>{t.payments.map((p) => (
              <tr key={p.recordid}>
                <td>{tzDateTime(p.recordedon)}</td>
                <td>{p.voidedon ? 'Undone' : p.denied ? 'Denied' : p.refund ? 'Refund' : p.writedown > 0 ? 'Write Down' : 'Payment'}</td>
                <td>{money(p.refund ? p.writedown : p.amount || p.writedown)}</td>
                <td>{p.voidedon ? p.voidreason : p.note || '-'}</td>
                <td className="actions">{!p.voidedon && <button type="button" onClick={() => open_('undo', '', p.recordid)}>Undo</button>}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
        {t.invoicenumber && t.remindercount > 0 && <div className="muted">Reminders Sent: {t.remindercount}, Last {tzDateTime(t.lastremindedon)}</div>}
        {(settling || t.paid > 0) && (
          <div className="settlerow">
            {settling && <>
              <label className="field paidfield">Amount Paid *
                <input type="number" min="0" step="0.01" value={amountPaid} onChange={(e) => setPaid(e.target.value)} />
              </label>
              <button type="button" className="primary" disabled={busy || amountPaid === ''} onClick={() => act('payment', { amount: amountPaid })}>Record The Payment</button>
              {t.broker && t.billingstatus === 'billed' && <button type="button" disabled={busy} onClick={() => open_('denied')}>Payment Denied</button>}
              <button type="button" disabled={busy} onClick={() => open_('writedown', t.owing.toFixed(2))}>Write Down</button>
            </>}
            {t.paid > 0 && <button type="button" disabled={busy} onClick={() => open_('refund', t.paid.toFixed(2))}>Record Refund</button>}
          </div>
        )}
      </div>
    </Modal>
  )
}
