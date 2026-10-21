// Driver page - Files. Moved out of
// pages/DriverReview.jsx, which had grown too large to work in safely.
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Ban, Car, Check, ChevronLeft, Download, FlaskConical, LayoutDashboard, ChevronRight, Clock, ExternalLink, Eye, FileSignature, FileText, FileUp, FolderOpen, History, IdCard, ListChecks, Loader2, MoreHorizontal, Plus, X, Send, UserCheck, UserX } from 'lucide-react'
import { STATE_NAMES } from '../../lib/states.js'
import { api } from '../../lib/api.js'
import { useRefreshOnFocus, useWatch } from '../../lib/live.js'
import { date } from '../../lib/format.js'
import { Bubble, Loading, useLoad } from '../../components/ui.jsx'
import { Modal } from '../../admin/common.jsx'
import Pager, { PAGE_SIZES } from '../../components/Pager.jsx'
import { useUser } from '../../App.jsx'
import SignatureBlock from '../../components/UserSignature.jsx'
import { ItemPanel, PanelsDialog, ReadingViewer, SingleDocumentDialog, docStanding } from '../../components/RequirementDialogs.jsx'
import DocumentViewer, { DocumentPane } from '../../components/DocumentViewer.jsx'
import ApplicantForm from '../../components/ApplicantForm.jsx'
import SignedDocViewer from '../../components/SignedDocViewer.jsx'
import { PhoneInput } from '../../components/MaskedInput.jsx'
import LicenseDialog from '../../components/LicenseDialog.jsx'
import TestDialog from '../../components/TestDialog.jsx'
import WithdrawDialog, { WithdrawnDialog } from '../../components/WithdrawDialog.jsx'
import { Email, Phone } from '../../components/Contact.jsx'
import { saveLicense, usePlaygroundHeight } from './common.jsx'

// Everything on file for this driver, in sections. A signed document is rebuilt from the record
// rather than stored, so it opens its own way.
const FROM = {
  driver: 'from the driver',
  service: 'back from a service',
  thirdparty: 'from outside',
}

export function DriverFiles({ id, onView, onViewSigned, onChanged, onGo }) {
  const [data, error, reload] = useLoad(() => api.get(`/drivers/${id}/files`), [id])
  const [kinds] = useLoad(() => api.get(`/drivers/${id}/files/kinds`), [id])
  const [zipping, setZipping] = useState(false)
  const [adding, setAdding] = useState(false)
  const [pulling, setPulling] = useState(null)
  const [undone, setUndone] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [page, setPage] = useState(1)
  const [pagesize, setPagesize] = useState(PAGE_SIZES[0])
  const card = useRef(null)
  const room = usePlaygroundHeight(card, [id, data])
  if (!data) return <div className="card qualcard"><h3>Driver Files</h3><Loading error={error} /></div>

  // Flattened to page it, with the section carried on each row so the heading can be put back
  // wherever the group changes on the page somebody is looking at. A file is a file; the grouping
  // is how they are read, not what they are.
  const all = data.sections.flatMap((sec) => sec.files.map((f) => ({ ...f, section: sec.name })))
  const total = all.length
  const pages = Math.max(1, Math.ceil(total / pagesize))
  const at = Math.min(page, pages)
  const shown = all.slice((at - 1) * pagesize, at * pagesize)

  return (
    <div className="card qualcard activitycard" ref={card}
      style={room ? { height: room } : undefined}>
      {/* The whole file, zipped - what somebody hands an auditor. Right-justified in the
          heading band, the same place Hours Of Service puts its action. */}
      <h3 className="withact">
        <span>Driver Files</span>
        <span className="row">
          <button type="button" onClick={() => setAdding(true)}>
            <Plus size={13} /> Add A File
          </button>
          <button type="button" disabled={zipping} onClick={async () => {
            setZipping(true)
            try { await api.download(`/drivers/${id}/files.zip`) } finally { setZipping(false) }
          }}>
            {zipping ? <Loader2 size={13} className="spin" /> : <Download size={13} />}
            {zipping ? ' Preparing…' : ' Download Driver File'}
          </button>
        </span>
      </h3>
      {err && <div className="notice bad">{err}</div>}
      {!total && <p className="muted" style={{ padding: '14px 20px' }}>Nothing on file yet.</p>}
      <div className="filescroll">
        {shown.map((f, i) => (
          <div key={f.recordid || f.doctype}>
            {(i === 0 || shown[i - 1].section !== f.section) && (
              <div className="qualgrouphead">
                <span className="qualsource">{f.section}</span>
                <span className="qualgroupcount">
                  {all.filter((x) => x.section === f.section).length}
                </span>
              </div>
            )}
            <div className="qualitem">
              {/* A file is a file. The bubbles say how a requirement stands, and nothing on this
                  list is a requirement - marking every document with a status it does not have was
                  saying something about it that is not true. */}
              <div className="qualmark filemark">
                {f.kind === 'signed' ? <FileSignature size={18} /> : <FileText size={18} />}
              </div>
              <div className="qualbody">
                <div className="qualname">{f.what}</div>
                <div className="qualmeta">
                  {[f.filename, f.bytes ? `${Math.round(f.bytes / 1024).toLocaleString()} KB` : null,
                    `${f.kind === 'signed' ? 'Signed' : 'Added'} ${date(f.added)}`,
                    FROM[f.origin]]
                    .filter(Boolean).join(' · ')}
                </div>
              </div>
              <div className="qualstate" />
              <div className="qualdo">
                <button type="button" onClick={() => (f.kind === 'signed'
                  ? onViewSigned(f.doctype)
                  : onView({ documentid: f.recordid, filename: f.filename }))}>
                  {f.kind === 'signed' ? <FileSignature size={13} /> : <Eye size={13} />} View
                </button>
                {/* Only what the office put there. The driver's own submission, what a service
                    returned and what a previous employer sent are somebody else's record of
                    what they did - a carrier that can quietly remove those can quietly remove
                    the inconvenient ones. The endpoint refuses them as well, so this is the
                    courtesy rather than the control. */}
                {f.kind === 'file' && f.origin === 'office' && (
                  <button type="button" onClick={() => setPulling(f)}>Withdraw</button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
      <Pager total={total} page={at} pagesize={pagesize}
        onPage={setPage} onPageSize={(n) => { setPagesize(n); setPage(1) }} noun="files" />

      {adding && (
        <AddFileDialog id={id} kinds={kinds?.kinds || []}
          onClose={() => setAdding(false)} onGo={onGo}
          onSaved={async () => { setAdding(false); await reload(); onChanged?.() }} />
      )}
      {pulling && (
        <WithdrawDialog title="Withdraw This File" busy={busy} err={err}
          what={`${pulling.what}${pulling.filename ? ` (${pulling.filename})` : ''} `
            + 'will be withdrawn from this driver\'s folder.'}
          warn="Whatever it was filed as goes with it, so any requirement it answered is
                outstanding again."
          onClose={() => setPulling(null)}
          onConfirm={(reason) => {
            setBusy(true); setErr(null)
            api.post(`/drivers/${id}/files/${pulling.recordid}/withdraw`, { reason })
              .then((out) => { setPulling(null); setUndone(out); reload(); onChanged?.() })
              .catch((e) => setErr(e.message)).finally(() => setBusy(false))
          }} />
      )}
      {undone && <WithdrawnDialog undone={undone.undone} onClose={() => setUndone(null)} />}
    </div>
  )
}

// Putting a file into a driver's folder, and saying what it is.
//
// A file on its own is not evidence of anything. A medical certificate answers 49 CFR 391.43 and
// runs out; a training record answers its own rule on its own clock; a scan of a letter answers
// nothing. So this asks which before it asks for the file, and the fields follow from the answer
// rather than from one form that asks everybody for everything.
function AddFileDialog({ id, kinds, onClose, onSaved, onGo }) {
  const today = new Date().toISOString().slice(0, 10)
  const [pick, setPick] = useState('')
  const [f, setF] = useState({ issuedon: today, expireson: '', file: null })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const chosen = kinds.find((k) => k.code === pick)
  const groups = [...new Set(kinds.map((k) => k.group))]

  const [license, setLicense] = useState(false)

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('credentialtypeid', chosen.typeid)
      body.append('subjectid', id)
      body.append('issuedon', f.issuedon)
      if (f.expireson) body.append('expireson', f.expireson)
      if (f.file) body.append('file', f.file)
      await api.post('/credentials', body)
      await onSaved()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  // The license has a screen of its own with both sides on it, so it opens here rather than
  // being rebuilt as three fields that would then disagree with it.
  if (license) {
    return (
      <LicenseDialog copies onClose={() => setLicense(false)}
        onAdd={async (held, copies) => {
          setBusy(true); setErr(null)
          try {
            await saveLicense(id, held, copies)
            setLicense(false)
            await onSaved()
          } catch (e) { setErr(e.message); setLicense(false) } finally { setBusy(false) }
        }} />
    )
  }

  return (
    <Modal title="Add A File" onClose={onClose} width={680}
      footer={<>
        {chosen?.kind === 'license' && (
          <button type="button" className="primary" onClick={() => setLicense(true)}>
            Add The License
          </button>
        )}
        {chosen?.goto && (
          <button type="button" className="primary"
            onClick={() => { onClose(); onGo?.(chosen.goto, chosen.code) }}>
            Open {chosen.name}
          </button>
        )}
        {chosen?.kind === 'credential' && (
          <button type="button" className="primary" disabled={busy || !f.file} onClick={save}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
        )}
        <button type="button" onClick={onClose}>Cancel</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="profileform">
          <label className="field span-6">What is it? *
            <select value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">Choose</option>
              {groups.map((g) => (
                <optgroup key={g} label={g}>
                  {kinds.filter((k) => k.group === g).map((k) => (
                    <option key={k.code} value={k.code}>{k.name}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          {chosen?.kind === 'credential' && (
            <>
              <label className="field span-3">Issued *
                <input type="date" value={f.issuedon} min="1900-01-01" max="2100-12-31"
                  onChange={(e) => setF({ ...f, issuedon: e.target.value })} />
              </label>
              {/* Asked, not required. The type knows how long its own kind of document lasts,
                  so a blank is an instruction rather than a gap - and the hint says which. */}
              <label className="field span-3">Expires
                <input type="date" value={f.expireson} min="1900-01-01" max="2100-12-31"
                  onChange={(e) => setF({ ...f, expireson: e.target.value })} />
              </label>
              <label className="field span-6">The File *
                <input type="file"
                  onChange={(e) => setF({ ...f, file: e.target.files[0] || null })} />
              </label>
            </>
          )}
        </div>
        {chosen && <div className="small muted">{chosen.hint}</div>}
      </div>
    </Modal>
  )
}
