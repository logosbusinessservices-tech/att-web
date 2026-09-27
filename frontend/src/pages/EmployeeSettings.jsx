import { useEffect, useMemo, useState } from 'react'
import AppHeader from '../components/AppHeader.jsx'
import { api } from '../lib/api.js'

function Toggle({ on, onChange, disabled }) {
  return (
    <button
      onClick={() => onChange(!on)}
      disabled={disabled}
      className={`w-11 h-6 rounded-full transition-colors relative ${on ? 'bg-emerald-600' : 'bg-slate-300'} disabled:opacity-50`}
    >
      <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all ${on ? 'left-[22px]' : 'left-0.5'}`} />
    </button>
  )
}

const inputCls = 'mt-1 w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm bg-white'

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-slate-500">{label}</span>
      {children}
    </label>
  )
}

export default function EmployeeSettings({ back = '/supervisor' }) {
  const [people, setPeople] = useState([])
  const [depts, setDepts] = useState([])
  const [sups, setSups] = useState([])
  const [stations, setStations] = useState([])
  const [q, setQ] = useState('')
  const [edit, setEdit] = useState(null) // editable copy of settings
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    api.supervisorOverview().then(setPeople).catch((e) => setError(e.message))
    api.departments().then(setDepts).catch(() => {})
    api.supervisors().then(setSups).catch(() => {})
    api.stations().then(setStations).catch(() => {})
  }, [])

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase()
    return people.filter((p) => !s || p.display_name.toLowerCase().includes(s) || p.external_id.toLowerCase().includes(s))
  }, [people, q])

  async function open(ext) {
    setError(''); setMsg('')
    try { setEdit(await api.getEmployeeSettings(ext)) } catch (e) { setError(e.message) }
  }

  function set(k, v) { setEdit((s) => ({ ...s, [k]: v })) }

  async function save() {
    setBusy(true); setError(''); setMsg('')
    try {
      const patch = {
        display_name: edit.display_name,
        phone: edit.phone,
        email: edit.email,
        blood_group: edit.blood_group,
        role: edit.role,
        department_id: edit.department_id ? Number(edit.department_id) : null,
        manager_id: edit.manager_id ? Number(edit.manager_id) : null,
        home_station_id: edit.home_station_id ? Number(edit.home_station_id) : null,
        field_scan_enabled: edit.field_scan_enabled,
      }
      const updated = await api.updateEmployeeSettings(edit.external_id, patch)
      setEdit(updated)
      setMsg('Saved.')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="Employee Settings" back={back} />
      <main className="p-4 max-w-md mx-auto space-y-4">
        {error && <p className="text-red-600 text-sm">{error}</p>}

        {!edit ? (
          <>
            <input value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Search employee by name or code…"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white" />
            <div className="bg-white rounded-xl shadow-sm divide-y divide-slate-100">
              {filtered.map((p) => (
                <button key={p.external_id} onClick={() => open(p.external_id)}
                  className="w-full text-left px-3 py-2.5 hover:bg-slate-50">
                  <div className="text-sm font-medium text-slate-800">{p.display_name}</div>
                  <div className="text-xs text-slate-400">{p.external_id}{p.department_name ? ` · ${p.department_name}` : ''}</div>
                </button>
              ))}
              {filtered.length === 0 && <div className="px-3 py-6 text-center text-slate-400 text-sm">No employees.</div>}
            </div>
          </>
        ) : (
          <div className="space-y-3">
            <button onClick={() => setEdit(null)} className="text-xs text-slate-500 underline">‹ back to list</button>
            <div className="bg-white rounded-xl shadow-sm p-4 space-y-3">
              <div className="text-xs text-slate-400">{edit.external_id}</div>

              <Field label="Full name">
                <input className={inputCls} value={edit.display_name || ''} onChange={(e) => set('display_name', e.target.value)} />
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Phone">
                  <input className={inputCls} value={edit.phone || ''} onChange={(e) => set('phone', e.target.value)} />
                </Field>
                <Field label="Blood group">
                  <input className={inputCls} value={edit.blood_group || ''} onChange={(e) => set('blood_group', e.target.value)} />
                </Field>
              </div>
              <Field label="Email">
                <input className={inputCls} type="email" value={edit.email || ''} onChange={(e) => set('email', e.target.value)} />
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Role">
                  <select className={inputCls} value={edit.role} onChange={(e) => set('role', e.target.value)}>
                    <option value="employee">Employee</option>
                    <option value="supervisor">Supervisor</option>
                  </select>
                </Field>
                <Field label="Department">
                  <select className={inputCls} value={edit.department_id ?? ''} onChange={(e) => set('department_id', e.target.value)}>
                    <option value="">—</option>
                    {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                  </select>
                </Field>
              </div>
              <Field label="Reporting supervisor">
                <select className={inputCls} value={edit.manager_id ?? ''} onChange={(e) => set('manager_id', e.target.value)}>
                  <option value="">—</option>
                  {sups.map((s) => <option key={s.id} value={s.id}>{s.display_name} ({s.external_id})</option>)}
                </select>
              </Field>
              <Field label="Home station">
                <select className={inputCls} value={edit.home_station_id ?? ''} onChange={(e) => set('home_station_id', e.target.value)}>
                  <option value="">—</option>
                  {stations.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </Field>

              <div className="flex items-center justify-between pt-1 border-t border-slate-100">
                <div>
                  <div className="text-sm font-medium text-slate-800">Field attendance</div>
                  <div className="text-xs text-slate-500">Allow face + GPS check-in.</div>
                </div>
                <Toggle on={edit.field_scan_enabled} disabled={busy} onChange={(v) => set('field_scan_enabled', v)} />
              </div>

              {msg && <p className="text-xs text-emerald-700">{msg}</p>}
              <button onClick={save} disabled={busy}
                className="w-full bg-slate-900 text-white rounded-lg py-2.5 text-sm font-medium disabled:opacity-50">
                {busy ? 'Saving…' : 'Save changes'}
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
