// Requirement dialogs - Screening. Moved out of
// Requirements.jsx, which had grown too large to work in safely.
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Ban, Car, Check, ChevronLeft, Download, FlaskConical, LayoutDashboard, ChevronRight, Clock, ExternalLink, Eye, FileSignature, FileText, FileUp, FolderOpen, History, IdCard, ListChecks, Loader2, MoreHorizontal, Plus, X, Send, UserCheck, UserX } from 'lucide-react'
import { STATE_NAMES } from '../../../lib/states.js'
import { api } from '../../../lib/api.js'
import { useRefreshOnFocus, useWatch } from '../../../lib/live.js'
import { date } from '../../../lib/format.js'
import { Bubble, Loading, useLoad } from '../../../components/ui.jsx'
import { Modal } from '../../../admin/common.jsx'
import Pager, { PAGE_SIZES } from '../../../components/Pager.jsx'
import { useUser } from '../../../App.jsx'
import SignatureBlock from '../../../components/UserSignature.jsx'
import { ItemPanel, PanelsDialog, ReadingViewer, SingleDocumentDialog, docStanding } from '../../../components/RequirementDialogs.jsx'
import DocumentViewer, { DocumentPane } from '../../../components/DocumentViewer.jsx'
import ApplicantForm from '../../../components/ApplicantForm.jsx'
import SignedDocViewer from '../../../components/SignedDocViewer.jsx'
import { PhoneInput } from '../../../components/MaskedInput.jsx'
import LicenseDialog from '../../../components/LicenseDialog.jsx'
import TestDialog from '../../../components/TestDialog.jsx'
import WithdrawDialog, { WithdrawnDialog } from '../../../components/WithdrawDialog.jsx'
import { Email, Phone } from '../../../components/Contact.jsx'
import { BLANK_CRASH, CRASH_STATE, FROM_ROW, unread, when } from '../common.jsx'
import { DriverLicenses } from '../Licenses.jsx'
import { ProhibitionPanel } from '../Testing.jsx'
import { CrashDialog } from '../Accidents.jsx'
import { DETAIL } from './common.jsx'

// 49 CFR asks nothing of this - a broker does. What the screen has to be clear about is what is
// being bought, what it costs, and that the answer is the vendor's finding rather than a verdict on
// the driver: somebody here still has to read it and decide.
//
// What is on offer is not named here. The tiers come from the price list, so adding one or
// changing what it costs is an administrator's job and not a release.
export function BackgroundScreening({ id, item, onClose, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/drivers/${id}/background`), [id])
  const [picked, setPicked] = useState(null)
  const [extras, setExtras] = useState([])     // the add-ons bought on top of the report
  const [upload, setUpload] = useState(null)   // a screening run somewhere else
  const [viewing, setViewing] = useState(null) // the report, open
  const [reviewing, setReviewing] = useState(null)  // and what somebody concluded from it
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (!data) {
    return (
      <Modal title={item.name} onClose={onClose} width={720}
        footer={<button type="button" onClick={onClose}>Close</button>}>
        <Loading error={error} />
      </Modal>
    )
  }
  const running = data.orders.find((o) => !o.receivedon)
  const money = (c) => `$${((c || 0) / 100).toFixed(2)}`
  // The first on offer until somebody says otherwise, rather than a SKU written in here - what
  // an account carries is the vendor's business and differs between companies.
  const reports = data.reports || []
  const tier = picked ?? reports[0]?.sku ?? ''
  // An order carries the SKU it was placed under. The account may since have stopped carrying it,
  // so the name is looked up and the SKU itself stands in when it is gone.
  const named = (sku) => (reports.find((x) => x.sku === sku) || {}).name || sku
  const chosen = reports.find((r) => r.sku === tier)
  const total = (chosen?.price || 0)
    + (data.addons || []).filter((a) => extras.includes(a.flag))
        .reduce((n, a) => n + (a.price || 0), 0)

  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); await reload(); onChanged?.() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (viewing) {
    return <DocumentViewer id={viewing} name="Background Screening"
      onClose={() => setViewing(null)} />
  }

  // What the office concluded. Its own act with its own record of who did it: the report being on
  // file and somebody having read it are two different facts, and an auditor asks about both.
  if (reviewing) {
    const say = (finding) => act(async () => {
      await api.post(`/drivers/${id}/reports/BACKGROUND_SCREENING/${reviewing.recordid}/reviewed`,
                     { finding })
      setReviewing(null)
    })
    return (
      <Modal title="What Does It Say?" width={560} onClose={() => setReviewing(null)}
        footer={<button type="button" onClick={() => setReviewing(null)}>Cancel</button>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="kv">
            <dt>Report</dt><dd>{named(reviewing.tier)}</dd>
            <dt>Came back</dt><dd>{date(reviewing.receivedon)}</dd>
          </div>
          <p className="muted small">
            Recorded against your name. The report stays on file whatever is chosen here.
          </p>
          <div className="formactions">
            {Object.entries(data.outcomes || {}).map(([v, l]) => (
              <button key={v} type="button" className={v === 'clear' ? 'primary' : undefined}
                disabled={busy} onClick={() => say(v)}>{l}</button>
            ))}
          </div>
        </div>
      </Modal>
    )
  }

  // A report run somewhere else. The requirement asks for a screening on file, not for one this
  // product ordered, so filing one is a first-class thing to do rather than a fallback.
  if (upload) {
    const fileIt = async () => {
      setBusy(true); setErr(null)
      try {
        const body = new FormData()
        body.append('issuedon', upload.issuedon)
        if (upload.outcome) body.append('outcome', upload.outcome)
        if (upload.note.trim()) body.append('note', upload.note.trim())
        if (upload.file) body.append('file', upload.file)
        await api.post(`/drivers/${id}/reports/BACKGROUND_SCREENING`, body)
        setUpload(null); await reload(); onChanged?.()
      } catch (e) { setErr(e.message) } finally { setBusy(false) }
    }
    return (
      <Modal title="File A Background Screening" onClose={() => setUpload(null)} width={620}
        footer={<>
          <button type="button" onClick={() => setUpload(null)}>Cancel</button>
          <button type="button" className="primary"
            disabled={busy || !upload.issuedon || !upload.file} onClick={fileIt}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="profileform">
            <label className="field span-3">Date On The Report *
              <input type="date" value={upload.issuedon}
                onChange={(e) => setUpload({ ...upload, issuedon: e.target.value })} />
            </label>
            <label className="field span-3">The Report *
              <input type="file"
                onChange={(e) => setUpload({ ...upload, file: e.target.files[0] || null })} />
            </label>
            {/* Read now or read later, but never silently counted as read. */}
            <label className="field span-3">What Does It Conclude?
              <select value={upload.outcome}
                onChange={(e) => setUpload({ ...upload, outcome: e.target.value })}>
                <option value="">Not reviewed yet</option>
                {Object.entries(data.outcomes || {}).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </label>
            <label className="field span-3">Note
              <textarea value={upload.note}
                onChange={(e) => setUpload({ ...upload, note: e.target.value })} />
            </label>
          </div>
        </div>
      </Modal>
    )
  }

  return (
    <Modal title={item.name} onClose={onClose} brief={item.description} width={880}
      footer={<>
        {/* Filing one obtained elsewhere is always on offer. A company with no account of its own
            still has drivers who were screened - by a broker, by a previous employer's vendor, or
            on paper - and the requirement is satisfied by the report, not by where it came from. */}
        <button type="button" disabled={busy} onClick={() => setUpload({
          issuedon: '', outcome: '', note: '', file: null })}>
          <FileUp size={14} /> File One You Already Have
        </button>
        {!running && data.available && reports.length > 0 && (
          <button type="button" className="primary" disabled={busy || !tier}
            onClick={() => act(() => api.post(`/drivers/${id}/background/order`,
              { reportsku: tier, addons: extras }))}>
            {busy ? <Loader2 size={15} className="spin" /> : `Order - ${money(total)}`}
          </button>
        )}
        {running && (
          <button type="button" disabled={busy}
            onClick={() => act(() => api.post(`/drivers/${id}/background/${running.recordid}/refresh`, {}))}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Check for the result'}
          </button>
        )}
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {/* What has already been ordered, first. Somebody opening this dialog is far more often
            asking "where is the one we did" than "what shall we buy", and the answer was at the
            bottom under everything else. */}
        {data.orders.length > 0 && (
          <table className="residencetable recordtable">
            {/* The actions column is given its width: the table lays out fixed, so without it
                six columns share the room equally and two buttons end up stacked on top of each
                other in a sixth of it. */}
            <thead><tr><th>Ordered</th><th>Depth</th><th>Charged</th><th>Came back</th>
              <th>Status</th><th style={{ width: 250 }} /></tr></thead>
            <tbody>
              {data.orders.map((o) => (
                <tr key={o.recordid}>
                  <td>{date(o.orderedon)}</td>
                  <td>{named(o.tier)}</td>
                  <td>{o.chargecents == null ? '-' : money(o.chargecents)}</td>
                  <td>{o.receivedon ? date(o.receivedon) : '-'}</td>
                  <td className={o.receivedon ? 'st-active' : 'st-ordered'}>
                    {o.vendorstatus === 'failed' ? 'Could not be run'
                      : o.receivedon ? (o.reviewstate === 'reviewed' ? 'Read' : 'Needs reading')
                        : o.vendorstatus === 'waiting' ? 'Waiting for the driver' : 'Running'}
                  </td>
                  {/* Buttons, not prose - the column keeps them on one line rather than
                      wrapping a label a word at a time. */}
                  <td className="actions">
                    <span className="row">
                      {/* The report itself. Nothing can be concluded from one nobody has opened,
                          so reading comes before the finding and not beside it. */}
                      {o.documentid && (
                        <button type="button" onClick={() => setViewing(o.documentid)}>
                          <Eye size={13} /> View
                        </button>
                      )}
                      {o.receivedon && o.reviewstate !== 'reviewed' && (
                        <button type="button" disabled={busy}
                          onClick={() => setReviewing(o)}>Record Finding</button>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* No account, no ordering - and said in a way somebody can act on, because the thing
            that fixes it is two screens away and they would otherwise have to guess. */}
        {!data.available && (
          <div className="notice warn">
            <div>
              <b>This company has no account with backgroundchecks.com yet</b>, so nothing can be
              ordered from here. Set one up under Company &rsaquo; Background Checks - the company
              is billed directly and its own name goes on the paperwork the driver signs.
              <div className="small" style={{ marginTop: 4 }}>
                A screening run somewhere else can still be filed against this requirement.
              </div>
            </div>
          </div>
        )}

        {!data.available ? null : running ? (
          <div className="stack">
            <div className="notice">
              {named(running.tier)} was ordered {date(running.orderedon)}
              {running.orderedbyname ? ` by ${running.orderedbyname}` : ''}. It has not come back
              yet.
              {running.vendor === 'certn'
                ? ' It will arrive on its own; checking is for when you do not want to wait.'
                : ' Check for the result when you want to know where it has got to.'}
            </div>
            {/* What is finished inside it and what is not. A report sits at "running" until
                its slowest part comes back, and a county court can take days - so an office
                looking at one that has not moved since Tuesday can see that it is one search
                outstanding rather than something gone wrong. */}
            {(data.progress || []).length > 0 && (
              <table className="residencetable recordtable">
                <thead><tr><th>Part of the report</th><th>Where it has got to</th></tr></thead>
                <tbody>
                  {data.progress.map((p) => (
                    <tr key={p.what}>
                      <td>{p.what}</td>
                      <td className={p.done ? 'st-active' : 'st-ordered'}>{p.state}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {/* Waiting on the DRIVER, not on the vendor - and that is the one kind of waiting an
                office can do something about. They have been emailed a link; this is the same
                form, opened here, for a driver who is stood in front of somebody. */}
            {running.vendorstatus === 'waiting' && running.vendor === 'backgroundchecks' && (
              <div className="notice warn">
                  <div>
                  <b>Waiting for the driver to fill it in.</b> Nothing is searched until they
                  have given their own details and signed the disclosures. We have emailed them
                  this link, and so has backgroundchecks.com.
                  {running.inviteurl && (
                    <div className="small" style={{ marginTop: 6 }}>
                      <b>Their link</b> - read it out, or send it again:
                      <div className="mono" style={{ wordBreak: 'break-all' }}>
                        {running.inviteurl}
                      </div>
                    </div>
                  )}
                </div>
                <span className="pushright">
                  <ApplicantForm script={data.widgetscript} reportKey={running.vendorref}
                    onDone={(how) => { if (how === 'complete') act(async () => {}) }} />
                </span>
              </div>
            )}
          </div>
        ) : (
          <>
            {data.skuproblem && <div className="notice warn">{data.skuproblem}</div>}
            <h3 className="formsection">What To Order</h3>
            {/* Their reports, at the prices this company pays them. Nothing here is TripProof's
                to price - we do not sell it and take no part of it. */}
            {reports.map((r) => (
              <label key={r.sku} className={`tierpick${tier === r.sku ? ' on' : ''}`}>
                <input type="radio" name="tier" value={r.sku} checked={tier === r.sku}
                  onChange={() => setPicked(r.sku)} />
                <span className="tierbody">
                  <span className="tiername">{r.name} <b>{money(r.price)}</b></span>
                  <span className="tiercovers">{r.covers}</span>
                </span>
              </label>
            ))}
            {(data.addons || []).length > 0 && (
              <>
                <h3 className="formsection">Add To It</h3>
                {data.addons.map((a) => (
                  <label key={a.flag} className="check">
                    <input type="checkbox" checked={extras.includes(a.flag)}
                      onChange={(e) => setExtras(e.target.checked
                        ? [...extras, a.flag] : extras.filter((x) => x !== a.flag))} />
                    {a.name} <b>{money(a.price)}</b>
                  </label>
                ))}
              </>
            )}
          </>
        )}

      </div>
    </Modal>
  )
}

// Where a driver stands against the exclusion lists.
//
// Two moments, and they look nothing alike. Almost always: clear, and the only thing worth showing
// is the run of months proving somebody checked. Rarely: a possible match, which is urgent, is not
// an accusation - names repeat - and can only be settled on OIG's own site against the SSN.
const OIG_SEARCH = 'https://exclusions.oig.hhs.gov/'

const PAGE = 12

const SOURCE_SITES = {
  OIG_LEIE: ['OIG exclusion list', OIG_SEARCH],
  SAM_EXCLUSIONS: ['SAM.gov', 'https://sam.gov/search'],
}

// Lists no longer offered, kept only so a check already recorded against one still reads as what it
// was. A screening history is a record of what somebody did, not of what the software offers today.
const RETIRED_SOURCES = { FL_AHCA: 'Florida sanctioned providers' }

const sourceName = (code) =>
  (SOURCE_SITES[code] || [])[0] || RETIRED_SOURCES[code] || code || 'OIG exclusion list'

export function ExclusionDetail({ id, r, which, records, onClose, onChanged }) {
  const today = new Date().toISOString().slice(0, 10)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [mode, setMode] = useState(null)              // 'record' | 'settle'
  const [viewing, setViewing] = useState(null)
  const [history, setHistory] = useState(false)
  const [page, setPage] = useState(0)
  const [f, setF] = useState({ source: 'OIG_LEIE', checkedon: today, names: '', result: 'clear',
    note: '', file: null, verdict: 'clear' })

  // Only the list this requirement is about. A SAM.gov match is not settled from the OIG dialog.
  const mine = records.filter((x) => !which || x.source === which)
  const open = mine.find((x) => x.determination === 'review')
  // A confirmed exclusion nobody has lifted. It is the only thing on this screen that stops a
  // driver working, so it is the only thing with a way out of it.
  const barred = mine.find((x) => x.determination === 'flagged' && !x.liftedon)
  // The latest screening against the list this requirement is about. The requirement shows what
  // the most recent check returned; every check is in the History.
  const latest = mine[0] || null
  const pages = Math.ceil(mine.length / PAGE)
  const from = page * PAGE
  const shown = mine.slice(from, from + PAGE)

  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); setMode(null); onChanged() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const record = () => act(async () => {
    const body = new FormData()
    body.append('source', f.source)
    body.append('checkedon', f.checkedon)
    body.append('namessearched', f.names)
    body.append('result', f.result)
    if (f.note) body.append('note', f.note)
    if (f.file) body.append('file', f.file)
    await api.post(`/drivers/${id}/exclusion-checks`, body)
  })

  const reinstate = () => act(async () => {
    const body = new FormData()
    body.append('liftedon', f.checkedon)
    body.append('reason', f.note)
    body.append('file', f.file)
    await api.post(`/drivers/${id}/exclusion-checks/${barred.recordid}/reinstate`, body)
  })

  const settle = () => act(async () => {
    const body = new FormData()
    body.append('result', f.verdict)
    body.append('verifymethod', open.source === 'SAM_EXCLUSIONS' ? 'samrecord' : 'ssn')
    if (f.note) body.append('note', f.note)
    body.append('file', f.file)
    await api.post(`/drivers/${id}/exclusion-checks/${open.recordid}/settle`, body)
  })

  // Recording a check is its own dialog. Laid over the list, the two were on screen at once,
  // each pretending the other was not there.
  if (mode === 'record') {
    return (
      <Modal title="Record A Check You Ran" onClose={() => setMode(null)}
        footer={<>
          <button type="button" className="primary" disabled={busy || !f.names.trim()}
            onClick={record}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
          <button type="button" onClick={() => setMode(null)}>Cancel</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="profileform">
            <label className="field span-2">List
              <select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}>
                {Object.entries(SOURCE_SITES).map(([k, [label]]) =>
                  <option key={k} value={k}>{label}</option>)}
              </select>
            </label>
            <label className="field span-2">Checked On
              <input type="date" value={f.checkedon}
                onChange={(e) => setF({ ...f, checkedon: e.target.value })} />
            </label>
            <label className="field span-2">Result
              <select value={f.result} onChange={(e) => setF({ ...f, result: e.target.value })}>
                <option value="clear">Clear</option>
                <option value="potential">Possible match</option>
                <option value="confirmed">Excluded</option>
              </select>
            </label>
            {/* OIG holds only the name known at exclusion, so former and maiden names have to be
                searched separately - and the record has to say which were tried. */}
            <label className="field span-6">Names Searched
              <input value={f.names} className="upper"
                onChange={(e) => setF({ ...f, names: e.target.value.toUpperCase() })} />
            </label>
            <label className="field span-6">Screenshot
              <input type="file" onChange={(e) => setF({ ...f, file: e.target.files[0] || null })} />
            </label>
          </div>
        </div>
      </Modal>
    )
  }

  return (
    <>
      <Modal title={r.name} onClose={onClose} brief={r?.description} width={DETAIL}
        footer={mode === 'reinstate' ? <button type="button" onClick={onClose}>Close</button> : <>
          {/* Left: the site for the list this requirement is about, and recording a check run
              there. Right: what is on file. */}
          <span className="footactions">
            {SOURCE_SITES[which] && (
              <a className="btn" href={SOURCE_SITES[which][1]} target="_blank" rel="noreferrer">
                <ExternalLink size={13} /> {SOURCE_SITES[which][0]}
              </a>
            )}
            <button type="button" onClick={() => setMode('record')}>
              <Plus size={13} /> Record a check I ran
            </button>
          </span>
          {latest && (
            <button type="button" onClick={() => setViewing({ path:
              `/drivers/${id}/exclusion-checks/${latest.recordid}/record`,
              filename: 'Search Audit Record' })}>
              <FileText size={13} /> Search Audit Record
            </button>
          )}
          <button type="button" disabled={!mine.length} onClick={() => setHistory(true)}>
            <History size={13} /> History
          </button>
          <button type="button" onClick={onClose}>Close</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}

          {barred && (
            <div className="notice bad stack">
              <div>
                <b>Excluded &ndash; this driver cannot work on Medicaid trips.</b>
                <div className="small">
                  Every trip they carry is an overpayment. An exclusion does not lapse: OIG lifts it
                  only on application, and only in writing.
                </div>
              </div>
              {mode !== 'reinstate' ? (
                <div className="row">
                  <button type="button" onClick={() => setMode('reinstate')}>
                    Record a reinstatement
                  </button>
                </div>
              ) : (
                <div className="stack">
                  <div className="profileform">
                    <label className="field span-2">Reinstated On
                      <input type="date" value={f.checkedon}
                        onChange={(e) => setF({ ...f, checkedon: e.target.value })} />
                    </label>
                    <label className="field span-4">Notice Of Reinstatement *
                      <input type="file"
                        onChange={(e) => setF({ ...f, file: e.target.files[0] || null })} />
                    </label>
                    <label className="field span-6">What Lifted It *
                      <textarea value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
                    </label>
                  </div>
                  <div className="row">
                    <button type="button" className="primary"
                      disabled={busy || !f.file || !f.note.trim()} onClick={reinstate}>
                      {busy ? <Loader2 size={15} className="spin" /> : 'Lift the exclusion'}
                    </button>
                    <button type="button" onClick={() => setMode(null)}>Cancel</button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* A possible match comes first and crowds everything else out. */}
          {open && <PossibleMatch record={open} f={f} setF={setF} busy={busy}
            settling={mode === 'settle'} onSettle={settle} onStart={() => setMode('settle')}
            onCancel={() => setMode(null)} />}

          {!latest && <div className="notice warn">This driver has never been screened.</div>}

          {latest && (
            <dl className="askfacts">
              <div><dt>Screening type</dt><dd>{SCREENING_TYPE[latest.source] || sourceName(latest.source)}</dd></div>
              <div><dt>Last screened</dt><dd>{date(latest.effectiveon)}</dd></div>
              <div><dt>Database version</dt><dd>{listVersion(latest)}</dd></div>
              <div><dt>Screening outcome</dt>
                <dd className={outcomeOf(latest)[1]}>{outcomeOf(latest)[0]}</dd></div>
              <div><dt>Next screening</dt><dd>{date(nextScreening(latest))}</dd></div>
              <div><dt>Verification status</dt><dd>{verificationOf(latest)}</dd></div>
              <div><dt>Evidence</dt>
                <dd>{latest.documentid ? 'Search audit record and screenshot' : 'Search audit record'}</dd></div>
            </dl>
          )}
        </div>
      </Modal>
      {history && (
        <Modal title={`${r.name} - History`} onClose={() => setHistory(false)} width={DETAIL}
          footer={<button type="button" onClick={() => setHistory(false)}>Close</button>}>
          <div className="stack">
            <table className="residencetable screeningtable">
              <thead><tr><th>Screened</th><th>List</th><th>Version</th><th>Outcome</th>
                <th>Verification</th><th /></tr></thead>
              <tbody>
                {shown.map((x) => (
                  <tr key={x.recordid}>
                    <td>{x.effectiveon ? date(x.effectiveon) : '-'}</td>
                    <td>{SCREENING_TYPE[x.source] || sourceName(x.source)}</td>
                    <td>{listVersion(x)}</td>
                    {/* Shorter in the history, where it repeats down the column. */}
                    <td className={outcomeOf(x)[1]}>
                      {x.determination === 'clear' ? 'No Match' : outcomeOf(x)[0]}
                    </td>
                    <td>{verificationOf(x)}</td>
                    <td className="actions">
                      <button type="button" className="linkbtn edit"
                        onClick={() => setViewing({ path:
                          `/drivers/${id}/exclusion-checks/${x.recordid}/record`,
                          filename: 'Search Audit Record' })}>
                        Record
                      </button>
                      {x.documentid && (
                        <button type="button" className="linkbtn edit"
                          onClick={() => setViewing({ documentid: x.documentid, filename: 'Screening evidence' })}>
                          Screenshot
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {/* A screening history only grows - a driver of two years has twenty-four rows from
                the monthly job alone - so it is paged rather than left to run off the bottom. */}
            {pages > 1 && (
              <div className="pager">
                <span className="muted small">
                  {from + 1}&ndash;{Math.min(from + PAGE, mine.length)} of {mine.length}
                </span>
                <div className="row">
                  <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>
                    <ChevronLeft size={14} /> Newer
                  </button>
                  <button type="button" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>
                    Older <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}
      {viewing && <DocumentViewer id={viewing.documentid} path={viewing.path} name={viewing.filename}
        onClose={() => setViewing(null)} />}
    </>
  )
}

// What a screening concluded, and in what colour.
const outcomeOf = (x) => (x.determination === 'clear' ? ['No match found', 'st-active']
  : x.determination === 'flagged'
    ? [x.liftedon ? `Excluded, lifted ${date(x.liftedon)}` : 'Excluded',
      x.liftedon ? 'st-inactive' : 'st-expired']
    : ['Possible match', 'st-ordered'])

// Whether a person has to settle it, and whether they have.
const verificationOf = (x) => (x.verifiedon
  ? `Verified ${date(x.verifiedon)}${x.verifiedbyname ? ` by ${x.verifiedbyname}` : ''}`
  : x.determination === 'review' ? 'Required' : 'Not required')

// The published list as people name it - "October 2026" - from the date OIG stamped on the file.
// A check somebody ran on the site by hand was not run against a downloaded list.
// SAM.gov publishes daily, so its version is the file's own date.
const listVersion = (x) => {
  if (!x.datasetstamp) return 'Searched on the site'
  if (x.source === 'SAM_EXCLUSIONS') return date(x.datasetstamp)
  const d = new Date(x.datasetstamp)
  return Number.isNaN(d.getTime()) ? x.datasetstamp
    : d.toLocaleString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' })
}

// OIG republishes monthly, SAM.gov daily.
const nextScreening = (x) => {
  const d = new Date(`${String(x.effectiveon).slice(0, 10)}T00:00:00`)
  if (x.source === 'SAM_EXCLUSIONS') d.setDate(d.getDate() + 1)
  else d.setMonth(d.getMonth() + 1)
  return d.toISOString().slice(0, 10)
}

const SCREENING_TYPE = { OIG_LEIE: 'OIG LEIE', SAM_EXCLUSIONS: 'SAM.gov' }

// A name came back on the list. Shown side by side, because what the person is doing is comparing
// two records - and the discriminators are the whole job.
function PossibleMatch({ record, f, setF, busy, settling, onSettle, onStart, onCancel }) {
  let listed = []
  try { listed = JSON.parse(record.candidatesjson || '[]') } catch { listed = [] }
  return (
    <div className="notice warn stack">
      <div>
        <b>A possible match &ndash; somebody has to settle this.</b>
        <div className="small">Names repeat. This is not an accusation.</div>
      </div>
      {listed.map((c, i) => (
        <div key={i} className="small">
          {[`${c.firstname} ${c.middle || ''} ${c.lastname}`.replace(/\s+/g, ' ').trim(),
            c.dob ? `DOB ${c.dob}` : null, [c.city, c.state].filter(Boolean).join(', '),
            c.general, c.excltype, c.agency, c.samnumber && `SAM number ${c.samnumber}`]
            .filter(Boolean).join(' \u00b7 ')}
        </div>
      ))}
      {/* SAM.gov carries no SSN at all, so a SAM match is settled by opening the exclusion itself
          and comparing it with what is known about the driver. */}
      <div className="small">
        {record.source === 'SAM_EXCLUSIONS'
          ? <>Settle it on SAM.gov &ndash; open the exclusion by its SAM number and compare it with
            this driver.</>
          : <>Settle it with the Social Security number on OIG&rsquo;s site &ndash; it is the only
            place that can answer definitively.</>}
      </div>
      {!settling ? (
        <div className="row">
          {record.source === 'SAM_EXCLUSIONS' ? (
            <a className="btn" href={SOURCE_SITES.SAM_EXCLUSIONS[1]} target="_blank" rel="noreferrer">
              <ExternalLink size={13} /> Open SAM.gov
            </a>
          ) : (
            <a className="btn" href={OIG_SEARCH} target="_blank" rel="noreferrer">
              <ExternalLink size={13} /> Open OIG verify
            </a>
          )}
          <button type="button" onClick={onStart}>Settle it</button>
        </div>
      ) : (
        <div className="stack">
          <div className="profileform">
            <label className="field span-3">What did OIG say?
              <select value={f.verdict} onChange={(e) => setF({ ...f, verdict: e.target.value })}>
                <option value="clear">Not this person</option>
                <option value="confirmed">This is the same person</option>
              </select>
            </label>
            <label className="field span-3">Screenshot *
              <input type="file" onChange={(e) => setF({ ...f, file: e.target.files[0] || null })} />
            </label>
            <label className="field span-6">Note
              <textarea value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
            </label>
          </div>
          <div className="row">
            <button type="button" className="primary" disabled={busy || !f.file} onClick={onSettle}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={onCancel}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}
