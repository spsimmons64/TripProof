import { useState } from 'react'
import { Loader2, ShieldCheck } from 'lucide-react'
import { api } from '../lib/api.js'
import { Loading, useLoad } from '../components/ui.jsx'

// How this company takes a card for a private-pay trip.
//
// Its own merchant account, through whichever processor it already banks with - NOT the
// Stripe account on the Billing tab, which is what TripProof charges this company through.
// Two things called "payments" in one product is how somebody refunds a passenger out of the
// wrong merchant account, so they sit on different tabs and are named for whose money moves.
//
// Nothing here charges anybody yet. This is the connection; the charge comes later, and a
// screen that implied otherwise would be a lie told to somebody about to paste a live key.
export default function MerchantConnect() {
  const [data, error, reload] = useLoad(() => api.get('/company/gateways'), [])
  // null means "whatever is on file"; an empty string is a deliberate "none".
  const [picked, setPicked] = useState(null)

  if (!data) return <Loading error={error} page />
  const held = Object.fromEntries(data.configured.map((g) => [g.code, g]))
  const code = picked === null ? (data.chosen || '') : picked
  const gateway = data.available.find((g) => g.code === code)

  return (
    <div className="stack">
      <div className="pagehead">
        <div>
          <h1>Merchant Connect</h1>
        </div>
      </div>

      <div className="card">
        <div className="profileform">
          <label className="field span-3">Merchant Services Company
            <select value={code} onChange={(e) => setPicked(e.target.value)}>
              <option value="">Not set</option>
              {data.available.map((g) => (
                <option key={g.code} value={g.code}>
                  {g.name}{held[g.code] ? ' - set up' : ''}
                </option>
              ))}
            </select>
          </label>
          {data.chosen && (
            <div className="field span-3 beside">
              <span className={held[data.chosen]?.ready ? 'st-active' : 'st-expired'}>
                {held[data.chosen]?.ready
                  ? `Taking payments through ${held[data.chosen].name}`
                  : `${held[data.chosen]?.name} is missing something it needs`}
              </span>
            </div>
          )}
        </div>

        {gateway && (
          /* Keyed on the gateway, so switching the dropdown starts a clean form instead of
             carrying one processor's half-typed keys into another's fields. */
          <GatewayForm key={gateway.code} gateway={gateway} held={held[gateway.code]}
            modes={data.modes} onDone={(next) => { setPicked(next); reload() }} />
        )}
      </div>
    </div>
  )
}

function GatewayForm({ gateway, held, modes, onDone }) {
  // Secrets start blank even where one is on file, and blank means "leave it alone". Filling
  // them in would put the key back on the wire and back on the screen every time somebody
  // opened this to change the mode.
  const [f, setF] = useState({
    mode: held?.mode || 'test',
    values: Object.fromEntries(gateway.fields.map((x) => [
      x.name, x.secret ? '' : (held?.values?.[x.name] || ''),
    ])),
  })
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const set = (name) => (e) => setF({ ...f, values: { ...f.values, [name]: e.target.value } })

  // Required unless it is already sealed on file.
  const missing = gateway.fields.filter((x) => !x.optional
    && !(f.values[x.name] || '').trim()
    && !(x.secret && held?.secrets?.[x.name]?.set))

  const act = async (fn, key, next) => {
    setBusy(key); setErr(null)
    try { await fn(); onDone(next) } catch (e) { setErr(e.message); setBusy(null) }
  }

  return (
    <>
      <hr className="brandrule" />
      <h3 className="formsection">{gateway.name}</h3>
      {gateway.note && <p className="muted small">{gateway.note}</p>}
      {err && <div className="notice bad">{err}</div>}
      <div className="profileform">
        <label className="field span-2">Mode
          <select value={f.mode} onChange={(e) => setF({ ...f, mode: e.target.value })}>
            {Object.entries(modes).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <div className="span-4" />
        {gateway.fields.map((x) => {
          const on = held?.secrets?.[x.name]
          return (
            <label className="field span-3" key={x.name}>
              {x.label}{x.optional ? '' : ' *'}
              {/* A gateway's credentials are compared character for character at the other
                  end, so they are the one place the house rule about upper case does not reach. */}
              <input value={f.values[x.name]} onChange={set(x.name)} data-case="none"
                type={x.secret ? 'password' : 'text'} autoComplete="off" spellCheck="false"
                placeholder={on?.set ? `On file ${on.hint} - leave blank to keep it` : ''} />
              {x.hint && <span className="muted small">{x.hint}</span>}
            </label>
          )
        })}
      </div>

      {/* What happens to a key, without naming how. The method is the one detail here that
          helps somebody attacking it and helps nobody using it. */}
      <p className="small keysafe">
        <ShieldCheck size={26} strokeWidth={2.2} /> Keys are encrypted before they are
        written down, tied to this company so a copy is useless anywhere else, and are never
        shown again - not on this screen, and not to TripProof.
      </p>

      <div className="formactions">
        {held && (
          <button type="button" disabled={busy !== null}
            onClick={() => act(() => api.del(`/company/gateways/${gateway.code}`),
              'remove', '')}>
            Remove
          </button>
        )}
        {/* Saving connects it. There is no separate "now use it" step: a company that has
            just typed its keys in has said which processor it uses. */}
        <button type="button" className="primary right"
          disabled={busy !== null || missing.length > 0}
          onClick={() => act(async () => {
            await api.put(`/company/gateways/${gateway.code}`, f)
            await api.post(`/company/gateways/${gateway.code}/use`, {})
          }, 'save', gateway.code)}>
          {busy === 'save' ? <Loader2 size={15} className="spin" /> : 'Save And Connect'}
        </button>
      </div>
    </>
  )
}
