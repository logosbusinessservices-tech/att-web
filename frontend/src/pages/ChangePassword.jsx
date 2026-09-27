import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppHeader from '../components/AppHeader.jsx'
import { api } from '../lib/api.js'
import { useAuth } from '../lib/auth.jsx'

export default function ChangePassword({ back }) {
  const { user, refreshUser } = useAuth()
  const navigate = useNavigate()
  const home = user?.role === 'supervisor' ? '/supervisor' : '/employee'

  const [method, setMethod] = useState('old') // old | otp
  const [oldPassword, setOldPassword] = useState('')
  const [otpCode, setOtpCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [hint, setHint] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  async function sendCode() {
    setError('')
    setBusy(true)
    try {
      const res = await api.requestPasswordOtp()
      setHint(res.debug_code ? `Dev code: ${res.debug_code}` : `Code sent to your phone. Valid ${res.ttl_minutes} min.`)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function submit(e) {
    e.preventDefault()
    setError('')
    if (newPassword.length < 6) return setError('New password must be at least 6 characters.')
    if (newPassword !== confirm) return setError('Passwords do not match.')
    setBusy(true)
    try {
      await api.changePassword({
        newPassword,
        oldPassword: method === 'old' ? oldPassword : null,
        otpCode: method === 'otp' ? otpCode : null,
      })
      await refreshUser()
      setDone(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <div className="min-h-screen bg-slate-50">
        <AppHeader title="Change Password" back={back || home} />
        <main className="p-4 max-w-md mx-auto">
          <div className="bg-white rounded-xl shadow-sm p-6 text-center space-y-3">
            <div className="w-14 h-14 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto text-2xl">✓</div>
            <p className="font-semibold text-slate-800">Password updated</p>
            <button onClick={() => navigate(home)} className="w-full bg-slate-900 text-white rounded-lg py-2.5 font-medium">
              Back to menu
            </button>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="Change Password" back={back || home} />
      <main className="p-4 max-w-md mx-auto space-y-4">
        {user?.must_change_password && (
          <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            You're still using your default password (your employee code). Please set a new one.
          </div>
        )}

        {/* How to verify */}
        <div className="flex bg-white rounded-xl shadow-sm p-1">
          {[['old', 'Current password'], ['otp', 'OTP (2FA)']].map(([m, label]) => (
            <button
              key={m}
              onClick={() => { setMethod(m); setError('') }}
              className={`flex-1 text-sm py-1.5 rounded-lg ${method === m ? 'bg-slate-900 text-white' : 'text-slate-600'}`}
            >
              {label}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="bg-white rounded-xl shadow-sm p-4 space-y-3">
          {method === 'old' ? (
            <label className="block text-xs text-slate-500">
              Current password
              <input
                type="password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                autoComplete="current-password"
                className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              />
            </label>
          ) : (
            <div className="space-y-2">
              <div className="flex gap-2">
                <input
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="Enter code sent to your phone"
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ''))}
                  className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm tracking-widest text-center"
                />
                <button type="button" onClick={sendCode} disabled={busy}
                  className="px-3 text-sm bg-slate-200 text-slate-700 rounded-lg disabled:opacity-50">
                  Send code
                </button>
              </div>
              {hint && <p className="text-xs text-slate-500">{hint}</p>}
            </div>
          )}

          <label className="block text-xs text-slate-500">
            New password
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
            />
          </label>
          <label className="block text-xs text-slate-500">
            Confirm new password
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
            />
          </label>

          {error && <p className="text-red-600 text-xs">{error}</p>}

          <button type="submit" disabled={busy}
            className="w-full bg-slate-900 text-white text-sm py-2.5 rounded-lg disabled:opacity-50">
            {busy ? 'Saving…' : 'Update password'}
          </button>
        </form>
      </main>
    </div>
  )
}
