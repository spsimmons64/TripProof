import { useEffect, useMemo, useRef, useState } from 'react'
import { loadStripe } from '@stripe/stripe-js'
import { CardElement, Elements, useElements, useStripe } from '@stripe/react-stripe-js'
import { AlertTriangle, Building2, Check, CreditCard, FileText, Layers, ShieldCheck, Truck } from 'lucide-react'
import { api, auth } from '../lib/api.js'
import { PhoneInput, ZipInput } from '../components/MaskedInput.jsx'
import { US_STATES } from '../admin/CustomerProfile.jsx'

const STEPS = [['Account information', Building2], ['Subscription', Layers], ['Payment card', CreditCard], ['Terms of Service', FileText]]
const MIN_PASSWORD = 12

// The online application: /apply. Step 1 creates the account (status "setup") and signs the
// applicant in, so an unfinished application resumes here after they sign in again. Step 2 picks
// the subscription from the fleet size. Step 3 has Stripe verify a card. Step 4 records the Terms,
// starts the subscription and makes the account active, then hands off to the login page.
export default function Apply({ resume }) {
  const [config, setConfig] = useState(null)
  const [state, setState] = useState(null)       // server's view once the account exists
  const [step, setStep] = useState(1)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/apply/config').then(setConfig).catch((e) => setError(e.message))
    if (resume) {
      api.get('/apply/state').then((s) => { setState(s); setStep(s.step) }).catch((e) => setError(e.message))
    }
  }, [resume])

  const stripePromise = useMemo(() => (config?.stripe ? loadStripe(config.stripe) : null), [config])
  const signOut = () => { auth.clear(); window.location.assign('/login') }

  return (
    <div className="applypage">
      <div className="applycard card">
        <div className="applyhead">
          <div className="brand"><span className="mark"><ShieldCheck /></span> TripProof</div>
          {state ? <button className="linkbtn" onClick={signOut}>Save and finish later</button>
            : <a href="/login" className="small">Already have an account? Sign in</a>}
        </div>
        <h1>Open your TripProof account</h1>
        <ol className="stepper">
          {STEPS.map(([label, Icon], i) => {
            const n = i + 1
            return (
              <li key={label} className={n === step ? 'on' : n < step ? 'done' : ''}>
                <span className="dot">{n < step ? <Check size={14} /> : <Icon size={14} />}</span>
                <span className="lbl"><span className="muted small">Step {n}</span>{label}</span>
              </li>
            )
          })}
        </ol>
        {error && <div className="notice bad"><AlertTriangle size={16} /> {error}</div>}
        {!config ? <div className="muted">Loading…</div> : (
          <>
            {step === 1 && <AccountStep state={state} onDone={(s) => { setState(s); setStep(2) }} />}
            {step === 2 && <PlanStep state={state} onBack={() => setStep(1)} onDone={(s) => { setState(s); setStep(3) }} />}
            {step === 3 && (stripePromise
              ? <Elements stripe={stripePromise}><CardStep state={state} onBack={() => setStep(2)} onDone={(s) => { setState(s); setStep(4) }} /></Elements>
              : <NoStripeCardStep onBack={() => setStep(2)} onDone={(s) => { setState(s); setStep(4) }} />)}
            {step === 4 && <TermsStep state={state} onBack={() => setStep(3)} />}
          </>
        )}
      </div>
    </div>
  )
}

// ---- Step 1 ---------------------------------------------------------------------------------------

function AccountStep({ state, onDone }) {
  const a = state?.account
  const [v, setV] = useState({
    name: a?.name || '', address1: a?.address1 || '', address2: a?.address2 || '', city: a?.city || '', state: a?.state || 'FL',
    zip: a?.zip || '', phone: a?.phone || '', fax: a?.fax || '', adminname: a?.adminname || '', adminemail: a?.adminemail || '',
    password: '', confirm: '', website: '',
  })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  // Functional update: browser autofill fires several fields at once, and each must build on the last.
  const set = (k) => (e) => { const value = e.target.value; setV((prev) => ({ ...prev, [k]: value })) }
  const existing = !!state

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!existing) {
      if (v.password.length < MIN_PASSWORD) return setError(`Choose a password of at least ${MIN_PASSWORD} characters.`)
      if (v.password !== v.confirm) return setError('The two passwords don’t match.')
    }
    setBusy(true)
    try {
      const { confirm, ...body } = v
      if (existing) {
        const { adminemail, password, website, ...fields } = body
        onDone(await api.put('/apply/account', fields))
      } else {
        const r = await api.post('/apply/start', body)
        auth.set(r.token)
        onDone(await api.get('/apply/state'))
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="stack">
      <section>
        <h3 className="formsection">Company</h3>
        <div className="profileform">
          <label className="field span-6">Company name *<input required value={v.name} onChange={set('name')} autoComplete="organization" /></label>
          <label className="field span-6">Address line 1 *<input required value={v.address1} onChange={set('address1')} autoComplete="address-line1" /></label>
          <label className="field span-6">Address line 2<input value={v.address2} onChange={set('address2')} autoComplete="address-line2" /></label>
          <label className="field span-3">City *<input required value={v.city} onChange={set('city')} autoComplete="address-level2" /></label>
          <label className="field span-1">State
            <select value={v.state} onChange={set('state')}>{US_STATES.map((s) => <option key={s}>{s}</option>)}</select>
          </label>
          <label className="field span-2">ZIP *<ZipInput required value={v.zip} onChange={set('zip')} /></label>
          <label className="field span-3">Telephone *<PhoneInput required value={v.phone} onChange={set('phone')} /></label>
          <label className="field span-3">Fax<PhoneInput value={v.fax} onChange={set('fax')} autoComplete="off" /></label>
        </div>
      </section>
      <section>
        <h3 className="formsection">Your login</h3>
        <div className="profileform">
          <label className="field span-3">Your name *<input required value={v.adminname} onChange={set('adminname')} autoComplete="name" /></label>
          <label className="field span-3">Email *<input type="email" required value={v.adminemail} onChange={set('adminemail')}
            readOnly={existing} className={existing ? 'readonly' : undefined} autoComplete="email" /></label>
          {!existing && <>
            <label className="field span-3">Password (at least {MIN_PASSWORD} characters) *<input type="password" required value={v.password} onChange={set('password')} autoComplete="new-password" /></label>
            <label className="field span-3">Confirm password *<input type="password" required value={v.confirm} onChange={set('confirm')} autoComplete="new-password" /></label>
          </>}
        </div>
        {/* Honeypot: hidden from people, filled in by bots. */}
        <input className="hp" tabIndex={-1} autoComplete="off" aria-hidden="true" value={v.website} onChange={set('website')} name="website" />
      </section>
      {error && <div className="error">{error}</div>}
      <div className="applyfoot">
        <span />
        <button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Continue to subscription'}</button>
      </div>
    </form>
  )
}

// ---- Step 2: subscription ---------------------------------------------------------------------------

const money = (v) => `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: Number(v) % 1 ? 2 : 0 })}`
const range = (p) => (p.maxvehicles ? `${p.minvehicles}-${p.maxvehicles} vehicles` : `${p.minvehicles}+ vehicles`)
const fits = (p, n) => n >= p.minvehicles && (p.maxvehicles == null || n <= p.maxvehicles)

function PlanStep({ state, onBack, onDone }) {
  const [plans, setPlans] = useState(null)
  const [fleet, setFleet] = useState(state?.fleetsize ? String(state.fleetsize) : '')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.get('/apply/plans').then(setPlans).catch((e) => setError(e.message)) }, [])
  const n = parseInt(fleet, 10)
  const match = plans && n > 0 ? plans.find((p) => fits(p, n)) : null

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try { onDone(await api.put('/apply/plan', { fleetsize: n })) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <form onSubmit={submit} className="stack">
      <section>
        <h3 className="formsection">Select your subscription</h3>
        <p className="muted" style={{ marginTop: 0 }}>Pricing is based on the size of your fleet. Tell us how many vehicles you operate and we’ll match your plan.</p>
        <label className="field fleetfield">
          How many vehicles do you operate? *
          <span className="fleetinput"><Truck size={16} /><input type="number" min="1" required value={fleet} onChange={(e) => setFleet(e.target.value)} /></span>
        </label>
        {!plans ? <div className="muted">Loading plans…</div> : (
          <div className="plans">
            {plans.map((p) => (
              <button type="button" key={p.recordid} className={`plan${p.contact ? ' contact' : ''}${match?.recordid === p.recordid ? ' on' : ''}`}
                onClick={() => !p.contact && setFleet(String(Math.max(p.minvehicles, n && fits(p, n) ? n : p.minvehicles)))}>
                {match?.recordid === p.recordid && <span className="planpick"><Check size={12} /> Your plan</span>}
                <span className="planname">{p.name}</span>
                <span className="planrange">{range(p)}</span>
                <span className="planprice">{p.contact ? 'Contact us' : <>{money(p.monthlyprice)}<small>/month</small></>}</span>
                {p.trialdays > 0 && !p.contact && <span className="plantrial">{p.trialdays}-day free trial</span>}
                <ul>{p.features.map((f) => <li key={f}>{f}</li>)}</ul>
              </button>
            ))}
          </div>
        )}
        {match?.contact && (
          <div className="notice info" style={{ marginTop: 12 }}><AlertTriangle size={16} /><div>Fleets of {match.minvehicles}+ vehicles are priced individually - please contact us and we’ll set up your account.</div></div>
        )}
      </section>
      {error && <div className="error">{error}</div>}
      <div className="applyfoot">
        <button type="button" onClick={onBack}>Back</button>
        <button className="primary" disabled={busy || !match || match.contact}>
          {busy ? 'Saving…' : match && !match.contact ? `Continue with ${match.name}` : 'Continue to payment'}
        </button>
      </div>
    </form>
  )
}

// ---- Step 3: card ---------------------------------------------------------------------------------

function CardStep({ state, onBack, onDone }) {
  const stripe = useStripe()
  const elements = useElements()
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [changing, setChanging] = useState(!state?.card)

  const verify = async (e) => {
    e.preventDefault()
    if (!stripe || !elements) return
    setBusy(true); setError(null)
    try {
      const { clientsecret } = await api.post('/apply/card/intent')
      const res = await stripe.confirmCardSetup(clientsecret, {
        payment_method: { card: elements.getElement(CardElement),
          billing_details: { name: state.account.adminname, email: state.account.adminemail,
            address: { line1: state.account.address1, postal_code: state.account.zip, country: 'US' } } },
      })
      if (res.error) throw new Error(res.error.message)
      onDone(await api.post('/apply/card/verify', {}))       // the server re-checks with Stripe
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={verify} className="stack">
      <section>
        <h3 className="formsection">Payment card</h3>
        <p className="muted" style={{ marginTop: 0 }}>We verify the card now; you won’t be charged until your subscription starts. Card details go straight to our payment processor, Stripe - TripProof never sees or stores the full number.</p>
        {state?.card && !changing ? (
          <div className="cardok"><Check size={16} /> {cardLabel(state.card)} verified <button type="button" className="linkbtn" onClick={() => setChanging(true)}>Use a different card</button></div>
        ) : (
          <div className="cardbox"><CardElement options={{ hidePostalCode: true, style: { base: { fontSize: '16px', color: '#13272b', '::placeholder': { color: '#74858a' } } } }} /></div>
        )}
      </section>
      {error && <div className="error">{error}</div>}
      <div className="applyfoot">
        <button type="button" onClick={onBack}>Back</button>
        {state?.card && !changing
          ? <button type="button" className="primary" onClick={() => onDone(state)}>Continue to terms</button>
          : <button className="primary" disabled={busy || !stripe}>{busy ? 'Verifying…' : 'Verify card and continue'}</button>}
      </div>
    </form>
  )
}

function NoStripeCardStep({ onBack, onDone }) {
  const [error, setError] = useState(null)
  const skip = async () => {
    try { onDone(await api.post('/apply/card/verify', { skip: true })) } catch (e) { setError(e.message) }
  }
  return (
    <div className="stack">
      <section>
        <h3 className="formsection">Payment card</h3>
        <div className="notice warn"><AlertTriangle size={16} /><div>Card payments aren’t set up on this server (no Stripe keys), so the card check can be skipped. This option disappears once STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY are set.</div></div>
      </section>
      {error && <div className="error">{error}</div>}
      <div className="applyfoot">
        <button type="button" onClick={onBack}>Back</button>
        <button className="primary" onClick={skip}>Skip card (development) and continue</button>
      </div>
    </div>
  )
}

const cardLabel = (c) => (c.last4 ? `${c.brand.toUpperCase()} ending ${c.last4} (exp ${c.exp})` : 'Card step skipped')

// ---- Step 4: terms -------------------------------------------------------------------------------

function TermsStep({ state, onBack }) {
  const [terms, setTerms] = useState(null)
  const [readToEnd, setReadToEnd] = useState(false)
  const [agree, setAgree] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const box = useRef()

  useEffect(() => { api.get('/apply/terms').then(setTerms).catch((e) => setError(e.message)) }, [])
  const onScroll = () => {
    const el = box.current
    if (el && el.scrollTop + el.clientHeight >= el.scrollHeight - 24) setReadToEnd(true)
  }
  // A tall screen may show the whole text at once; check only once the terms are actually there
  // (the "Loading…" placeholder would otherwise count as read to the end).
  useEffect(() => { if (terms) onScroll() }, [terms])  // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async () => {
    setBusy(true); setError(null)
    try {
      const r = await api.post('/apply/complete', { agree, tosversion: terms.version, tossha256: terms.sha256 })
      // Done: sign out of the application session and land on the login page, email filled in.
      auth.clear()
      window.location.assign(`/login?welcome=1&email=${encodeURIComponent(r.email)}`)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <section>
        <h3 className="formsection">Terms of Service</h3>
        {state?.plan && (
          <div className="ordersum">
            <div><span className="muted small">Subscription</span><b>{state.plan.name}</b> · {state.fleetsize} vehicles</div>
            <div><span className="muted small">Price</span><b>{money(state.plan.monthlyprice)}/month</b>{state.plan.trialdays > 0 && <> after a {state.plan.trialdays}-day free trial</>}</div>
            {state.card && <div><span className="muted small">Payment</span>{cardLabel(state.card)}</div>}
          </div>
        )}
        <div className="tosbox" ref={box} onScroll={onScroll}>
          {terms ? <Markdown text={terms.text} /> : 'Loading…'}
        </div>
        <label className={`check agree${readToEnd ? '' : ' disabled'}`}>
          <input type="checkbox" checked={agree} disabled={!readToEnd} onChange={(e) => setAgree(e.target.checked)} />
          <span>I have read and agree to the TripProof Terms of Service{terms ? ` (version ${terms.version})` : ''} on behalf of <b>{state?.account?.name}</b>, and I’m authorized to do so.</span>
        </label>
        {!readToEnd && <div className="small muted">Scroll to the end of the terms to continue.</div>}
      </section>
      {error && <div className="error">{error}</div>}
      <div className="applyfoot">
        <button type="button" onClick={onBack}>Back</button>
        <button className="primary" disabled={!agree || busy || !terms} onClick={submit}>{busy ? 'Creating your account…' : 'Create my account'}</button>
      </div>
    </div>
  )
}

// Just enough Markdown for the Terms: #/## headings, paragraphs, "- " lists, **bold**.
function Markdown({ text }) {
  const inline = (s, key) => s.split(/(\*\*[^*]+\*\*)/).map((part, i) =>
    part.startsWith('**') ? <b key={`${key}-${i}`}>{part.slice(2, -2)}</b> : part)
  const blocks = []
  let list = null
  text.split('\n').forEach((line, i) => {
    if (line.startsWith('- ')) {
      if (!list) { list = []; blocks.push({ type: 'ul', items: list, key: i }) }
      list.push(line.slice(2))
      return
    }
    list = null
    if (line.startsWith('## ')) blocks.push({ type: 'h3', text: line.slice(3), key: i })
    else if (line.startsWith('# ')) blocks.push({ type: 'h2', text: line.slice(2), key: i })
    else if (line.trim()) blocks.push({ type: 'p', text: line, key: i })
  })
  return blocks.map((b) => b.type === 'ul'
    ? <ul key={b.key}>{b.items.map((it, j) => <li key={j}>{inline(it, `${b.key}-${j}`)}</li>)}</ul>
    : b.type === 'h2' ? <h2 key={b.key}>{b.text}</h2>
    : b.type === 'h3' ? <h3 key={b.key}>{b.text}</h3>
    : <p key={b.key}>{inline(b.text, b.key)}</p>)
}
