import { useEffect, useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { api, auth } from '../lib/api.js'

const MIN = 12

// Where an invitation or reset link lands: /reset?token=… Works signed in or out; on success the
// user is signed in and sent to their home page.
export default function ResetPassword() {
  const token = new URLSearchParams(window.location.search).get('token') || ''
  const [info, setInfo] = useState(null)
  const [invalid, setInvalid] = useState(null)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!token) { setInvalid('This link is missing its token.'); return }
    api.get(`/auth/reset/${encodeURIComponent(token)}`).then(setInfo).catch((e) => setInvalid(e.message))
  }, [token])

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    if (password.length < MIN) return setError(`Use at least ${MIN} characters.`)
    if (password !== confirm) return setError('The two passwords don’t match.')
    setBusy(true)
    try {
      const r = await api.post('/auth/reset', { token, password })
      auth.set(r.token)
      window.location.assign('/')
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="loginpage">
      <form className="card login stack" onSubmit={submit}>
        <div className="brand"><span className="mark"><ShieldCheck /></span> TripProof</div>
        {invalid ? (
          <>
            <h2 style={{ margin: 0 }}>Link not valid</h2>
            <div className="muted">{invalid}</div>
            <a href="/login">Go to sign in</a>
          </>
        ) : !info ? <div className="muted">Checking your link…</div> : (
          <>
            <div>
              <h2 style={{ margin: '0 0 4px' }}>{info.purpose === 'invite' ? `Welcome, ${info.name}` : 'Choose a new password'}</h2>
              <div className="muted">
                {info.purpose === 'invite' ? `Set a password for your ${info.accountname} login.` : `For ${info.email}.`}
              </div>
            </div>
            <label className="field">Email<input value={info.email} readOnly autoComplete="username" /></label>
            <label className="field">New password (at least {MIN} characters)
              <input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </label>
            <label className="field">Confirm Password
              <input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
            </label>
            {error && <div className="error">{error}</div>}
            <button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Set password and sign in'}</button>
          </>
        )}
      </form>
    </div>
  )
}
