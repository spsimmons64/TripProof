import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Eye, FileUp, Loader2, Pencil, Plus } from 'lucide-react'
import PolicyEditor from '../components/PolicyEditor.jsx'
import { api } from '../lib/api.js'
import { Bubble, Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import DocumentViewer from '../components/DocumentViewer.jsx'
import SignatureBlock from '../components/UserSignature.jsx'
import { date } from '../lib/format.js'

// What is asked of the COMPANY, read from the same engine the driver screen reads. An operator
// looking at a wall of green drivers can still be the thing that fails an audit - no designated
// employer representative, a policy nobody can produce, a registration that lapsed - and until
// this screen existed there was nowhere any of that could be seen.
const MARKS = {
  satisfied: ['received', 'Current'],
  expiring: ['received', 'Expiring'],
  expired: ['blocked', 'Expired'],
  failed: ['blocked', 'Failed'],
  overdue: ['blocked', 'Overdue'],
  notapplicable: ['waived', 'Not required'],
  unknown: ['todo', 'Cannot be decided'],
  pending: ['todo', 'Nothing on file'],
}

export default function CompanyRequirements() {
  const [data, error, reload] = useLoad(() => api.get('/company/requirements'), [])
  const [open, setOpen] = useState(null)
  const [viewing, setViewing] = useState(null)

  if (!data) return <div className="card"><Loading error={error} /></div>

  const live = data.items.filter((i) => i.applies === true)
  // What nobody has answered yet still shows, because it is work: somebody has to say whether the
  // rule reaches this company. What has been answered NO does not - a list of obligations this
  // company does not have is not a list anybody reads.
  const undecided = data.items.filter((i) => i.applies === null)

  const row = (i) => {
    return (
      <div key={i.code} className="factrow reqrow">
        <div className="reqmark"><Bubble state={i.status} /></div>
        <div className="factwhat reqname">
          {i.name}
          <span className="factcite">
            {[i.authority, i.citation, i.duetext].filter(Boolean).join(' · ')}
          </span>
          <span className="factasking">
            {i.why}{i.expireson ? ` Next due ${date(i.expireson)}.` : ''}
          </span>
        </div>
        <div className="reqdo">
          <button type="button" onClick={() => setOpen(i)}>
            <FileUp size={13} /> Details
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="stack">
      <div className="pagehead"><h1>Company Requirements</h1></div>

      {data.stops.length > 0 && (
        <div className="card notcleared" role="alert">
          <div className="notclearedsays">
            <h2>Outstanding Company Obligations</h2>
            <p>These are the company&rsquo;s own, not any driver&rsquo;s. A file full of qualified
              drivers does not answer them.</p>
          </div>
        </div>
      )}

      <div className="card factpanel">
        <h3 className="reqhead">What Is Asked Of This Company</h3>
        {live.map(row)}
        {!live.length && <div className="hirenone muted">Nothing applies yet.</div>}
      </div>

      {undecided.length > 0 && (
        <div className="card factpanel">
          {/* Not "waiting on an answer from the company", which named only one of the two
              reasons and sent people to Company Operations looking for a question that is not
              there. Some of these wait on a question nobody has answered; others wait on a
              requirement on THIS page that nobody has done yet - the exposure control plan
              cannot be decided until the exposure determination above it is made. The line
              under each one says which, and where. */}
          <h3 className="reqhead">Not Settled Yet</h3>
          <p className="reqaside">
            Each of these waits on something nobody has settled. The line under it says what.
          </p>
          {undecided.map(row)}
        </div>
      )}

      {open && (
        <CompanyDetail item={open} types={data.types} onClose={() => setOpen(null)}
          onView={setViewing} onDone={() => { setOpen(null); reload() }}
          /* Appointing somebody is not finishing with the dialog - there may be a second person
             to add, or the wrong one to take off again. The list behind refreshes; this stays. */
          onChanged={reload} />
      )}
      {viewing && <DocumentViewer id={viewing.documentid} name={viewing.name}
        onClose={() => setViewing(null)} />}
    </div>
  )
}

// Which requirements are answered by a policy TripProof publishes rather than by a document the
// company uploads.
const POLICIES = {
  DRUG_ALCOHOL_POLICY: 'DRUG_POLICY',
  WORKPLACE_POLICY: 'WORKPLACE_POLICY',
  PHI_POLICY: 'PHI_POLICY',
  SSPP: 'SSPP',
  TPA_AGREEMENT: 'SERVICE_AGENT_POLICY',
  // BBP_EXPOSURE_DETERMINATION is NOT here. It is answered by a determination somebody
  // makes and certifies, not by adopting a policy - and because this map is consulted
  // first, leaving it here sent the requirement to the policy editor, where Save adopted
  // a policy that the requirement no longer reads. Its wording is reached from inside
  // the determination dialog instead.
}

// A requirement answered by a document the company produces, which TripProof also publishes a
// written policy for - the procedure that sits beside the record. Reached from the same dialog
// as the record, because a policy nothing points at is a policy nobody finds.
const COMPANION_POLICY = {
  HIPAA_RISK_ANALYSIS: 'HIPAA_RISK_ANALYSIS_POLICY',
}

// The blanks the server fills, offered from a menu so nobody has to remember the spelling - and so
// that a half-deleted brace cannot leave a policy naming nobody.
const MERGE_FIELDS = [
  ['{company}', 'Company name'],
  ['{address}', 'Company address'],
  ['{telephone}', 'Company telephone'],
  ['{effectivedate}', 'Effective date'],
  ['{dername}', 'DER name'],
  ['{dertitle}', 'DER title'],
  ['{derphone}', 'DER telephone'],
  ['{deremail}', 'DER email'],
  ['{derline}', 'DER name and email'],
  ['{safetyname}', 'Safety Manager name'],
  ['{safetytitle}', 'Safety Manager title'],
  ['{safetyphone}', 'Safety Manager telephone'],
  ['{safetyemail}', 'Safety Manager email'],
  ['{safetyline}', 'Safety Manager name and email'],
  ['{discipline}', 'Discipline after a DOT violation'],
]

// The supervisor training record's own blanks, on top of the ones above. These are the lines
// each supervisor fills in on their own copy, so they are rules on the published sheet.
const RECORD_FIELDS = [
  ['{supervisor}', 'Supervisor name'],
  ['{supervisortitle}', 'Supervisor job title'],
  ['{designated}', 'Date designated as supervisor'],
  ['{provider}', 'Training provider'],
  ['{alcoholminutes}', 'Alcohol training minutes'],
  ['{drugminutes}', 'Controlled substances training minutes'],
  ['{completedon}', 'Date training completed'],
  ['{certificate}', 'Training certificate attached'],
  ['{note}', 'Additional notes'],
  ['{supervisorsignature}', 'Supervisor signature'],
  ['{supervisorsignedon}', 'Date signed'],
  ['{verifiedby}', 'Verified by'],
]

function PolicyDetail({ item, code, onClose, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/company/policies/${code}`), [code])
  const [f, setF] = useState(null)
  const [draft, setDraft] = useState(null)        // the words, while they are being changed
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (!data) {
    return (
      <Modal title={item.name} onClose={onClose} width={860}
        footer={<button type="button" onClick={onClose}>Close</button>}>
        <Loading error={error} />
      </Modal>
    )
  }
  const now = f ?? { effectiveon: data.effectiveon || '', discipline: data.discipline || '',
    other: data.disciplineother || '' }

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.put('/company/policies/settings', {
        code,
        effectiveon: now.effectiveon || null,
        discipline: now.discipline || null,
        other: now.discipline === 'other' ? now.other : null,
      })
      setF(null); await reload(); onChanged?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal title={item.name} onClose={onClose} brief={item.description} width={900} tall
      footer={draft === null ? (
        <>
          {/* Rewriting the words is a mode, not the finishing action, so it keeps the left
              with the other things that do not commit anything. */}
          <div className="footactions">
            <button type="button" onClick={() => setDraft(data.source)}>
              <Pencil size={13} /> Edit Policy
            </button>
          </div>
          <button type="button" className="primary" disabled={busy} onClick={save}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
          <button type="button" onClick={() => window.print()}>Print</button>
          <button type="button" onClick={onClose}>Close</button>
        </>
      ) : (
        <>
          <button type="button" className="primary" disabled={busy || !draft.trim()}
            onClick={async () => {
              setBusy(true); setErr(null)
              try {
                await api.put(`/company/policies/${code}`, { text: draft })
                setDraft(null); await reload(); onChanged?.()
              } catch (e) { setErr(e.message) } finally { setBusy(false) }
            }}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save the wording'}
          </button>
          <button type="button" onClick={() => setDraft(null)}>Cancel</button>
        </>
      )}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {/* Editing is a mode: the settings and the notice step out of the way so the editor has the
            dialog to itself and its toolbar stays at the top of it. */}
        {draft === null && (
        <>
        {/* The two things in these pages that are the company's own. Everything else is the
            regulation, kept current by TripProof. */}
        <div className="profileform">
          <label className="field span-3">Effective Date
            <input type="date" value={now.effectiveon} min="1900-01-01" max="2100-12-31"
              onChange={(e) => setF({ ...now, effectiveon: e.target.value })} />
          </label>
          {/* Only the DOT policy has a section 10 to fill. The workplace policy says what it
              says about consequences in its own words and has no blank for this. */}
          {code === 'DRUG_POLICY' && (
            <>
              <label className="field span-6">After A DOT Violation, This Company
                <select value={now.discipline}
                  onChange={(e) => setF({ ...now, discipline: e.target.value })}>
                  <option value="">Choose</option>
                  {Object.entries(data.choices || {}).map(([v, l]) =>
                    <option key={v} value={v}>{l}</option>)}
                </select>
              </label>
              {now.discipline === 'other' && (
                <label className="field span-9">In Your Own Words
                  <input value={now.other} className="upper"
                    onChange={(e) => setF({ ...now, other: e.target.value.toUpperCase() })} />
                </label>
              )}
            </>
          )}
        </div>
        {/* Whose words these are, and what that means. A company on its own wording stops
            receiving our corrections, which is worth saying once rather than discovering. */}
        <div className={`notice${data.own ? ' warn' : ''}`}>
          {data.own
            ? 'This is your own wording. It no longer changes when TripProof updates the published '
              + 'policy - put the published text back to start tracking those again.'
            : 'The published policy, kept current by TripProof. Edit it and it becomes yours.'}
          {data.own && (
            <button type="button" className="linkbtn edit" style={{ marginLeft: 8 }} disabled={busy}
              onClick={async () => {
                setBusy(true)
                try { await api.del(`/company/policies/${code}`); setDraft(null); await reload() }
                catch (e) { setErr(e.message) } finally { setBusy(false) }
              }}>Put the published text back</button>
          )}
        </div>

        </>
        )}
        {draft === null ? (
          <>
            {/* The policy as it stands, with the DER printed on it from the appointment on file. */}
            <div className="card policyview"
              dangerouslySetInnerHTML={{ __html: data.text }} />
          </>
        ) : (
          <>
            {/* The blanks are what make this worth having - the DER fills itself from the
                appointment on file - and they are the one thing a rich editor can lose. So they
                are offered from a menu rather than left to be typed, and the editor is told to
                leave the braces alone. */}
            <PolicyEditor value={draft} onChange={setDraft}
              fields={code === 'SUPERVISOR_TRAINING_RECORD'
                ? [...MERGE_FIELDS, ...RECORD_FIELDS] : MERGE_FIELDS} />

          </>
        )}
      </div>
    </Modal>
  )
}

// 49 CFR 382.603. Every person appointed to determine reasonable suspicion needs at least sixty
// minutes on alcohol misuse and sixty on controlled substances, so the screen is the appointments
// with their training beside them - an untrained supervisor is the thing worth seeing.
function SupervisorTraining({ item, onClose, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get('/company/supervisor-training'), [])
  const [roles, , reloadRoles] = useLoad(() => api.get('/company/roles/supervisor'), [])
  const [reading, setReading] = useState(null)
  const [blank, setBlank] = useState(false)
  const [pick, setPick] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (!data) {
    return (
      <Modal title={item.name} onClose={onClose} width={760}
        footer={<button type="button" onClick={onClose}>Close</button>}>
        <Loading error={error} />
      </Modal>
    )
  }
  const people = data.supervisors

  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); await reload(); await reloadRoles(); onChanged?.() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  // What the office does here is appoint people and watch for the signature. It does not
  // record the training: 49 CFR 382.603 is about the person who will decide whether a driver
  // is sent for a test, and a row of minutes typed in by their manager is an assertion about
  // them rather than by them. They sign their own record; this is where you see that they have.
  //
  // The appointment is made from here too, because appointing is the only thing left that
  // moves this requirement - a screen that shows an empty list and sends you elsewhere to fill
  // it is a screen that cannot do the one job it has.
  return (
    <>
      <Modal title={item.name} onClose={onClose} brief={item.description} width={760}
        footer={<>
          <div className="footactions">
            <button type="button" onClick={() => setBlank(true)}>
              <Pencil size={13} /> Edit The Policy
            </button>
          </div>
          <button type="button" onClick={onClose}>Close</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="formactions appointrow">
            <label className="field">Person
              <select value={pick} onChange={(e) => setPick(e.target.value)}>
                <option value="">Choose</option>
                {(roles?.people || [])
                  .filter((u) => !people.some((h) => h.userid === u.recordid))
                  .map((u) => <option key={u.recordid} value={u.recordid}>{u.name}</option>)}
              </select>
            </label>
            <button type="button" className="primary right" disabled={busy || !pick}
              onClick={() => act(async () => {
                await api.post('/company/roles/supervisor', { userid: pick }); setPick('')
              })}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Appoint'}
            </button>
          </div>
          <hr className="brandrule" />
          {!people.length ? (
            <div className="notice warn">
              Nobody holds the supervisor appointment, so nobody in this company may determine
              reasonable suspicion.
            </div>
          ) : (
            <table className="residencetable recordtable">
              <thead><tr><th className="growcol">Supervisor</th><th>Appointed</th>
                <th>Signed</th><th>Record</th><th /></tr></thead>
              <tbody>
                {people.map((x) => (
                  <tr key={x.userid}>
                    <td className="growcol">{x.name}</td>
                    <td>{x.since ? date(x.since) : '-'}</td>
                    <td>{x.signedon ? date(x.signedon) : '-'}</td>
                    {/* The mark, not the word. This column is the state and nothing else, so it
                        reads the way every other state in the product reads. */}
                    <td><Bubble state={x.signedon ? 'satisfied' : 'pending'} /></td>
                    <td className="actions">
                      {x.signedon && (
                        <button type="button" className="linkbtn edit"
                          onClick={() => setReading(x)}>View</button>
                      )}
                      {/* Both actions wear the same pill the other record tables use. The
                          actions column is 150px and lets its content overflow, so a
                          full-size button beside a linkbtn runs off the edge of the dialog. */}
                      <button type="button" className="linkbtn edit" disabled={busy}
                        onClick={() => act(() => api.del(
                          `/company/roles/supervisor/${x.roleid}`))}>Remove</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Modal>
      {/* The blank form IS the policy - the same published sheet, read and edited the way the
          other policies are. What a supervisor signs is a copy of it with their own lines
          filled, so there is nowhere for a form and a policy to drift apart. */}
      {blank && <PolicyDetail item={{ name: 'DOT Reasonable Suspicion Supervisor Training Record',
                                      description: item.description }}
        code="SUPERVISOR_TRAINING_RECORD" onClose={() => setBlank(false)} onChanged={onChanged} />}
      {reading && <SignedRecord who={reading} onClose={() => setReading(null)} />}
    </>
  )
}

// What one supervisor signed, as they signed it - read back from the signature rather than
// re-rendered: the record can be corrected afterwards, the company can rewrite the wording, and
// the words somebody put their name to do not change with either.
function SignedRecord({ who, onClose }) {
  const [data, error] = useLoad(
    () => api.get(`/company/supervisor-training/${who.userid}/signed`), [who.userid])
  return (
    <Modal title={`Training Record - ${who.name}`} onClose={onClose} width={900}
      footer={<>
        <button type="button" onClick={() => window.print()}>Print</button>
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      {!data ? <Loading error={error} /> : (
        <div className="stack">
          <div className="notice good">
            Signed {date(data.signedon)} by {data.signedby}.
          </div>
          <div className="card policyview"
            dangerouslySetInnerHTML={{ __html: data.html || '' }} />
        </div>
      )}
    </Modal>
  )
}

// 29 CFR 1910.1030(c)(2). Which job classifications have occupational exposure to blood, made
// without regard to protective equipment, written down and certified.
//
// What it decides is not filed and forgotten: it is the fact that turns bloodborne pathogens
// training on or off for every driver, so this screen shows the answer in force, what it was
// based on, and every determination before it.
function ExposureDetermination({ item, onClose, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get('/company/exposure-determination'), [])
  const [making, setMaking] = useState(false)
  const [reading, setReading] = useState(null)
  const [blank, setBlank] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (!data) {
    return (
      <Modal title={item.name} onClose={onClose} width={820}
        footer={<button type="button" onClick={onClose}>Close</button>}>
        <Loading error={error} />
      </Modal>
    )
  }
  const held = data.current

  if (making) {
    return <MakeDetermination data={data} onClose={() => setMaking(false)}
      onDone={async () => { setMaking(false); await reload(); onChanged?.() }} />
  }

  return (
    <>
      <Modal title={item.name} onClose={onClose} brief={item.description} width={820}
        footer={<>
          {/* Both on the left: the act first, then the words it is made against. Close keeps
              the right on its own, as it does in every other dialog. */}
          <div className="footactions">
            <button type="button" onClick={() => setBlank(true)}>
              <Pencil size={13} /> Edit Policy
            </button>
          </div>
          {/* Offered only to somebody who may do it. Showing the form to a launched staff
              session and refusing it after they had ticked, signed and pressed Certify is
              warning after the save, which is the thing the guard exists to avoid. */}
          {data.maycertify && (
            <button type="button" onClick={() => setMaking(true)}>
              <Plus size={13} /> {held ? 'Reassess' : 'Make The Determination'}
            </button>
          )}
          <button type="button" onClick={onClose}>Close</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          {data.because && <div className="notice warn">{data.because}</div>}
          {!held ? (
            <div className="notice warn">
              No determination has been made. 29 CFR 1910.1030(c)(2) asks for one either way,
              and until it exists nobody can say whether the drivers owe bloodborne pathogens
              training.
            </div>
          ) : (
            <>
              <section>
                <h3 className="formsection">Determined {date(held.assessedon)}</h3>
                <table className="residencetable recordtable">
                  <thead><tr><th className="growcol">Occupational exposure</th>
                    <th>Next review</th><th>Certified</th><th /></tr></thead>
                  <tbody>
                    <tr>
                      <td className={`growcol ${held.exposed ? 'st-expired' : 'st-active'}`}>
                        {held.exposed ? 'Identified' : 'None identified'}
                      </td>
                      <td>{held.nextreview ? date(held.nextreview) : '-'}</td>
                      <td>{held.signedon ? date(held.signedon) : 'Not certified'}</td>
                      <td className="actions">
                        {held.signedon && (
                          <button type="button" className="linkbtn edit"
                            onClick={() => setReading(held)}>View</button>
                        )}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </section>
              {/* What it was decided on. "There is exposure" without saying which duties
                  make it so is not what 1910.1030(c)(2)(i) asks for. */}
              {data.ticked.length > 0 && (
                <section>
                  <h3 className="formsection">The Duties It Was Decided On</h3>
                  <ul className="hirelist">
                    {data.ticked.map((k) => <li key={k}>{data.duties[k]}</li>)}
                  </ul>
                </section>
              )}
            </>
          )}
          {data.history.length > 1 && (
            <section>
              <h3 className="formsection">Earlier Determinations</h3>
              <table className="residencetable recordtable">
                <thead><tr><th>Assessed</th><th className="growcol">Outcome</th>
                  <th>Made by</th><th>State</th><th /></tr></thead>
                <tbody>
                  {data.history.filter((x) => x.recordid !== held?.recordid).map((x) => (
                    <tr key={x.recordid}>
                      <td>{date(x.assessedon)}</td>
                      <td className="growcol">
                        {x.exposed ? 'Exposure identified' : 'No exposure identified'}
                      </td>
                      <td>{x.madeby || '-'}</td>
                      <td className={x.withdrawn ? 'st-expired' : undefined}>
                        {x.withdrawn ? 'Withdrawn' : 'Superseded'}
                      </td>
                      <td className="actions">
                        {x.signedon && (
                          <button type="button" className="linkbtn edit"
                            onClick={() => setReading(x)}>View</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
          {held && !held.withdrawn && (
            <div className="formactions">
              <button type="button" className="right" disabled={busy}
                onClick={async () => {
                  setBusy(true); setErr(null)
                  try {
                    await api.del(`/company/exposure-determination/${held.recordid}`)
                    await reload(); onChanged?.()
                  } catch (e) { setErr(e.message) } finally { setBusy(false) }
                }}>Withdraw This Determination</button>
            </div>
          )}
        </div>
      </Modal>
      {/* The blank sheet IS the published policy, read and edited the way the others are.
          A certified determination is a copy of it with this company's answers filled in, so
          there is nowhere for a form and a policy to drift apart. */}
      {blank && <PolicyDetail item={{ name: 'Bloodborne Pathogens Occupational Exposure '
                                            + 'Determination', description: item.description }}
        code="BBP_EXPOSURE_DETERMINATION" onClose={() => setBlank(false)}
        onChanged={onChanged} />}
      {reading && <SignedDetermination held={reading} onClose={() => setReading(null)} />}
    </>
  )
}

// Making it. One question, ticked - not a taxonomy to type.
//
// 1910.1030(c)(2) turns on whether anybody's assigned work involves reasonably anticipated
// contact with blood, and the regulation names the duties that make it so. So the company
// ticks the ones its people actually do and the answer follows: any duty is exposure, none is
// not. Nobody has to invent a job classification, and nobody can tick a duty and then record
// "no occupational exposure" beside it.
//
// Section 9 certifies sections 3 to 7, so it is all signed in one act rather than saved now
// and certified later.
function MakeDetermination({ data, onClose, onDone }) {
  const today = new Date().toISOString().slice(0, 10)
  const [f, setF] = useState({ assessedon: today, nextreview: '', changes: '', corrective: '' })
  const [ticked, setTicked] = useState([])
  const [signature, setSignature] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const keys = Object.keys(data.duties)
  const exposed = ticked.length > 0
  // No "I have decided" step. Signing IS the decision, so ticking nothing and signing is a
  // determination of no exposure - the same act, one control fewer.
  const missing = [
    !f.assessedon && 'the assessment date',
    !signature && 'your certification',
  ].filter(Boolean)

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post('/company/exposure-determination', {
        assessedon: f.assessedon,
        duties: ticked,
        nextreview: f.nextreview || null,
        changes: f.changes.trim() || null,
        corrective: f.corrective.trim() || null,
      })
      onDone()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal title="Make The Exposure Determination" onClose={onClose} width={820}
      footer={<>
        <button type="button" className="primary" disabled={busy || missing.length > 0}
          onClick={save}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Certify It'}
        </button>
        <button type="button" onClick={onClose}>Cancel</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="notice warn">
          29 CFR 1910.1030(c)(2)(ii). Decide this without regard to protective equipment - the
          question is what the work exposes somebody to, not what they are given to wear
          against it.
        </div>
        <section>
          <h3 className="formsection">
            Do your people do any of these as part of the job?
          </h3>
          <div className="endorsementgrid onecol">
            {keys.map((k) => (
              <label key={k}>
                <input type="checkbox" checked={ticked.includes(k)}
                  onChange={(e) => setTicked(e.target.checked
                    ? [...ticked, k] : ticked.filter((x) => x !== k))} />
                {data.short?.[k] || data.duties[k]}
              </label>
            ))}
          </div>
        </section>
        {/* The answer, before it is signed - because it is the answer, not a field. Shown from
            the start: nothing ticked is already a reading, and the line says what signing it
            would mean. */}
        {(
          <div className={`notice ${exposed ? 'warn' : 'good'}`}>
            {exposed
              ? 'Occupational exposure identified. The drivers who do this work will owe '
                + 'bloodborne pathogens training, and the company will owe a written exposure '
                + 'control plan.'
              : 'No occupational exposure identified. Neither bloodborne pathogens training '
                + 'nor an exposure control plan is required of this company.'}
          </div>
        )}
        <div className="profileform">
          <label className="field span-2">Assessment Date *
            <input type="date" value={f.assessedon} max={today}
              onChange={(e) => setF({ ...f, assessedon: e.target.value })} />
          </label>
          <label className="field span-2">Next Review
            <input type="date" value={f.nextreview}
              onChange={(e) => setF({ ...f, nextreview: e.target.value })} />
          </label>
          <label className="field span-2" />
          {/* A row each. Both take a sentence, and half a row is not enough of one. */}
          <label className="field span-6">Changes Identified
            <input value={f.changes} className="upper"
              onChange={(e) => setF({ ...f, changes: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-6">Corrective Actions
            <input value={f.corrective} className="upper"
              onChange={(e) => setF({ ...f, corrective: e.target.value.toUpperCase() })} />
          </label>
        </div>
        <SignatureBlock signature={signature} onSigned={setSignature}
          label="Signature Of Authorized Representative" action="Sign" />
      </div>
    </Modal>
  )
}

// The determination as it was certified, read back from the signature.
function SignedDetermination({ held, onClose }) {
  const [data, error] = useLoad(
    () => api.get(`/company/exposure-determination/${held.recordid}/signed`), [held.recordid])
  return (
    <Modal title={`Exposure Determination - ${date(held.assessedon)}`} onClose={onClose}
      width={900}
      footer={<>
        <button type="button" onClick={() => window.print()}>Print</button>
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      {!data ? <Loading error={error} /> : (
        <div className="stack">
          <div className="notice good">
            Certified {date(data.signedon)} by {data.signedby}.
          </div>
          <div className="card policyview"
            dangerouslySetInnerHTML={{ __html: data.html || '' }} />
        </div>
      )}
    </Modal>
  )
}

// One accident as 49 CFR 390.15(b) asks about it, written up from the register rather than
// from one driver's file.
const BLANK_REGISTER = { driverid: '', occurredon: '', location: '', injuries: '',
                         fatalities: '', hazmatreleased: '', note: '' }

// The register - 49 CFR 390.15(b) - across the whole roster. An auditor asking to see it is
// not asking to be walked through the drivers one at a time.
function AccidentRegister({ item, onClose, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get('/accidents'), [])
  const [adding, setAdding] = useState(false)
  const [f, setF] = useState(BLANK_REGISTER)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const now = new Date().toISOString().slice(0, 16)

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/drivers/${f.driverid}/accidents`, {
        occurredon: f.occurredon,
        location: f.location.trim().toUpperCase() || null,
        injuries: f.injuries === '' ? null : Number(f.injuries),
        fatalities: f.fatalities === '' ? null : Number(f.fatalities),
        hazmatreleased: f.hazmatreleased === '' ? null : f.hazmatreleased === 'yes',
        note: f.note.trim().toUpperCase() || null,
      })
      setAdding(false); setF(BLANK_REGISTER); reload(); onChanged?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const kept = data?.accidents || []

  return (
    <Modal title="Accident Register" onClose={onClose} brief={item.description} width={980}
      footer={<>
        <button type="button" onClick={() => { setF({ ...BLANK_REGISTER, occurredon: now }); setAdding(true) }}>
          <Plus size={13} /> Record An Accident
        </button>
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {!data ? <Loading error={error} /> : kept.length ? (
          <table className="residencetable recordtable">
            <thead><tr><th>When</th><th>Driver</th><th className="growcol">Where</th>
              <th>Injured</th><th>Killed</th><th>Hazmat</th><th>Complete</th></tr></thead>
            <tbody>
              {kept.map((x) => (
                <tr key={x.recordid}>
                  <td>{x.occurredon ? date(x.occurredon) : '-'}</td>
                  <td>{x.driver || '-'}</td>
                  <td className="growcol">{x.location || '-'}</td>
                  <td>{x.injuries ?? '-'}</td>
                  <td>{x.fatalities ?? '-'}</td>
                  <td>{x.hazmatreleased === null ? '-' : x.hazmatreleased ? 'Yes' : 'No'}</td>
                  {/* 390.15(b)(1) names the particulars. A register missing one of them is a
                      register that does not answer the question it is kept for. */}
                  <td className={x.missing.length ? 'st-expired' : 'st-active'}>
                    {x.missing.length ? `Missing ${x.missing.join(', ')}` : 'Yes'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="notice good">
            No accident has been recorded. 49 CFR 390.15(b) asks for the list to be kept, and an
            empty list is a list kept - there is nothing outstanding here.
          </div>
        )}
      </div>
      {adding && (
        <Modal title="Record An Accident" onClose={() => setAdding(false)} width={680}
          footer={<>
            <button type="button" className="primary" disabled={busy || !f.driverid || !f.occurredon}
              onClick={save}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={() => setAdding(false)}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="profileform">
              <label className="field span-3">Driver *
                <select value={f.driverid} onChange={(e) => setF({ ...f, driverid: e.target.value })}>
                  <option value="">Choose</option>
                  {(data?.drivers || []).map((d) => (
                    <option key={d.recordid} value={d.recordid}>{d.name}</option>
                  ))}
                </select>
              </label>
              <label className="field span-3">When *
                <input type="datetime-local" value={f.occurredon} max={now}
                  onChange={(e) => setF({ ...f, occurredon: e.target.value })} />
              </label>
              <label className="field span-6">City Or Town, And State
                <input value={f.location}
                  onChange={(e) => setF({ ...f, location: e.target.value.toUpperCase() })} />
              </label>
              <label className="field span-2">People Injured
                <input type="number" min="0" value={f.injuries}
                  onChange={(e) => setF({ ...f, injuries: e.target.value })} />
              </label>
              <label className="field span-2">People Killed
                <input type="number" min="0" value={f.fatalities}
                  onChange={(e) => setF({ ...f, fatalities: e.target.value })} />
              </label>
              <label className="field span-2">Hazmat Released
                <select value={f.hazmatreleased}
                  onChange={(e) => setF({ ...f, hazmatreleased: e.target.value })}>
                  <option value="">Not stated</option>
                  <option value="no">No</option>
                  <option value="yes">Yes</option>
                </select>
              </label>
              <label className="field span-6">Note
                <textarea value={f.note}
                  onChange={(e) => setF({ ...f, note: e.target.value.toUpperCase() })} />
              </label>
            </div>
            <p className="small muted">
              Fuel spilled from the fuel tanks of the vehicles involved is not a hazardous
              material release for this purpose.
            </p>
          </div>
        </Modal>
      )}
    </Modal>
  )
}

// The random testing pool, the annual rates and every draw made from it - 49 CFR 382.305.
function RandomSelections({ item, onClose, onChanged, extra = null, brief = null }) {
  const [data, error, reload] = useLoad(() => api.get('/company/random-selections'), [])
  const [pool] = useLoad(() => api.get('/company/random-pool'), [])
  const [f, setF] = useState(null)
  const [adding, setAdding] = useState(false)
  const [picked, setPicked] = useState([])
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (!data) {
    return (
      <Modal title={item.name} onClose={onClose} width={760}
        footer={<button type="button" onClick={onClose}>Close</button>}>
        <Loading error={error} />
      </Modal>
    )
  }
  const now = f ?? { drawnon: '', testtype: 'drug', selected: '', performedby: '',
                     note: '', file: null }

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('drawnon', now.drawnon)
      body.append('testtype', now.testtype)
      if (now.selected) body.append('selected', now.selected)
      picked.forEach((id) => body.append('drivers', id))
      if (now.performedby.trim()) body.append('performedby', now.performedby.trim())
      if (now.note.trim()) body.append('note', now.note.trim())
      if (now.file) body.append('file', now.file)
      await api.post('/company/random-selections', body)
      setF(null); setPicked([]); setAdding(false); await reload(); onChanged?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  // The MVR pattern: the record in the dialog, the form in a dialog of its own.
  if (adding) {
    return (
      <Modal title="Record A Draw" onClose={() => { setAdding(false); setF(null) }} width={680}
        footer={<>
          <button type="button" className="primary" disabled={busy || !now.drawnon} onClick={save}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
          <button type="button" onClick={() => { setAdding(false); setF(null) }}>Cancel</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="profileform">
            <label className="field span-2">Drawn On
              <input type="date" value={now.drawnon} min="1900-01-01" max="2100-12-31"
                onChange={(e) => setF({ ...now, drawnon: e.target.value })} />
            </label>
            <label className="field span-2">For
              <select value={now.testtype}
                onChange={(e) => setF({ ...now, testtype: e.target.value })}>
                {Object.entries(data.types).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </label>
            <label className="field span-3">Drawn By
              <input value={now.performedby} className="upper"
                onChange={(e) => setF({ ...now, performedby: e.target.value.toUpperCase() })} />
            </label>
            <label className="field span-3">The List Of Names It Produced
              <input type="file"
                onChange={(e) => setF({ ...now, file: e.target.files[0] || null })} />
            </label>
            <label className="field span-6">Note
              <textarea value={now.note} className="upper"
                onChange={(e) => setF({ ...now, note: e.target.value.toUpperCase() })} />
            </label>
          </div>
          {/* Ticked from the pool rather than counted. Only pool members are offered: a name
              that was not in the hat cannot have come out of it, and the count on the draw is
              these ticks, so the two can never disagree. */}
          <section>
            <h3 className="formsection">Who came out</h3>
            {!(pool?.drivers || []).length ? (
              <div className="muted">
                Nobody is in the pool yet. Put drivers in from their own Requirements -
                Random testing pool membership.
              </div>
            ) : (
              <div className="endorsementgrid">
                {pool.drivers.map((d) => (
                  <label key={d.recordid}>
                    <input type="checkbox" checked={picked.includes(d.recordid)}
                      onChange={(e) => setPicked(e.target.checked
                        ? [...picked, d.recordid]
                        : picked.filter((x) => x !== d.recordid))} />
                    {d.name}
                  </label>
                ))}
              </div>
            )}
          </section>
        </div>
      </Modal>
    )
  }

  return (
    <Modal title={item.name} onClose={onClose} brief={brief ?? item.description} width={820}
      footer={<>
        {extra}
        <button type="button" onClick={() => setAdding(true)}>
          <Plus size={13} /> Record A Draw
        </button>
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {/* The pool is two numbers, because the rate is not computed from the one people
            expect. 382.305(b) sets it against the AVERAGE number of driver positions across
            the year - a carrier running twenty drivers all year and one that hired twenty in
            December owe very different numbers of tests. */}
        <section>
          <h3 className="formsection">{data.year}</h3>
          <p className="muted small">
            {data.pool} driver{data.pool === 1 ? '' : 's'} in the pool today
            {data.average !== undefined && (data.averagedsince
              ? `, averaging ${data.average} since ${date(data.averagedsince)}`
              : `, averaging ${data.average} across ${data.year}`)}. The rate is taken on the
            {' '}average, not on today's count - 49 CFR 382.305(b).
          </p>
          <table className="residencetable recordtable">
            <thead><tr><th>For</th><th>Rate</th><th>Drawn</th><th>Owed</th>
              <th className="growcol" /></tr></thead>
            <tbody>
              {Object.entries(data.rates).map(([k, rate]) => (
                <tr key={k}>
                  <td>{data.types[k]}</td>
                  <td>{rate}%</td>
                  <td>{data.progress[k].selected}</td>
                  <td className={data.progress[k].selected >= data.progress[k].owed
                    ? 'st-active' : 'st-expired'}>{data.progress[k].owed}</td>
                  <td className="growcol" />
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section>
          <h3 className="formsection">Drawn</h3>
          {!data.selections.length ? (
            <div className="muted">No Draws Recorded</div>
          ) : (
          <table className="residencetable recordtable">
            <thead><tr><th>Drawn</th><th>For</th><th>Driver</th>
              <th className="growcol">Test</th><th /></tr></thead>
            <tbody>
              {data.selections.flatMap((x) => (
                (x.drivers || []).length ? x.drivers : [null]
              ).map((who, i) => (
                <tr key={who ? who.recordid : x.recordid}>
                  <td>{date(x.drawnon)}
                    {i === 0 && x.poolsize != null && (
                      <div className="muted small">pool of {x.poolsize}</div>
                    )}
                  </td>
                  <td>{data.types[x.testtype] || x.testtype}</td>
                  <td>{who ? who.driver : <span className="muted">No names recorded</span>}</td>
                  <td className={`growcol ${who && who.result
                    ? (['positive', 'refusal', 'adulterated', 'substituted'].includes(who.result)
                      ? 'st-expired' : 'st-active')
                    : who && who.excusedon ? '' : 'st-expired'}`}>
                    {who && who.result
                      ? `${data.results?.[who.result] || who.result}`
                        + `${who.collectedon ? ` ${date(who.collectedon)}` : ''}`
                      : who && who.excusedon ? `Not tested - ${who.excused}`
                        : who ? 'Not tested' : '-'}
                  </td>
                  <td className="actions">
                    {who && !who.testid && !who.excusedon ? (
                      <button type="button" className="linkbtn edit"
                        onClick={() => navigate(`/drivers/${who.driverid}?section=testing`)}>
                        Record The Test
                      </button>
                    ) : who ? (
                      <button type="button" className="linkbtn edit"
                        onClick={() => navigate(`/drivers/${who.driverid}?section=testing`)}>
                        Open
                      </button>
                    ) : null}
                    {i === 0 && !x.tested && (
                      <button type="button" disabled={busy} onClick={async () => {
                        setBusy(true)
                        try {
                          await api.del(`/company/random-selections/${x.recordid}`)
                          await reload(); onChanged?.()
                        } catch (e) { setErr(e.message) } finally { setBusy(false) }
                      }}>Withdraw</button>
                    )}
                  </td>
                </tr>
              )))}
            </tbody>
          </table>
          )}
        </section>
      </div>
    </Modal>
  )
}

// The MIS figures for one year - 49 CFR 382.403, Part 40 Appendix J.
function MisReport({ item, typeid, onClose, onChanged }) {
  const [year, setYear] = useState(null)
  const [data, error] = useLoad(
    () => api.get(`/company/mis-report${year ? `?year=${year}` : ''}`), [year])
  // What 49 CFR 382.403 turns on is that the report was SENT, not that somebody scanned it
  // afterwards. Asking for a document to satisfy it left a carrier who filed on time reading
  // as in violation until the copier was free.
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState({ on: new Date().toISOString().slice(0, 10), file: null })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const record = async () => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('credentialtypeid', typeid)
      body.append('subjectid', 'company')
      body.append('issuedon', sent.on)
      if (sent.file) body.append('file', sent.file)
      await api.post('/credentials', body)
      setSending(false)
      onChanged?.()
      onClose()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  if (!data) {
    return (
      <Modal title={item.name} onClose={onClose} width={900}
        footer={<button type="button" onClick={onClose}>Close</button>}>
        <Loading error={error} />
      </Modal>
    )
  }
  const years = [data.year + 1, data.year, data.year - 1, data.year - 2]
  const d = data.totals.drug, al = data.totals.alcohol

  if (sending) {
    return (
      <Modal title="Record That The MIS Report Was Sent" onClose={() => setSending(false)}
        width={620}
        footer={<>
          <button type="button" className="primary" disabled={busy || !sent.on} onClick={record}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
          <button type="button" onClick={() => setSending(false)}>Cancel</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="profileform">
            <label className="field span-3">Sent On *
              <input type="date" value={sent.on} min="1900-01-01" max="2100-12-31"
                onChange={(e) => setSent({ ...sent, on: e.target.value })} />
            </label>
            {/* Wanted, not required. 382.401(b) asks the carrier to keep it for five years, so
                the copy belongs here - but a report that went in on time went in on time
                whether or not anybody has been to the scanner yet. */}
            <label className="field span-9">Copy Of What You Sent
              <input type="file"
                onChange={(e) => setSent({ ...sent, file: e.target.files[0] || null })} />
            </label>
          </div>
          <div className="small muted">
            Kept five years - 49 CFR 382.401(b). The copy can be added later by recording it
            again.
          </div>
        </div>
      </Modal>
    )
  }

  return (
    <Modal title={item.name} onClose={onClose} brief={item.description} width={900}
      footer={<>
        {typeid && (
          <div className="footactions">
            <button type="button" onClick={() => setSending(true)}>
              <Plus size={13} /> Record That It Was Sent
            </button>
          </div>
        )}
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      <div className="stack">
        <div className="notice">
          <div>
            These are the figures for the <b>U.S. Department of Transportation Drug and Alcohol
            Testing MIS Data Collection Form</b>, printed at 49 CFR Part 40, Appendix J. The
            letter FMCSA sent asking for it says where to send it back.
          </div>
        </div>
        <div className="profileform">
          <label className="field span-2">Calendar Year
            <select value={data.year} onChange={(e) => setYear(Number(e.target.value))}>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
        </div>

        {/* Part II. The form asks for the AVERAGE number of covered driver positions across
            the year, not the headcount the day it is filled in. */}
        <section>
          <h3 className="formsection">Covered employees</h3>
          <p className="muted small">
            {data.covered} average driver position{data.covered === 1 ? '' : 's'}
            {data.coveredfrom ? `, counted from ${date(data.coveredfrom)}` : ''} - the average
            across the year, which is what the form asks for.
          </p>
        </section>

        {/* The two halves of the form. They are separate because the regulation keeps them
            separate: a specimen and a breath sample are not the same test. */}
        {[['drug', 'Controlled substances',
           ['tests', 'negative', 'positive', 'refusal', 'cancelled'],
           ['Tests', 'Negative', 'Positive', 'Refusals', 'Canceled']],
          ['alcohol', 'Alcohol',
           ['tests', 'under02', 'band0202', 'band04', 'refusal', 'cancelled'],
           ['Tests', 'Under 0.02', '0.02 - 0.039', '0.04 or more', 'Refusals', 'Canceled']]
        ].map(([key, title, cols, heads]) => (
          <section key={key}>
            <h3 className="formsection">{title}</h3>
            <table className="residencetable recordtable">
              <thead><tr><th>Reason</th>
                {heads.map((h) => <th key={h}>{h}</th>)}
                <th className="growcol" /></tr></thead>
              <tbody>
                {data.reasons.map((r) => (
                  <tr key={r}>
                    <td>{data.reasonsays[r]}</td>
                    {cols.map((col) => <td key={col}>{data[key][r][col]}</td>)}
                    <td className="growcol" />
                  </tr>
                ))}
                <tr>
                  <td><b>Total</b></td>
                  {cols.map((col) => <td key={col}><b>{(key === 'drug' ? d : al)[col]}</b></td>)}
                  <td className="growcol" />
                </tr>
              </tbody>
            </table>
          </section>
        ))}

        {/* Said out loud rather than folded into a column. A figure on a federal form that
            nobody can trace back to a record is worse than a gap somebody can go and close. */}
        {/* A federal form that reports tests against no employees is a form somebody will be
            asked about. The figure is the average pool across the year, so it reads zero when
            nobody was ever put in the pool - which is a gap in the record, not a fact about
            the business. */}
        {data.covered <= 0 && (d.tests > 0 || al.tests > 0) && (
          <div className="notice bad">
            This says {d.tests + al.tests} tests were given to an average of no drivers. The
            covered-employee figure is counted from the random testing pool, and nobody was in
            it for this year - put the drivers in from their own requirements and this will be
            right.
          </div>
        )}
        {(data.unrecorded > 0 || data.offform > 0) && (
          <div className="notice warn">
            {data.unrecorded > 0 && (
              <div>{data.unrecorded} test{data.unrecorded === 1 ? ' does' : 's do'} not say
                whether {data.unrecorded === 1 ? 'it was' : 'they were'} for controlled
                substances or alcohol, so {data.unrecorded === 1 ? 'it is' : 'they are'} in
                neither half above. Open the test and say which.</div>
            )}
            {data.offform > 0 && (
              <div>{data.offform} test{data.offform === 1 ? '' : 's'} were given for a reason
                the MIS form does not ask about, so they are not counted.</div>
            )}
          </div>
        )}
      </div>
    </Modal>
  )
}

// The employer's Clearinghouse account. Nothing is uploaded because nothing is issued - the
// account is established electronically at FMCSA - so this records its state and who confirmed it.
function ClearinghouseDetail({ item, onClose, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get('/company/clearinghouse'), [])
  const [f, setF] = useState(null)
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
  const r = data.registration
  const now = f ?? {
    registered: r?.registered == null ? '' : String(!!r.registered),
    verifiedon: r?.verifiedon || '',
    ctpaused: !!r?.ctpaused,
    ctpaname: r?.ctpaname || '',
    queryplan: !!r?.queryplan,
    note: r?.note || '',
    file: null,
  }

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('registered', now.registered === 'true')
      if (now.verifiedon) body.append('verifiedon', now.verifiedon)
      body.append('ctpaused', now.ctpaused)
      if (now.ctpaname.trim()) body.append('ctpaname', now.ctpaname.trim())
      body.append('queryplan', now.queryplan)
      if (now.note.trim()) body.append('note', now.note.trim())
      if (now.file) body.append('file', now.file)
      await api.put('/company/clearinghouse', body)
      setF(null); await reload(); onChanged?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal title={item.name} onClose={onClose} brief={item.description} width={760}
      footer={<>
        <button type="button" className="primary" disabled={busy || now.registered === ''}
          onClick={save}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="notice">
          There is no registration form to file. The employer account is created at{' '}
          {data.where}{data.usdot ? `, under USDOT ${data.usdot}` : ''}. Record its state here.
        </div>
        <div className="profileform">
          <label className="field span-3">Employer Account Registered
            <select value={now.registered}
              onChange={(e) => setF({ ...now, registered: e.target.value })}>
              <option value="">Choose</option>
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </label>
          <label className="field span-3">Account Confirmed On
            <input type="date" value={now.verifiedon} min="1900-01-01" max="2100-12-31"
              onChange={(e) => setF({ ...now, verifiedon: e.target.value })} />
          </label>
          <label className="field span-3">Query Plan Bought
            <select value={String(now.queryplan)}
              onChange={(e) => setF({ ...now, queryplan: e.target.value === 'true' })}>
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </label>
          <label className="field span-3">A Consortium Or TPA Acts For Us
            <select value={String(now.ctpaused)}
              onChange={(e) => setF({ ...now, ctpaused: e.target.value === 'true' })}>
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </label>
          {now.ctpaused && (
            <label className="field span-6">Who
              <input value={now.ctpaname} className="upper"
                onChange={(e) => setF({ ...now, ctpaname: e.target.value.toUpperCase() })} />
            </label>
          )}
          <label className="field span-6">Account Confirmation
            <input type="file" onChange={(e) => setF({ ...now, file: e.target.files[0] || null })} />
          </label>
          <label className="field span-9">Note
            <textarea value={now.note} className="upper"
              onChange={(e) => setF({ ...now, note: e.target.value.toUpperCase() })} />
          </label>
        </div>
        {r?.lastverifiedon && (
          <div className="muted">
            Last verified {date(r.lastverifiedon)}
            {r.updatedbyname ? ` by ${r.updatedbyname}` : ''}.
          </div>
        )}
        <div className="notice">{data.driverside}</div>
      </div>
    </Modal>
  )
}


// The FMCSA biennial update. Three things in one screen because they are one job: what is due and
// when, everything the form asks for that is already on file, and the record that it went in.
function Mcs150Detail({ item, onClose, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get('/company/mcs150'), [])
  const [f, setF] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (!data) {
    return (
      <Modal title={item.name} onClose={onClose} width={820}
        footer={<button type="button" onClick={onClose}>Close</button>}>
        <Loading error={error} />
      </Modal>
    )
  }
  const now = f ?? { filedon: '', method: 'portal', note: '', file: null }

  const record = async () => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('filedon', now.filedon)
      body.append('method', now.method)
      if (now.note.trim()) body.append('note', now.note.trim())
      if (now.file) body.append('file', now.file)
      await api.post('/company/mcs150', body)
      setF(null); await reload(); onChanged?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const c = data.counts
  return (
    <Modal title={item.name} onClose={onClose} brief={item.description} width={880} tall
      footer={<>
        <button type="button" className="primary" disabled={busy || !now.filedon} onClick={record}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Record This Filing'}
        </button>
        <button type="button" onClick={() => window.print()}>Print Worksheet</button>
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {!data.usdot ? (
          <div className="notice warn">
            This company has no USDOT number on file, so the filing month cannot be worked out.
            Record it on Company - Operations.
          </div>
        ) : (
          <div className={`notice${data.overdue ? ' bad' : ''}`}>
            USDOT {data.usdot}
            {data.mcnumber ? ` · MC ${data.mcnumber}` : ''} · next update due by{' '}
            <b>{date(data.due)}</b>
            {data.overdue ? ' - this one has not been filed.' : '.'}
          </div>
        )}

        <h3 className="formsection">Record A Filing</h3>
        <div className="profileform">
          <label className="field span-2">Date Filed
            <input type="date" value={now.filedon} min="1900-01-01" max="2100-12-31"
              onChange={(e) => setF({ ...now, filedon: e.target.value })} />
          </label>
          <label className="field span-3">How It Was Filed
            <select value={now.method}
              onChange={(e) => setF({ ...now, method: e.target.value })}>
              {Object.entries(data.methods).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="field span-4">Proof Of Filing
            <input type="file" onChange={(e) => setF({ ...now, file: e.target.files[0] || null })} />
          </label>
          <label className="field span-9">Note
            <textarea value={now.note} className="upper"
              onChange={(e) => setF({ ...now, note: e.target.value.toUpperCase() })} />
          </label>
        </div>

        {data.filings.length > 0 && (
          <table className="residencetable recordtable">
            <thead><tr><th>Filed</th><th>How</th><th>By</th><th /></tr></thead>
            <tbody>
              {data.filings.map((x) => (
                <tr key={x.recordid}>
                  <td>{date(x.filedon)}</td>
                  <td>{data.methods[x.method] || x.method}</td>
                  <td>{x.filedbyname || '-'}</td>
                  <td className="actions">
                    <button type="button" disabled={busy} onClick={async () => {
                      setBusy(true)
                      try { await api.del(`/company/mcs150/${x.recordid}`); await reload(); onChanged?.() }
                      catch (e) { setErr(e.message) } finally { setBusy(false) }
                    }}>Withdraw</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h3 className="formsection">Worksheet</h3>
        <div className="card policyview">
          <h2>Identity</h2>
          <table>
            <tbody>
              {[['Legal name', data.identity.name], ['DBA', data.identity.dba],
                ['Principal address', [data.identity.address1, data.identity.address2,
                  [data.identity.city, data.identity.state, data.identity.zip]
                    .filter(Boolean).join(' ')].filter(Boolean).join(', ')],
                ['Telephone', data.identity.phone], ['Fax', data.identity.fax],
                ['Email', data.identity.email], ['EIN', data.identity.ein],
                ['USDOT number', data.usdot], ['MC number', data.mcnumber],
                ['Company official', data.official]].map(([k, v]) => (
                  <tr key={k}><th>{k}</th><td>{v || '__________'}</td></tr>
                ))}
            </tbody>
          </table>

          <h2>Drivers</h2>
          <table>
            <tbody>
              <tr><th>Total drivers</th><td>{c.driverstotal}</td></tr>
              <tr><th>Drivers holding a CDL</th><td>{c.driverscdl}</td></tr>
            </tbody>
          </table>

          <h2>Vehicles</h2>
          <table>
            <tbody>
              <tr><th>Vans and cars, 8 seats or fewer</th><td>{c.vehicles.van_8_or_fewer}</td></tr>
              <tr><th>Buses, 9 to 15 seats</th><td>{c.vehicles.bus_9_to_15}</td></tr>
              <tr><th>Buses, 16 seats or more</th><td>{c.vehicles.bus_16_or_more}</td></tr>
              {c.vehicles.unknownseats > 0 && (
                <tr><th>Seating capacity not recorded</th><td>{c.vehicles.unknownseats}</td></tr>
              )}
              <tr><th>Total vehicles</th><td>{c.vehicles.total}</td></tr>
            </tbody>
          </table>

          {/* Named rather than left as empty boxes somebody has to notice. A worksheet that
              guesses at a number the carrier certifies to is worse than one that says it cannot. */}
          <h2>Not On File - Answer These On The Form</h2>
          <ul>{Object.values(c.notheld).map((t) => <li key={t}>{t}</li>)}</ul>

          <h2>Where It Goes</h2>
          <p>{data.where.note}</p>
          <p>FMCSA Portal: {data.where.portal}</p>
          <p>By post: {data.where.post}</p>
        </div>
      </div>
    </Modal>
  )
}


// A requirement answered by naming somebody. 49 CFR 40.3 wants an employee of the company, so the
// choice is the people who have a login here rather than a name typed into a box - and an
// appointment that ends keeps its row with a date on it, because who held a role and when is
// exactly what an audit asks.
function RoleDetail({ item, role, onClose, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/company/roles/${role}`), [role])
  const [pick, setPick] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); await reload(); onChanged?.() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal title={item.name} onClose={onClose} brief={item.description} width={680}
      footer={<button type="button" onClick={onClose}>Close</button>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {!data ? <Loading error={error} /> : (
          <>
            {/* The act first, then what it has produced - the same way round as the supervisor
                appointments, because two dialogs that do one job should not read in opposite
                orders. */}
            <div className="formactions appointrow">
              <label className="field">Person
                <select value={pick} onChange={(e) => setPick(e.target.value)}>
                  <option value="">Choose</option>
                  {data.people
                    .filter((u) => !data.held.some((h) => h.userid === u.recordid))
                    .map((u) => <option key={u.recordid} value={u.recordid}>{u.name}</option>)}
                </select>
              </label>
              <button type="button" className="primary right" disabled={busy || !pick}
                onClick={() => act(async () => {
                  await api.post(`/company/roles/${role}`, { userid: pick }); setPick('')
                })}>
                {busy ? <Loader2 size={15} className="spin" /> : 'Appoint'}
              </button>
            </div>
            <hr className="brandrule" />
            <table className="residencetable recordtable">
              <thead><tr><th className="growcol">Who</th><th>Since</th><th /></tr></thead>
              <tbody>
                {data.held.map((h) => (
                  <tr key={h.recordid}>
                    <td className="growcol">{h.name}</td>
                    <td>{date(h.since)}</td>
                    <td className="actions">
                      {/* A pill like every other row action. The actions column lets its
                          content overflow, and a full-size button runs off the edge. */}
                      <button type="button" className="linkbtn edit" disabled={busy}
                        onClick={() => act(() =>
                          api.del(`/company/roles/${role}/${h.recordid}`))}>Remove</button>
                    </td>
                  </tr>
                ))}
                {!data.held.length && (
                  <tr><td colSpan={3}>Nobody holds this role.</td></tr>
                )}
              </tbody>
            </table>
          </>
        )}
      </div>
    </Modal>
  )
}

// One company requirement: what it is, what is on file for it, and the form that would answer it.
function CompanyDetail({ item, types, onClose, onView, onDone, onChanged }) {
  const today = new Date().toISOString().slice(0, 10)
  const [f, setF] = useState({ issuedon: today, expireson: '', file: null })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [filing, setFiling] = useState(false)
  const [policy, setPolicy] = useState(false)
  const [kind, , which] = [(item.evidencesource || '').split(':')[0], 0,
    (item.evidencesource || '').split(':')[1]]
  const typeid = kind === 'credential' ? types?.[which] : null
  // Whether this thing carries an expiry. `days` is a fixed life the rule sets; `ondocument`
  // is a certificate that states its own, and both need the date recorded or nothing can tell
  // the office it has run out.
  const dated = ['days', 'ondocument'].includes(item.recurrence)

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('credentialtypeid', typeid)
      body.append('subjectid', 'company')
      body.append('issuedon', f.issuedon)
      if (f.expireson) body.append('expireson', f.expireson)
      if (f.file) body.append('file', f.file)
      await api.post('/credentials', body)
      onDone()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  // A policy TripProof publishes and fills in. There is nothing to upload: the words are ours and
  // kept current, and what is the company's own - the date it took effect, and the one paragraph
  // at section 10 that is their decision rather than the regulation's - is asked for here.
  if (POLICIES[item.code]) {
    return <PolicyDetail item={item} code={POLICIES[item.code]} onClose={onClose}
      onChanged={onChanged} />
  }

  // Training a named person completed, so it hangs off the supervisor appointments rather than
  // off a filing cabinet.
  if (kind === 'supervisortraining') {
    return <SupervisorTraining item={item} onClose={onClose} onChanged={onChanged} />
  }

  // A decision the company makes and certifies, not a document it files. What it decides is a
  // fact the drivers' requirements read, so it is made here rather than anywhere else.
  if (kind === 'exposuredetermination') {
    return <ExposureDetermination item={item} onClose={onClose} onChanged={onChanged} />
  }

  // The register - 49 CFR 390.15(b). Not a document either: a list, kept across the whole
  // roster, which until now could only be reached one driver at a time through post-accident
  // testing. An auditor asking to see the register is not asking for a tour of the roster.
  if (kind === 'accidentregister') {
    return <AccidentRegister item={item} onClose={onClose} onChanged={onChanged} />
  }

  // Not a document: there is no Clearinghouse registration form. What is held is the state of the
  // employer account at FMCSA.
  if (kind === 'clearinghouse') {
    return <ClearinghouseDetail item={item} onClose={onClose} onChanged={onChanged} />
  }

  // The biennial update is filed with FMCSA, not here. What this holds is when it went in, the
  // proof, and everything the official form asks for that TripProof already knows.
  if (kind === 'mcs150' || item.code === 'MCS150') {
    return <Mcs150Detail item={item} onClose={onClose} onChanged={onChanged} />
  }

  // A role is held by a person. There is nothing to upload and nothing to date - the question is
  // who, and the answer is somebody with a login here.
  if (kind === 'companyrole') {
    return <RoleDetail item={item} role={which} onClose={onClose} onChanged={onChanged} />
  }

  // The enrolment document and the draws drawn from it, on one screen. Two rules, because
  // 382.305 asks two things, but one subject - and the program rule's own standing is
  // computed FROM the draws (`nodraws`), so a dialog that could not show them was asking
  // somebody to answer a question it would not let them see.
  // 49 CFR 382.403. The form is a government document with its own layout and its own
  // submission route, so this does not reproduce it - a lookalike only invites somebody to
  // send ours instead of theirs. What it gives is every figure the form asks for, counted off
  // the records, so filling it in is reading numbers across rather than counting rows by hand
  // at the end of a year.
  if (!filing && item.code === 'DA_MIS_REPORT') {
    return (
      <MisReport item={item} typeid={typeid} onClose={onClose} onChanged={onChanged} />
    )
  }

  if (!filing && item.code === 'RANDOM_TESTING_PROGRAM') {
    if (policy) {
      return (
        <PolicyDetail item={item} code="RANDOM_TESTING_POLICY"
          onClose={() => setPolicy(false)} onChanged={onChanged} />
      )
    }
    return (
      <RandomSelections item={item} onClose={onClose} onChanged={onChanged}
        brief={item.description}
        extra={(
          <div className="footactions">
            <button type="button" onClick={() => setPolicy(true)}>
              <Pencil size={13} /> Edit Policy
            </button>
          </div>
        )} />
    )
  }

  if (!filing && policy && COMPANION_POLICY[item.code]) {
    return (
      <PolicyDetail item={item} code={COMPANION_POLICY[item.code]}
        onClose={() => setPolicy(false)} onChanged={onChanged} />
    )
  }

  if (filing) {
    return (
      <Modal title={`${item.documentid || item.on ? 'Update' : 'Add'} ${item.name}`}
        onClose={() => setFiling(false)} width={620}
        footer={<>
          <button type="button" className="primary"
            disabled={busy || (dated && !f.expireson)} onClick={save}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
          <button type="button" onClick={() => setFiling(false)}>Cancel</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="profileform">
            <label className="field span-3">Issued
              <input type="date" value={f.issuedon} min="1900-01-01" max="2100-12-31"
                onChange={(e) => setF({ ...f, issuedon: e.target.value })} />
            </label>
            {/* Only where the thing goes out of date. A designation stands until it is
                replaced, but a certificate states its own expiry - which is exactly what
                `ondocument` means, and asking only on `days` left those requirements with
                nowhere to put the date and so nothing to watch them expire against. */}
            {dated && (
              <label className="field span-3">Expires *
                <input type="date" value={f.expireson} min={f.issuedon || '1900-01-01'}
                  max="2100-12-31"
                  onChange={(e) => setF({ ...f, expireson: e.target.value })} />
              </label>
            )}
            <label className="field span-6">Copy
              <input type="file" onChange={(e) => setF({ ...f, file: e.target.files[0] || null })} />
            </label>
          </div>
        </div>
      </Modal>
    )
  }

  return (
    /* Built the way a driver's requirement is built: the facts as an `askfacts` list, every
       action in the footer, and the same width - rather than a loose pair of lines with a
       button floating under them. */
    <Modal title={item.name} onClose={onClose} brief={item.description} width={900}
      footer={<>
        {/* Reading what is on file is not one of the actions that change it, so it sits on the
            left with the other read-only footer buttons. */}
        {(item.documentid || COMPANION_POLICY[item.code]) && (
          <div className="footactions">
            {item.documentid && (
              <button type="button"
                onClick={() => onView({ documentid: item.documentid, name: item.name })}>
                <Eye size={13} /> View Current Document
              </button>
            )}
            {COMPANION_POLICY[item.code] && (
              <button type="button" onClick={() => setPolicy(true)}>
                <Pencil size={13} /> Edit Policy
              </button>
            )}
          </div>
        )}
        {typeid && (
          <button type="button" onClick={() => setFiling(true)}>
            <Plus size={13} />
            {/* One flex item, not two. A button is `display: inline-flex` with a gap, so a word
                and a span beside it are spaced by the gap AND by any literal space between
                them - which is how "Update  Commercial Auto Liability Insurance" got two.
                Filing a second certificate replaces the one on file rather than adding to a
                pile, so the button says which of the two it is doing. */}
            <span className="reqname">
              {item.documentid || item.on ? 'Update ' : 'Add '}{item.name}
            </span>
          </button>
        )}
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      <div className="stack">
        {item.note && <div className="notice warn">{item.note}</div>}
        <dl className="askfacts">
          <div><dt>Standing</dt><dd>{item.why}</dd></div>
          {item.authority && <div><dt>Authority</dt><dd>{item.authority}</dd></div>}
          {item.citation && <div><dt>Citation</dt><dd>{item.citation}</dd></div>}
          <div><dt>On file</dt>
            <dd>{item.on ? date(item.on) : 'Nothing yet'}</dd></div>
          {/* A certificate with no expiry recorded is not a certificate that never expires -
              it is one nothing can watch. Say which, rather than printing the rule's "when it
              is first due" line over a document that is already on file. */}
          <div><dt>Next due</dt>
            <dd className={dated && item.on && !item.expireson ? 'st-expired' : undefined}>
              {item.expireson ? date(item.expireson)
                : dated && item.on ? 'No expiry recorded - update it to put one on file'
                  : item.duetext || 'Does not expire'}</dd></div>
          {item.retentionrule && (
            <div><dt>Kept</dt><dd>{item.retentionrule}</dd></div>
          )}
        </dl>
      </div>
    </Modal>
  )
}
