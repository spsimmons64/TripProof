import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Check } from 'lucide-react'
import { FieldError, useFirstField } from '../components/LicenseDialog.jsx'
import PublicShell from '../components/PublicShell.jsx'
import OutsideSignDialog from '../components/OutsideSignDialog.jsx'

// A road test, administered by an examiner from a link - 49 CFR 391.31.
//
// The examiner usually does not work here. They have no account, nothing to prove themselves
// against, and no reason to learn this software - so the page is the whole of their relationship
// with it: the form, the decision, and their signature, on one page, once.
//
// There is no score and there is no pass mark. 391.31 asks the examiner whether the driver can
// operate the vehicle safely; a percentage would invent a threshold the regulation does not have.
// The certificate is produced from what they enter here, so there is no second form to sign.

const FONTS = [['modern', 'Modern'], ['signature', 'Inked'], ['quick', 'Quick'],
               ['hand', 'Handwritten'], ['cursive', 'Cursive'], ['fine', 'Fine'], ['bold', 'Bold']]

const call = async (path, body) => {
  const res = await fetch(`/api/road-test${path}`, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  const json = await res.json().catch(() => null)
  if (!res.ok) throw new Error(typeof json?.detail === 'string' ? json.detail : 'That did not work')
  return json
}

const today = () => new Date().toISOString().slice(0, 10)

export default function RoadTest() {
  const { token } = useParams()
  const [asked, setAsked] = useState(null)
  const [done, setDone] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [bad, setBad] = useState({})
  const [signing, setSigning] = useState(false)
  const box = useFirstField()
  const [v, setV] = useState({
    testedon: today(), startedat: '', endedat: '', miles: '',
    examinername: '', examinertitle: '', examinerorg: '',
    vehicledescr: '', vin: '', vehicletype: '', gvwr: '', seats: '',
    airbrakes: null, manual: null, trailer: null, representative: null,
    ratings: {}, extras: {}, comments: '', result: '', signature: '', fontkey: 'modern',
  })

  useEffect(() => {
    call(`/${token}`).then((r) => {
      setAsked(r)
      setV((s) => ({ ...s, examinername: r.examiner?.name || '' }))
    }).catch((e) => setErr(e.message))
  }, [token])

  const set = (k, value) => { setBad(({ [k]: _g, ...rest }) => rest); setV({ ...v, [k]: value }) }
  const rate = (group, key, value) => setV({ ...v, [group]: { ...v[group], [key]: value } })

  const send = async () => {
    const problems = {}
    if (!v.testedon) problems.testedon = 'When was the test?'
    if (!v.examinername.trim()) problems.examinername = 'Your name is required'
    if (v.representative === null) problems.representative = 'This has to be answered'
    if (!v.result) problems.result = 'Say whether the driver passed'
    if (!v.signature.trim()) problems.signature = 'Sign the certificate'
    setBad(problems)
    if (Object.keys(problems).length) return
    setBusy(true); setErr(null)
    try {
      setDone(await call(`/${token}`, {
        ...v,
        miles: v.miles === '' ? null : Number(v.miles),
        gvwr: v.gvwr === '' ? null : Number(v.gvwr),
        seats: v.seats === '' ? null : Number(v.seats),
        vehicletype: v.vehicletype || null,
      }))
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const frame = (inner) => (
    <PublicShell company={asked?.accountname || done?.accountname} what="Road test" scroll>
      <div className="signsheet">{inner}</div>
    </PublicShell>
  )
  if (done) {
    return frame(
      <div className="card stack signdone">
        <span className="savedmark"><Check size={24} strokeWidth={3} /></span>
        <h1>Thank you</h1>
        <p>The road test is recorded as <b>{done.result}</b> and filed with {done.accountname}.
          You can close this page.</p>
      </div>)
  }
  if (err && !asked) return frame(<div className="card"><div className="notice bad">{err}</div></div>)
  if (!asked) return frame(<div className="card"><p className="muted">Opening…</p></div>)

  // One row per item: what is being judged on the left, the four answers on the right. The same
  // shape the employer's reply form uses, because it is the same kind of question.
  const rateable = (group, list) => (
    <div className="asklist">
      {list.map((i) => (
        <div key={i.key} className="askrow">
          <span className="askwhat">{i.label}</span>
          <span className="askpick">
            {Object.entries(asked.ratings).map(([val, label]) => (
              <label key={val}>
                <input type="radio" name={`${group}-${i.key}`}
                  checked={v[group][i.key] === val}
                  onChange={() => rate(group, i.key, val)} /> {label}
              </label>
            ))}
          </span>
        </div>
      ))}
    </div>
  )

  const yesno = (k, label) => (
    <div className="askrow">
      <span className="askwhat">{label}</span>
      <span className="askpick">
        <label><input type="radio" name={k} checked={v[k] === true}
          onChange={() => set(k, true)} /> Yes</label>
        <label><input type="radio" name={k} checked={v[k] === false}
          onChange={() => set(k, false)} /> No</label>
      </span>
    </div>
  )

  return frame(
    <div className="card stack" ref={box}>
      <h1>Road Test Evaluation</h1>
      <p className="muted">
        {asked.accountname} has asked you to road test {asked.driver.name} under 49 CFR 391.31.
      </p>
      {err && <div className="notice bad">{err}</div>}

      <h3 className="formsection">Driver</h3>
      <dl className="askfacts">
        <div><dt>Driver</dt><dd>{asked.driver.name}</dd></div>
        <div><dt>License</dt>
          <dd>{[asked.driver.licensestate, asked.driver.licensenumber].filter(Boolean).join(' ') || '-'}</dd></div>
        <div><dt>Class</dt><dd>{asked.driver.licenseclass || '-'}</dd></div>
      </dl>

      <h3 className="formsection">The Test</h3>
      <div className="profileform">
        <label className={`field span-2${bad.testedon ? ' bad' : ''}`}>Date *
          <input type="date" value={v.testedon} onChange={(e) => set('testedon', e.target.value)} />
          <FieldError message={bad.testedon} />
        </label>
        <label className="field span-2">Started
          <input type="time" value={v.startedat} onChange={(e) => set('startedat', e.target.value)} />
        </label>
        <label className="field span-2">Ended
          <input type="time" value={v.endedat} onChange={(e) => set('endedat', e.target.value)} />
        </label>
        <label className="field span-2">Approximate Miles
          <input type="number" min="0" value={v.miles}
            onChange={(e) => set('miles', e.target.value)} />
        </label>
        <label className={`field span-2${bad.examinername ? ' bad' : ''}`}>Examiner *
          <input value={v.examinername} className="upper"
            onChange={(e) => set('examinername', e.target.value.toUpperCase())} />
          <FieldError message={bad.examinername} />
        </label>
        <label className="field span-2">Title
          <input value={v.examinertitle} className="upper"
            onChange={(e) => set('examinertitle', e.target.value.toUpperCase())} />
        </label>
        <label className="field span-6">Organization
          <input value={v.examinerorg} className="upper"
            onChange={(e) => set('examinerorg', e.target.value.toUpperCase())} />
        </label>
      </div>

      {/* 391.31(b): the test must be in a vehicle representative of what the driver will operate,
          which is why this section is not optional decoration. */}
      <h3 className="formsection">Vehicle Used</h3>
      <div className="profileform">
        <label className="field span-3">Vehicle
          <input value={v.vehicledescr} className="upper"
            onChange={(e) => set('vehicledescr', e.target.value.toUpperCase())} />
        </label>
        <label className="field span-3">VIN
          <input value={v.vin} className="upper"
            onChange={(e) => set('vin', e.target.value.toUpperCase())} />
        </label>
        <label className="field span-2">Type
          <select value={v.vehicletype} onChange={(e) => set('vehicletype', e.target.value)}>
            <option value="">Choose</option>
            {Object.entries(asked.vehicletypes).map(([k, l]) => (
              <option key={k} value={k}>{l}</option>
            ))}
          </select>
        </label>
        <label className="field span-2">GVWR
          <input type="number" min="0" value={v.gvwr}
            onChange={(e) => set('gvwr', e.target.value)} />
        </label>
        <label className="field span-2">Passenger Capacity
          <input type="number" min="0" value={v.seats}
            onChange={(e) => set('seats', e.target.value)} />
        </label>
      </div>
      <div className="asklist">
        {yesno('airbrakes', 'Air brakes')}
        {yesno('manual', 'Manual transmission')}
        {yesno('trailer', 'Trailer')}
        <div className={`askrow${bad.representative ? ' bad' : ''}`}>
          <span className="askwhat">
            Representative of the vehicle the driver will operate *
            <FieldError message={bad.representative} />
          </span>
          <span className="askpick">
            <label><input type="radio" name="representative" checked={v.representative === true}
              onChange={() => set('representative', true)} /> Yes</label>
            <label><input type="radio" name="representative" checked={v.representative === false}
              onChange={() => set('representative', false)} /> No</label>
          </span>
        </div>
      </div>

      <h3 className="formsection">Evaluation - 49 CFR 391.31(c)</h3>
      {rateable('ratings', asked.items)}

      <h3 className="formsection">Passenger Skills</h3>
      <p className="muted small">
        Company, state or contract requirements. Not part of 49 CFR 391.31.
      </p>
      {rateable('extras', asked.extras)}

      <h3 className="formsection">Decision</h3>
      <div className={`askrow${bad.result ? ' bad' : ''}`}>
        <span className="askwhat">Overall road test result *<FieldError message={bad.result} /></span>
        <span className="askpick">
          {Object.entries(asked.results).map(([k, l]) => (
            <label key={k}><input type="radio" name="result" checked={v.result === k}
              onChange={() => set('result', k)} /> {l}</label>
          ))}
        </span>
      </div>
      <div className="profileform">
        <label className="field span-6">Examiner Comments
          <textarea rows={3} value={v.comments}
            onChange={(e) => set('comments', e.target.value)} />
        </label>
      </div>

      {/* The certification. Signing is its own act behind its own button - nobody proves who this
          person is, because there is nothing to prove against, so the dialog asks for the name and
          nothing else. The line stays blank until they have signed it. */}
      <div className="signhereblock">
        <p className="muted small">
          I certify that I have tested the above-named driver in accordance with 49 CFR 391.31 and
          that the road test was conducted in a vehicle representative of the type of motor vehicle
          the driver will operate.
        </p>
        <div className="signblock">
          <div className="signfields">
            <div className="signbox">
              <span className="signlabel">Signature Of Examiner</span>
              <div className="signline">
                {v.signature && (
                  <span className={`sigink font-${v.fontkey}`}>{v.signature}</span>
                )}
              </div>
            </div>
            <div className="signbox datebox">
              <span className="signlabel">Date</span>
              <div className="signline">
                {v.signature ? new Date().toLocaleDateString('en-US') : null}
              </div>
            </div>
          </div>
          {!v.signature && (
            <div className={`field signaction${bad.signature ? ' bad' : ''}`}>
              <button type="button" className="primary" onClick={() => setSigning(true)}>
                Sign The Certificate
              </button>
              <FieldError message={bad.signature} />
            </div>
          )}
        </div>
      </div>

      <div className="formactions">
        <button type="button" className="primary right" disabled={busy} onClick={send}>
          {busy ? 'Filing…' : 'File The Road Test'}
        </button>
      </div>
      {signing && (
        <OutsideSignDialog title="Sign The Certificate" name={v.examinername}
          certification={'I certify that I have tested the above-named driver in accordance with '
            + '49 CFR 391.31 and that the road test was conducted in a vehicle representative of '
            + 'the type of motor vehicle the driver will operate.'}
          onClose={() => setSigning(false)}
          onSigned={(typedname, fontkey) => {
            setBad(({ signature: _g, ...rest }) => rest)
            setV({ ...v, signature: typedname, fontkey })
            setSigning(false)
          }} />
      )}
    </div>
  )
}
