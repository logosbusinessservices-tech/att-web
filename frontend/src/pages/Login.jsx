import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth.jsx'
import { api } from '../lib/api.js'

function PasswordForm({ onDone }) {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      onDone(await login(username, password))
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      {error && <div className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>}
      <input
        className="w-full border border-slate-300 rounded-lg px-3 py-2"
        placeholder="Employee code (e.g. EMP001)"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        autoCapitalize="none"
        autoComplete="username"
      />
      <input
        className="w-full border border-slate-300 rounded-lg px-3 py-2"
        type="password"
        placeholder="Password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="current-password"
      />
      <button disabled={busy} className="w-full bg-slate-900 text-white rounded-lg py-2 font-medium disabled:opacity-50">
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  )
}

function OtpForm({ onDone }) {
  const { loginWithToken } = useAuth()
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [stage, setStage] = useState('phone') // phone | code
  const [hint, setHint] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function requestCode(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const res = await api.requestOtp(phone)
      setStage('code')
      // In dev the backend returns the code so you can test without SMS.
      setHint(res.debug_code ? `Dev code: ${res.debug_code}` : `Code sent. Valid ${res.ttl_minutes} min.`)
    } catch (err) {
      setError(err.message || 'Could not send code')
    } finally {
      setBusy(false)
    }
  }

  async function verify(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const res = await api.verifyOtp(phone, code)
      onDone(await loginWithToken(res.access_token))
    } catch (err) {
      setError(err.message || 'Invalid code')
    } finally {
      setBusy(false)
    }
  }

  if (stage === 'phone') {
    return (
      <form onSubmit={requestCode} className="space-y-4">
        {error && <div className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>}
        <input
          className="w-full border border-slate-300 rounded-lg px-3 py-2"
          type="tel"
          placeholder="Mobile number"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          autoComplete="tel"
        />
        <button disabled={busy} className="w-full bg-slate-900 text-white rounded-lg py-2 font-medium disabled:opacity-50">
          {busy ? 'Sending…' : 'Send code'}
        </button>
      </form>
    )
  }

  return (
    <form onSubmit={verify} className="space-y-4">
      {error && <div className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>}
      {hint && <div className="text-xs text-slate-500 bg-slate-50 rounded-lg px-3 py-2">{hint}</div>}
      <input
        className="w-full border border-slate-300 rounded-lg px-3 py-2 tracking-widest text-center text-lg"
        inputMode="numeric"
        autoComplete="one-time-code"
        placeholder="______"
        maxLength={8}
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
      />
      <button disabled={busy} className="w-full bg-slate-900 text-white rounded-lg py-2 font-medium disabled:opacity-50">
        {busy ? 'Verifying…' : 'Verify & sign in'}
      </button>
      <button type="button" onClick={() => { setStage('phone'); setCode(''); setHint(''); setError('') }}
        className="w-full text-xs text-slate-400 underline">
        Use a different number
      </button>
    </form>
  )
}

export default function Login() {
  const navigate = useNavigate()
  const [mode, setMode] = useState('otp') // otp | password

  function done(me) {
    navigate(me.role === 'supervisor' ? '/supervisor' : '/employee', { replace: true })
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-red-dark p-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl p-6 space-y-4">
        <div className="text-center">
          <img src="/logo.svg" alt="RVNL" className="h-12 mx-auto mb-3" />
          <h1 className="text-xl font-bold text-slate-800">Railway Attendance</h1>
          <p className="text-sm text-slate-500">
            {mode === 'otp' ? 'Sign in with a code sent to your phone' : 'Sign in with your employee code'}
          </p>
        </div>

        <div className="flex bg-slate-100 rounded-lg p-1">
          {['otp', 'password'].map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`flex-1 text-sm py-1.5 rounded-md ${mode === m ? 'bg-white shadow-sm font-medium text-slate-800' : 'text-slate-500'}`}
            >
              {m === 'otp' ? 'OTP' : 'Password'}
            </button>
          ))}
        </div>

        {mode === 'otp' ? <OtpForm onDone={done} /> : <PasswordForm onDone={done} />}

        <button
          onClick={() => navigate('/signup')}
          className="w-full text-sm text-slate-500 pt-1"
        >
          New employee? <span className="text-slate-800 font-medium underline">Create an account</span>
        </button>
      </div>
    </div>
  )
}
