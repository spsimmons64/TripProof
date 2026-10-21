// Driver page - Testing. Moved out of
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
import { usePlaygroundHeight } from './common.jsx'

// The return-to-duty process, start to finish, in the one place the violation is.
//
// 49 CFR 382.501 and Part 40 Subpart O. Three things were wrong with the panel this replaces,
// and they were all the same thing - it could show the process but not run it:
//
//   The SAP information button told you to go and record it somewhere else. There was no way
//   at all to record the SAP evaluation from here. And a return-to-duty test could be filed at
//   any moment, including before the SAP had signed the driver off, where 40.305 lifts nothing
//   - so the office filed the test, watched the bar stay up, and had no idea why.
//
// So this owns the process. Every step is listed in the order it happens, each says what is on
// file, and the step that can be done now carries the button that does it. A step that is not
// yet reachable says what has to happen first instead of offering a button that does nothing.
// Nothing here sends anybody to another screen.
export function ProhibitionPanel({ id, held, testing, dot, onView, onChanged }) {
  const [doing, setDoing] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [said, setSaid] = useState(null)
  const today = new Date().toISOString().slice(0, 10)
  const [sapinfo, setSapinfo] = useState({ givenon: today, file: null })
  const [rtd, setRtd] = useState({ sapname: '', sapevaluatedon: '', sapcompliedon: '',
                                   followuptests: '', followupuntil: '', note: '', file: null })
  // The one case where the panel outlives the thing it is about: a negative return-to-duty test
  // clears the prohibition, so `held` goes away in the same breath as the news that it did.
  if (!held) return said ? <div className="notice good">{said}</div> : null

  const who = dot ? 'Substance abuse professional (SAP)' : 'Evaluator'
  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); setDoing(null); await onChanged?.() } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }
  const post = (path, fields, upload) => {
    const body = new FormData()
    Object.entries(fields).forEach(([k, v]) => { if (v !== '' && v != null) body.append(k, v) })
    if (upload) body.append('file', upload)
    return api.post(`/drivers/${id}/testing/${path}`, body)
  }

  const decide = (decision) => act(() => post('decision', { decision }))
  const saveSapInfo = () => act(() => post('decision', { sapinfogivenon: sapinfo.givenon },
                                           sapinfo.file))
  const saveRtd = () => act(async () => {
    const body = new FormData()
    Object.entries(rtd).forEach(([k, v]) => {
      if (v !== '' && v != null && k !== 'file') body.append(k, v)
    })
    if (rtd.file) body.append('file', rtd.file)
    await api.put(`/drivers/${id}/testing/prohibition`, body)
  })
  const saveTest = (f) => act(async () => {
    const body = new FormData()
    body.append('reason', 'returntoduty')
    body.append('collectedon', f.collectedon)
    body.append('result', f.result)
    if (f.testtype) body.append('testtype', f.testtype)
    if (f.substance?.trim()) body.append('substance', f.substance.trim())
    if (f.bac !== '' && f.bac != null) body.append('bac', f.bac)
    if (f.note.trim()) body.append('note', f.note.trim().toUpperCase())
    if (f.file) body.append('file', f.file)
    const out = await api.post(`/drivers/${id}/testing/tests`, body)
    // Say which of the two happened. A negative lifts the bar; anything else is a fresh
    // violation on a driver who was already barred, and both deserve a sentence rather than
    // a silently redrawn panel.
    setSaid(out?.cleared
      ? 'The return-to-duty test is negative and the SAP has signed this driver off. The bar is '
        + 'lifted and they may perform safety-sensitive functions again.'
      : 'Recorded. The bar still stands - the return-to-duty test must come back negative '
        + '(49 CFR 40.305).')
  })

  // The steps, in the order they happen. `can` is what may be done now; `blocked` is the reason
  // it may not be, which is the sentence somebody needs when the button they expected is absent.
  const prescribed = Boolean(held.sapcompliedon)
  const continuing = held.decision === 'continue'
  const steps = [
    // 40.287 is owed to the driver whether or not they are kept on, which is exactly the duty
    // that gets dropped when somebody decides not to hire and closes the file.
    { key: 'sapinfo', done: Boolean(held.sapinfogivenon),
      name: dot ? 'SAP information given to the driver'
                : 'List of evaluators given to the driver',
      cite: dot ? '49 CFR 40.287 · Owed whether or not they are kept on' : 'Owed either way',
      answer: held.sapinfogivenon
        ? <>{date(held.sapinfogivenon)}{held.sapinfodocumentid && <>{' '}
            <button type="button" className="linkbtn edit"
              onClick={() => onView({ documentid: held.sapinfodocumentid,
                filename: 'SAP information' })}>View</button></>}</>
        : null,
      can: 'Record', do: () => { setSapinfo({ givenon: today, file: null }); setDoing('sapinfo') } },
    // DOT says what this person may DO. Whether they are employed is the company's own call and
    // nothing here decides it either way.
    { key: 'decision', done: Boolean(held.decision),
      name: 'Employment decision',
      cite: 'The company\'s own, not DOT\'s - the bar stands either way',
      answer: held.decision
        ? `${testing?.decisions?.[held.decision] || held.decision}`
          + `${held.decidedon ? ` ${date(held.decidedon)}` : ''}`
        : null,
      buttons: (
        <>
          <button type="button" disabled={busy} onClick={() => decide('donothire')}>
            Do Not Hire
          </button>
          <button type="button" disabled={busy} onClick={() => decide('continue')}>
            Keep On
          </button>
        </>
      ) },
    { key: 'evaluation', done: prescribed,
      name: dot ? 'SAP evaluation and what the SAP prescribed' : 'Evaluation',
      cite: dot ? '49 CFR 40.305' : 'What the company\'s own policy requires',
      answer: (held.sapname || held.sapevaluatedon || held.sapcompliedon) ? (
        <>
          {[held.sapname, held.sapevaluatedon && `evaluated ${date(held.sapevaluatedon)}`,
            held.sapcompliedon && `complied ${date(held.sapcompliedon)}`]
            .filter(Boolean).join(' · ')}
          {held.documentid && <>{' '}
            <button type="button" className="linkbtn edit"
              onClick={() => onView({ documentid: held.documentid,
                filename: dot ? 'SAP determination' : 'Evaluation' })}>View</button></>}
        </>
      ) : null,
      blocked: continuing ? null
        : 'Make the employment decision first. There is no evaluation to record for a driver the '
          + 'company is not keeping on.',
      can: prescribed ? 'Update' : 'Record',
      do: () => {
        setRtd({ sapname: held.sapname || '', sapevaluatedon: held.sapevaluatedon || '',
                 sapcompliedon: held.sapcompliedon || '',
                 followuptests: held.followuptests || '', followupuntil: held.followupuntil || '',
                 note: '', file: null })
        setDoing('rtd')
      } },
    // The last step, and the only one that lifts anything.
    { key: 'rtdtest', done: Boolean(held.rtdtestid),
      name: 'Negative return-to-duty test',
      cite: dot ? '49 CFR 40.305 · This is what lifts the bar'
                : 'This is what lifts the bar',
      answer: held.rtdtestid ? 'On file' : null,
      blocked: !continuing
        ? 'Make the employment decision first.'
        : (dot && !prescribed)
          ? 'Available once the SAP has recorded that this driver completed what was prescribed. '
            + 'A test collected before that lifts nothing (49 CFR 40.305).'
          : null,
      can: 'Record', do: () => setDoing('test') },
  ]
  if (held.followuptests) {
    steps.push({ key: 'followup', done: true,
      name: 'Follow-up testing plan',
      cite: dot ? '49 CFR 40.307 and 382.311 · An obligation after the bar lifts, not a bar'
                : 'An obligation after the bar lifts, not a bar',
      answer: `${held.followuptests} test${held.followuptests === 1 ? '' : 's'}`
        + (held.followupuntil ? ` through ${date(held.followupuntil)}` : '') })
  }

  return (
    <>
      <div className="notice bad stack">
        <div><b>{held.reason}</b></div>
        <div className="small">
          Removed from safety-sensitive functions
          {held.startedon ? ` since ${date(held.startedon)}` : ''}
          {testing?.programs?.[held.program] ? ` · ${testing.programs[held.program]}` : ''}
        </div>
        <div className="small">{testing?.returntoduty}</div>
      </div>
      {err && <div className="notice bad">{err}</div>}
      {said && <div className="notice">{said}</div>}
      <div className="rtdsteps">
        {steps.map((st) => (
          <div key={st.key} className="factrow reqrow">
            <div className="reqmark">
              <Bubble state={st.mark || (st.done ? 'satisfied' : 'todo')} />
            </div>
            <div className="factwhat reqname">
              {st.name}
              <span className="factcite">{st.cite}</span>
              {st.answer && <span className="factanswer rtdanswer">{st.answer}</span>}
              {!st.done && st.blocked && <span className="factcite">{st.blocked}</span>}
              {st.note && <span className="factnote">{st.note}</span>}
            </div>
            <div className="reqdo">
              {!st.done && !st.blocked && (st.buttons || (st.do && (
                <button type="button" disabled={busy} onClick={st.do}>{st.can}</button>
              )))}
              {st.done && st.can === 'Update' && (
                <button type="button" disabled={busy} onClick={st.do}>Update</button>
              )}
            </div>
          </div>
        ))}
      </div>

      {doing === 'sapinfo' && (
        <Modal title="SAP Information Given" onClose={() => setDoing(null)} width={620}
          footer={<>
            <button type="button" className="primary" disabled={busy} onClick={saveSapInfo}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={() => setDoing(null)}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="profileform">
              <label className="field span-4">Given On
                <input type="date" value={sapinfo.givenon}
                  onChange={(e) => setSapinfo({ ...sapinfo, givenon: e.target.value })} />
              </label>
              {/* The list itself, not only the day it was handed over. A date with nothing behind
                  it is the employer's word for it, which is what an auditor asks to see. */}
              <label className="field span-8">The List Given
                <input type="file"
                  onChange={(e) => setSapinfo({ ...sapinfo, file: e.target.files[0] || null })} />
              </label>
            </div>
          </div>
        </Modal>
      )}

      {doing === 'rtd' && (
        <Modal title={dot ? 'SAP Evaluation' : 'Evaluation'} onClose={() => setDoing(null)}
          width={680}
          footer={<>
            <button type="button" className="primary" disabled={busy} onClick={saveRtd}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={() => setDoing(null)}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <section>
              <h3 className="formsection">{dot ? 'SAP' : 'Evaluation'}</h3>
              <div className="profileform">
                <label className="field span-4">{who}
                  <input value={rtd.sapname} className="upper"
                    onChange={(e) => setRtd({ ...rtd, sapname: e.target.value.toUpperCase() })} />
                </label>
                <label className="field span-2">Evaluated On
                  <input type="date" value={rtd.sapevaluatedon}
                    onChange={(e) => setRtd({ ...rtd, sapevaluatedon: e.target.value })} />
                </label>
                <label className="field span-3">Completed What Was Prescribed
                  <input type="date" value={rtd.sapcompliedon}
                    onChange={(e) => setRtd({ ...rtd, sapcompliedon: e.target.value })} />
                </label>
              </div>
            </section>
            <section>
              <h3 className="formsection">Follow Up Testing</h3>
              <div className="profileform">
                <label className="field span-2">How Many Tests
                  <input type="number" min="0" value={rtd.followuptests}
                    onChange={(e) => setRtd({ ...rtd, followuptests: e.target.value })} />
                </label>
                <label className="field span-3">Through
                  <input type="date" value={rtd.followupuntil}
                    onChange={(e) => setRtd({ ...rtd, followupuntil: e.target.value })} />
                </label>
                <label className="field span-6">Note
                  <textarea value={rtd.note}
                    onChange={(e) => setRtd({ ...rtd, note: e.target.value })} />
                </label>
                {/* The written determination behind the dates. A date with nothing behind it is
                    somebody's word for it, which is what an auditor asks to see. */}
                <label className="field span-6">
                  {dot ? 'SAP determination' : 'Evaluation documentation'}
                  <input type="file"
                    onChange={(e) => setRtd({ ...rtd, file: e.target.files[0] || null })} />
                </label>
              </div>
            </section>
          </div>
        </Modal>
      )}

      {doing === 'test' && (
        <TestDialog title="Return To Duty Test" reason="returntoduty" locked
          reasons={testing?.reasons} results={testing?.results} busy={busy} err={err}
          onSave={saveTest} onClose={() => setDoing(null)} />
      )}
    </>
  )
}

// Every drug and alcohol test on this driver, as one list. Whether they may drive is NOT said
// here: the red banner above every section of the file already says it, and a second copy on
// this page only repeated it - in raw codes, which is worse than not saying it at all.
export function TestingHistory({ id, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/drivers/${id}/testing`), [id])
  const [page, setPage] = useState(1)
  const [pagesize, setPagesize] = useState(PAGE_SIZES[0])
  const [adding, setAdding] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [opened, setOpened] = useState(null)
  const [pulling, setPulling] = useState(null)   // the test being taken back
  const [undone, setUndone] = useState(null)     // what the withdrawal reversed
  const card = useRef(null)
  const room = usePlaygroundHeight(card, [id, data])

  // A return-to-duty test is no longer among the reasons offered here until the process has
  // reached the point where one would mean something - the server decides that - so the "you
  // have just filed a test that lifted nothing" warning this used to print has nowhere left to
  // fire from. Recording one is a step inside the prohibition, not a loose entry in a list.
  const save = (f) => {
    setBusy(true); setErr(null)
    const body = new FormData()
    body.append('reason', f.reason)
    body.append('collectedon', f.collectedon)
    body.append('result', f.result)
    if (f.testtype) body.append('testtype', f.testtype)
    if (f.substance?.trim()) body.append('substance', f.substance.trim())
    if (f.bac !== '' && f.bac != null) body.append('bac', f.bac)
    if (f.note.trim()) body.append('note', f.note.trim().toUpperCase())
    if (f.file) body.append('file', f.file)
    api.post(`/drivers/${id}/testing/tests`, body)
      .then(() => { setAdding(false); reload(); onChanged?.() })
      .catch((e) => setErr(e.message))
      .finally(() => setBusy(false))
  }

  if (!data) {
    return <div className="card qualcard"><h3>D&A Testing History</h3><Loading error={error} /></div>
  }
  const tests = data.tests || []
  const pages = Math.max(1, Math.ceil(tests.length / pagesize))
  const at = Math.min(page, pages)
  const shown = tests.slice((at - 1) * pagesize, at * pagesize)
  const bad = (r) => ['positive', 'refusal', 'adulterated', 'substituted'].includes(r)

  return (
    <>
      <div className="card qualcard activitycard" ref={card}
        style={room ? { height: room } : undefined}>
        <h3 className="withact">
          <span>D&A Testing History</span>
          {(data.offer || []).length > 0 && (
            <button type="button"
              onClick={() => setAdding(true)}>
              <Plus size={13} /> Record A Test
            </button>
          )}
        </h3>
        {err && <div className="notice bad">{err}</div>}
        <div className="hireband">
          {!tests.length ? <div className="hireempty">No tests recorded</div> : (
            <table className="residencetable recordtable">
              <thead><tr><th>Collected</th><th>Reason</th><th>Result</th>
                <th className="growcol">Note</th><th /></tr></thead>
              <tbody>
                {shown.map((t) => (
                  <tr key={t.recordid}>
                    <td>{t.collectedon ? date(t.collectedon) : '-'}</td>
                    <td>{data.reasons?.[t.reason] || t.reason}</td>
                    <td className={bad(t.result) ? 'st-expired' : 'st-active'}>
                      {data.results?.[t.result] || t.result}
                    </td>
                    <td className="growcol">{t.note || '-'}</td>
                    <td className="actions">
                      {/* A positive is not a document - it is a bar, and what somebody needs
                          to see is how far through getting out from under it this driver is.
                          The lab report is one line of that, reachable from inside it. */}
                      {bad(t.result) ? (
                        <button type="button" className="linkbtn edit toread"
                          onClick={() => setOpened(t)}>View</button>
                      ) : t.documentid && (
                        <button type="button" className="linkbtn edit"
                          onClick={() => setViewing({ documentid: t.documentid,
                            filename: t.filename || 'Test result' })}>View</button>
                      )}
                      {/* A test typed against the wrong name is the one mistake on this screen
                          that cannot be left: it bars a driver who did nothing, or clears one
                          who is barred. */}
                      <button type="button" className="linkbtn edit"
                        onClick={() => setPulling(t)}>Withdraw</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <Pager total={tests.length} page={at} pagesize={pagesize} noun="tests"
          onPage={setPage} onPageSize={(n) => { setPagesize(n); setPage(1) }} />
      </div>

      {adding && (
        <TestDialog title="Record A Test" reasons={data.reasons} results={data.results}
          offer={data.offer} busy={busy} err={err}
          onSave={save} onClose={() => setAdding(false)} />
      )}
      {opened && (
        <Modal title={`${data.reasons?.[opened.reason] || opened.reason} - `
          + `${data.results?.[opened.result] || opened.result}`}
          onClose={() => setOpened(null)} width={900}
          footer={<>
            {opened.documentid && (
              <button type="button"
                onClick={() => setViewing({ documentid: opened.documentid,
                  filename: opened.filename || 'Laboratory report' })}>
                <Eye size={13} /> Laboratory Report
              </button>
            )}
            <button type="button" onClick={() => setOpened(null)}>Close</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <dl className="askfacts">
              <div><dt>Collected</dt>
                <dd>{opened.collectedon ? date(opened.collectedon) : '-'}</dd></div>
              {opened.note && <div><dt>Note</dt><dd>{opened.note}</dd></div>}
            </dl>
            {/* What this test led to. Two different things depending on whether the bar it
                caused is still up: a bar in force is a process somebody is in the middle of,
                so the panel that RUNS it belongs here. A bar that was lifted is a record, and
                what the reader wants from it is the paperwork and the dates - which until now
                it showed none of, so a positive from last March opened on screen saying
                "Collected" and nothing else. */}
            {data.prohibited?.testid === opened.recordid ? (
              <ProhibitionPanel id={id} held={data.prohibited} testing={data}
                dot={data.program === 'dot'} onView={setViewing}
                onChanged={async () => { await reload(); onChanged?.() }} />
            ) : (() => {
              const past = (data.history || []).find((h) => h.testid === opened.recordid)
              if (!past) return null
              const dot = (past.program || data.program) === 'dot'
              return (
                <>
                  <div className="notice">
                    <b>{past.reason}</b>
                    {past.clearedon
                      ? ` The bar was lifted on ${date(past.clearedon)}.`
                      : ' The bar from this test is no longer the one in force.'}
                  </div>
                  <dl className="askfacts">
                    <div><dt>Removed from safety-sensitive functions</dt>
                      <dd>{date(past.startedon)}</dd></div>
                    <div><dt>Employment decision</dt>
                      <dd>{past.decision
                        ? `${data.decisions?.[past.decision] || past.decision}`
                          + `${past.decidedon ? ` ${date(past.decidedon)}` : ''}`
                        : 'Not recorded'}</dd></div>
                    <div><dt>{dot ? 'Substance abuse professional (SAP)' : 'Evaluator'}</dt>
                      <dd>{[past.sapname,
                            past.sapevaluatedon && `evaluated ${date(past.sapevaluatedon)}`,
                            past.sapcompliedon && `complied ${date(past.sapcompliedon)}`]
                        .filter(Boolean).join(' · ') || 'Not recorded'}</dd></div>
                    <div><dt>{dot ? 'SAP determination' : 'Evaluation'}</dt>
                      <dd>{past.documentid
                        ? <button type="button" className="linkbtn edit"
                            onClick={() => setViewing({ documentid: past.documentid,
                              filename: dot ? 'SAP determination' : 'Evaluation' })}>View</button>
                        : 'Not on file'}</dd></div>
                    <div><dt>SAP information given to the driver</dt>
                      <dd>{past.sapinfogivenon
                        ? <>{date(past.sapinfogivenon)}{past.sapinfodocumentid && <>{' '}
                            <button type="button" className="linkbtn edit"
                              onClick={() => setViewing({ documentid: past.sapinfodocumentid,
                                filename: 'SAP information' })}>View</button></>}</>
                        : 'Not recorded'}</dd></div>
                    {past.followuptests > 0 && (
                      <div><dt>Follow-up testing plan</dt>
                        <dd>{past.followuptests} test{past.followuptests === 1 ? '' : 's'}
                          {past.followupuntil ? ` through ${date(past.followupuntil)}` : ''}</dd></div>
                    )}
                  </dl>
                </>
              )
            })()}
          </div>
        </Modal>
      )}
      {pulling && (
        <WithdrawDialog title="Withdraw This Test" busy={busy} err={err}
          what={`The ${(data.reasons?.[pulling.reason] || pulling.reason).toLowerCase()} test of `
            + `${date(pulling.collectedon)} - `
            + `${data.results?.[pulling.result] || pulling.result} - will be withdrawn.`}
          warn="Whatever it did will be undone: a bar it raised comes off, a bar it lifted goes
                back on."
          onClose={() => setPulling(null)}
          onConfirm={(reason) => {
            setBusy(true); setErr(null)
            api.post(`/drivers/${id}/testing/tests/${pulling.recordid}/withdraw`, { reason })
              .then((out) => { setPulling(null); setUndone(out); reload(); onChanged?.() })
              .catch((e) => setErr(e.message)).finally(() => setBusy(false))
          }} />
      )}
      {undone && (
        <WithdrawnDialog undone={undone.undone} note={undone.poolnote}
          onClose={() => setUndone(null)} />
      )}
      {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
        onClose={() => setViewing(null)} />}
    </>
  )
}
