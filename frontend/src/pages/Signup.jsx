import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'

// Public self sign-up. The applicant submits all their details in one form; the
// account is created as *pending* and an Executive Assistant approves it
// (assigning the employee code + onboarding attendance photos). No OTP.
export default function Signup() {
  const navigate = useNavigate()
  const [stage, setStage] = useState('details') // details | done
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const [depts, setDepts] = useState([])
  const [stations, setStations] = useState([])
  const [designations, setDesignations] = useState([])
  const [employmentTypes, setEmploymentTypes] = useState([])
  const [form, setForm] = useState({
    display_name: '',
    phone: '',
    date_of_birth: '',
    department_id: '',
    department_custom: '',
    designation_id: '',
    designation_custom: '',
    employment_type_id: '',
    employment_type_custom: '',
    home_station_id: '',
    email: '',
    blood_group: '',
  })

  useEffect(() => {
    api.signupOptions().then((o) => {
      setDepts(o.departments || [])
      setStations(o.stations || [])
      setDesignations(o.designations || [])
      setEmploymentTypes(o.employment_types || [])
    }).catch(() => {})
  }, [])

  function set(k, v) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  function isOther(list, id) {
    const sel = list.find((x) => String(x.id) === String(id))
    return !!(sel && sel.is_other)
  }

  async function submit(e) {
    e.preventDefault()
    setError('')
    if (!form.display_name.trim()) return setError('Enter your full name.')
    if (!form.phone.trim()) return setError('Enter your mobile number.')
    if (!form.department_id) return setError('Select your department.')
    if (isOther(depts, form.department_id) && !form.department_custom.trim())
      return setError('Enter your department.')
    if (isOther(designations, form.designation_id) && !form.designation_custom.trim())
      return setError('Enter your designation.')
    if (isOther(employmentTypes, form.employment_type_id) && !form.employment_type_custom.trim())
      return setError('Enter your employment type.')
    setBusy(true)
    try {
      await api.signup({
        phone: form.phone,
        display_name: form.display_name,
        department_id: Number(form.department_id),
        department_custom: isOther(depts, form.department_id) ? form.department_custom : null,
        designation_id: form.designation_id ? Number(form.designation_id) : null,
        designation_custom: isOther(designations, form.designation_id) ? form.designation_custom : null,
        employment_type_id: form.employment_type_id ? Number(form.employment_type_id) : null,
        employment_type_custom: isOther(employmentTypes, form.employment_type_id) ? form.employment_type_custom : null,
        date_of_birth: form.date_of_birth || null,
        home_station_id: form.home_station_id ? Number(form.home_station_id) : null,
        email: form.email || null,
        blood_group: form.blood_group || null,
      })
      setStage('done')
    } catch (err) {
      setError(err.message || 'Sign-up failed')
    } finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-red-dark p-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl p-6 space-y-4">
        <div className="text-center">
          <img src="/logo.svg" alt="RVNL" className="h-12 mx-auto mb-3" />
          <h1 className="text-xl font-bold text-slate-800">Create your account</h1>
          <p className="text-sm text-slate-500">Fill in your details for approval</p>
        </div>

        {error && <div className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>}

        {stage === 'details' && (
          <form onSubmit={submit} className="space-y-3">
            <input required className={inputCls} placeholder="Full name *"
              value={form.display_name} onChange={(e) => set('display_name', e.target.value)} />
            <input required className={inputCls} type="tel" placeholder="Mobile number *" autoComplete="tel"
              value={form.phone} onChange={(e) => set('phone', e.target.value)} />
            <label className="block text-xs text-slate-500">Date of birth
              <input className={inputCls} type="date"
                value={form.date_of_birth} onChange={(e) => set('date_of_birth', e.target.value)} />
            </label>

            <select required className={inputCls} value={form.department_id}
              onChange={(e) => set('department_id', e.target.value)}>
              <option value="">Select department *</option>
              {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
            {isOther(depts, form.department_id) && (
              <input className={inputCls} placeholder="Enter your department *"
                value={form.department_custom} onChange={(e) => set('department_custom', e.target.value)} />
            )}

            <select className={inputCls} value={form.designation_id}
              onChange={(e) => set('designation_id', e.target.value)}>
              <option value="">Select designation (optional)</option>
              {designations.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
            {isOther(designations, form.designation_id) && (
              <input className={inputCls} placeholder="Enter your designation *"
                value={form.designation_custom} onChange={(e) => set('designation_custom', e.target.value)} />
            )}

            <select className={inputCls} value={form.employment_type_id}
              onChange={(e) => set('employment_type_id', e.target.value)}>
              <option value="">Select employment type (optional)</option>
              {employmentTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            {isOther(employmentTypes, form.employment_type_id) && (
              <input className={inputCls} placeholder="Enter your employment type *"
                value={form.employment_type_custom} onChange={(e) => set('employment_type_custom', e.target.value)} />
            )}

            <select className={inputCls} value={form.home_station_id}
              onChange={(e) => set('home_station_id', e.target.value)}>
              <option value="">Home location (optional)</option>
              {stations.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <input className={inputCls} type="email" placeholder="Email (optional)"
              value={form.email} onChange={(e) => set('email', e.target.value)} />
            <input className={inputCls} placeholder="Blood group (optional)"
              value={form.blood_group} onChange={(e) => set('blood_group', e.target.value)} />

            <p className="text-xs text-slate-400">
              An administrator will review this and assign your employee code once approved.
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
              Thanks! Your sign-up is awaiting approval. You'll be notified once your
              account is activated.
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
