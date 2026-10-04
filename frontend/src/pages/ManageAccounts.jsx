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

function isOther(list, id) {
  const sel = list.find((x) => String(x.id) === String(id))
  return !!(sel && sel.is_other)
}

// EA super-admin console: manage any account across all departments, including
// promoting an employee to departmental supervisor.
export default function ManageAccounts({ back = '/assistant' }) {
  const [people, setPeople] = useState([])
  const [opts, setOpts] = useState({ departments: [], stations: [], designations: [], employment_types: [] })
  const [sups, setSups] = useState([])
  const [q, setQ] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')
  const [edit, setEdit] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  function loadList() {
    api.eaAccounts(roleFilter).then(setPeople).catch((e) => setError(e.message))
  }

  useEffect(() => { loadList() }, [roleFilter]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    api.eaRefOptions().then(setOpts).catch(() => {})
    api.eaSupervisors().then(setSups).catch(() => {})
  }, [])

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase()
    return people.filter((p) => !s || p.display_name.toLowerCase().includes(s) || p.external_id.toLowerCase().includes(s))
  }, [people, q])

  async function open(ext) {
    setError(''); setMsg('')
    try { setEdit(await api.eaAccount(ext)) } catch (e) { setError(e.message) }
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
        date_of_birth: edit.date_of_birth || null,
        role: edit.role,
        department_id: edit.department_id ? Number(edit.department_id) : null,
        department_custom: isOther(opts.departments, edit.department_id) ? edit.department_custom : null,
        designation_id: edit.designation_id ? Number(edit.designation_id) : null,
        designation_custom: isOther(opts.designations, edit.designation_id) ? edit.designation_custom : null,
        employment_type_id: edit.employment_type_id ? Number(edit.employment_type_id) : null,
        employment_type_custom: isOther(opts.employment_types, edit.employment_type_id) ? edit.employment_type_custom : null,
        manager_id: edit.manager_id ? Number(edit.manager_id) : null,
        home_station_id: edit.home_station_id ? Number(edit.home_station_id) : null,
        field_scan_enabled: edit.field_scan_enabled,
      }
      const updated = await api.eaUpdateAccount(edit.external_id, patch)
      setEdit(updated)
      setMsg('Saved.')
      loadList()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="Manage Accounts" back={back} />
      <main className="p-4 max-w-md mx-auto space-y-4">
        {error && <p className="text-red-600 text-sm">{error}</p>}

        {!edit ? (
          <>
            <input value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Search by name or employee code…"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white" />
            <div className="flex gap-1 text-xs">
              {['all', 'employee', 'supervisor'].map((r) => (
                <button key={r} onClick={() => setRoleFilter(r)}
                  className={`flex-1 py-1.5 rounded-lg capitalize ${roleFilter === r ? 'bg-slate-900 text-white' : 'bg-white text-slate-600 border border-slate-200'}`}>
                  {r === 'all' ? 'All' : r}
                </button>
              ))}
            </div>
            <div className="bg-white rounded-xl shadow-sm divide-y divide-slate-100">
              {filtered.map((p) => (
                <button key={p.external_id} onClick={() => open(p.external_id)}
                  className="w-full text-left px-3 py-2.5 hover:bg-slate-50">
                  <div className="text-sm font-medium text-slate-800">{p.display_name}
                    <span className="ml-2 text-[10px] uppercase text-slate-400">{p.role}</span>
                  </div>
                  <div className="text-xs text-slate-400">{p.external_id}{p.department_name ? ` · ${p.department_custom || p.department_name}` : ''}</div>
                </button>
              ))}
              {filtered.length === 0 && <div className="px-3 py-6 text-center text-slate-400 text-sm">No accounts.</div>}
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
              <div className="grid grid-cols-2 gap-2">
                <Field label="Email">
                  <input className={inputCls} type="email" value={edit.email || ''} onChange={(e) => set('email', e.target.value)} />
                </Field>
                <Field label="Date of birth">
                  <input className={inputCls} type="date" value={edit.date_of_birth || ''} onChange={(e) => set('date_of_birth', e.target.value)} />
                </Field>
              </div>

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
                    {opts.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                  </select>
                </Field>
              </div>
              {isOther(opts.departments, edit.department_id) && (
                <Field label="Department (custom)">
                  <input className={inputCls} value={edit.department_custom || ''} onChange={(e) => set('department_custom', e.target.value)} />
                </Field>
              )}

              <Field label="Designation">
                <select className={inputCls} value={edit.designation_id ?? ''} onChange={(e) => set('designation_id', e.target.value)}>
                  <option value="">—</option>
                  {opts.designations.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </Field>
              {isOther(opts.designations, edit.designation_id) && (
                <Field label="Designation (custom)">
                  <input className={inputCls} value={edit.designation_custom || ''} onChange={(e) => set('designation_custom', e.target.value)} />
                </Field>
              )}

              <Field label="Employment type">
                <select className={inputCls} value={edit.employment_type_id ?? ''} onChange={(e) => set('employment_type_id', e.target.value)}>
                  <option value="">—</option>
                  {opts.employment_types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </Field>
              {isOther(opts.employment_types, edit.employment_type_id) && (
                <Field label="Employment type (custom)">
                  <input className={inputCls} value={edit.employment_type_custom || ''} onChange={(e) => set('employment_type_custom', e.target.value)} />
                </Field>
              )}

              <Field label="Reporting supervisor">
                <select className={inputCls} value={edit.manager_id ?? ''} onChange={(e) => set('manager_id', e.target.value)}>
                  <option value="">—</option>
                  {sups.map((s) => <option key={s.id} value={s.id}>{s.display_name} ({s.external_id})</option>)}
                </select>
              </Field>
              <Field label="Home location">
                <select className={inputCls} value={edit.home_station_id ?? ''} onChange={(e) => set('home_station_id', e.target.value)}>
                  <option value="">—</option>
                  {opts.stations.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
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
