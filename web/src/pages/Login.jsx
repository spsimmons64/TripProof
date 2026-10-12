import { useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { api } from '../lib/api.js'

export default function Login({ onLogin }) {
  const params = new URLSearchParams(window.location.search)
  const welcome = params.get('welcome') === '1'
  const [email, setEmail] = useState(params.get('email') || '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { token } = await api.post('/auth/login', { email, password })
      onLogin(token)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="loginpage">
    <form className="card login stack" onSubmit={submit}>
      <div className="brand"><span className="mark"><ShieldCheck /></span> TripProof</div>
      {welcome
        ? <div className="notice good"><ShieldCheck size={16} /><div>Your account is ready. Sign in with the password you just chose.</div></div>
        : <div className="muted">Trip-by-trip credential proof for NEMT operators.</div>}
      <label className="field">Email<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
      <label className="field">Password<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
      {error && <div className="error">{error}</div>}
      <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      {!welcome && <div className="small muted" style={{ textAlign: 'center' }}>New to TripProof? <a href="/apply">Open an account</a></div>}
    </form>
    </div>
  )
}
