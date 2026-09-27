import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'

// Public self sign-up. The employee proves their mobile via OTP, then submits
// basic details. The account is created as *pending* and a supervisor in the
// chosen department approves it (assigning the employee code + permissions).
export default function Signup() {
  const navigate = useNavigate()
  const [stage, setStage] = useState('phone') // phone | code | details | done
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [hint, setHint] = useState('')

  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [depts, setDepts] = useState([])
  const [stations, setStations] = useState([])
  const [form, setForm] = useState({
    display_name: '',
    department_id: '',
    home_station_id: '',
    email: '',
    blood_group: '',
  })

  useEffect(() => {
    api.signupOptions().then((o) => {
      setDepts(o.departments || [])
      setStations(o.stations || [])
    }).catch(() => {})
  }, [])

  function set(k, v) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  async function requestCode(e) {
    e.preventDefault()
    setError(''); setBusy(true)
    try {
      const res = await api.signupRequestOtp(phone)
      setStage('code')
      setHint(res.debug_code ? `Dev code: ${res.debug_code}` : `Code sent. Valid ${res.ttl_minutes} min.`)
    } catch (err) {
      setError(err.message || 'Could not send code')
    } finally { setBusy(false) }
  }

  function confirmCode(e) {
    e.preventDefault()
    if (!code) { setError('Enter the code sent to your phone.'); return }
    setError(''); setStage('details')
  }

  async function submit(e) {
    e.preventDefault()
    setError(''); setBusy(true)
    try {
      await api.signup({
        phone,
        code,
        display_name: form.display_name,
        department_id: Number(form.department_id),
        home_station_id: form.home_station_id ? Number(form.home_station_id) : null,
        email: form.email || null,
        blood_group: form.blood_group || null,
      })
      setStage('done')
    } catch (err) {
      setError(err.message || 'Sign-up failed')
      // A bad/expired code is easiest to fix by going back to the code step.
      if (/code/i.test(err.message || '')) setStage('code')
    } finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-red-dark p-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl p-6 space-y-4">
        <div className="text-center">
          <img src="/logo.svg" alt="RVNL" className="h-12 mx-auto mb-3" />
          <h1 className="text-xl font-bold text-slate-800">Create your account</h1>
          <p className="text-sm text-slate-500">Sign up with your mobile number</p>
        </div>

        {error && <div className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>}

        {stage === 'phone' && (
          <form onSubmit={requestCode} className="space-y-4">
            <input
              className={inputCls} type="tel" placeholder="Mobile number" autoComplete="tel"
              value={phone} onChange={(e) => setPhone(e.target.value)}
            />
            <button disabled={busy} className={primaryBtn}>
              {busy ? 'Sending…' : 'Send verification code'}
            </button>
          </form>
        )}

        {stage === 'code' && (
          <form onSubmit={confirmCode} className="space-y-4">
            {hint && <div className="text-xs text-slate-500 bg-slate-50 rounded-lg px-3 py-2">{hint}</div>}
            <input
              className={`${inputCls} tracking-widest text-center text-lg`} inputMode="numeric"
              autoComplete="one-time-code" placeholder="______" maxLength={8}
              value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            />
            <button className={primaryBtn}>Continue</button>
            <button type="button" onClick={() => { setStage('phone'); setCode(''); setHint(''); setError('') }}
              className="w-full text-xs text-slate-400 underline">Use a different number</button>
          </form>
        )}

        {stage === 'details' && (
          <form onSubmit={submit} className="space-y-3">
            <input required className={inputCls} placeholder="Full name *"
              value={form.display_name} onChange={(e) => set('display_name', e.target.value)} />
            <select required className={inputCls} value={form.department_id}
              onChange={(e) => set('department_id', e.target.value)}>
              <option value="">Select department *</option>
              {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
            <select className={inputCls} value={form.home_station_id}
              onChange={(e) => set('home_station_id', e.target.value)}>
              <option value="">Home station (optional)</option>
              {stations.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <input className={inputCls} type="email" placeholder="Email (optional)"
              value={form.email} onChange={(e) => set('email', e.target.value)} />
            <input className={inputCls} placeholder="Blood group (optional)"
              value={form.blood_group} onChange={(e) => set('blood_group', e.target.value)} />
            <p className="text-xs text-slate-400">
              Your supervisor will review this and assign your employee code once approved.
            </p>
            <button disabled={busy} className={primaryBtn}>
              {busy ? 'Submitting…' : 'Submit for approval'}
            </button>
          </form>
        )}

        {stage === 'done' && (
          <div className="space-y-4 text-center">
            <div className="w-16 h-16 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto text-3xl">✓</div>
            <p className="text-sm text-slate-600">
              Thanks! Your sign-up is awaiting supervisor approval. You'll get a text
              once your account is activated.
            </p>
            <button onClick={() => navigate('/login')} className={primaryBtn}>Back to sign in</button>
          </div>
        )}

        {stage !== 'done' && (
          <button onClick={() => navigate('/login')} className="w-full text-xs text-slate-400 underline">
            Already have an account? Sign in
          </button>
        )}
      </div>
    </div>
  )
}

const inputCls = 'w-full border border-slate-300 rounded-lg px-3 py-2 text-sm'
const primaryBtn = 'w-full bg-slate-900 text-white rounded-lg py-2 font-medium disabled:opacity-50'
