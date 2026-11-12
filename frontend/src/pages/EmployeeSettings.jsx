import { useEffect, useMemo, useState } from 'react'
import AppHeader from '../components/AppHeader.jsx'
import { api } from '../lib/api.js'
import { useAuth } from '../lib/auth.jsx'

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
  const { user } = useAuth()
  const isSuperAdmin = user?.external_id === 'EA001'
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

    // Phase 10: EA001 super-admin only — reset password to default (= employee code).
  const [resetConfirm, setResetConfirm] = useState(false)  // showing confirmation popup?
  const [resetResult, setResetResult] = useState(null)     // success popup state

    // Phase 11: EA001 super-admin only — remove employee (soft delete).
  const [removeConfirm, setRemoveConfirm] = useState(false)
  const [removeResult, setRemoveResult] = useState(null)
    // Phase 12: EA001 super-admin only — discard account (hard delete).
  const [discardStep, setDiscardStep] = useState(null)  // null | 'preview' | 'typing' | 'done'
  const [discardPreview, setDiscardPreview] = useState(null)  // counts from backend
  const [discardConfirm, setDiscardConfirm] = useState('')    // what EA typed
  const [discardResult, setDiscardResult] = useState(null)    // success result


  async function doReset() {
    setBusy(true); setError(''); setMsg('')
    try {
      const result = await api.eaResetPassword(edit.external_id)
      setResetResult(result)
      setResetConfirm(false)
    } catch (e) {
      setError(e.message)
      setResetConfirm(false)
    } finally {
      setBusy(false)
    }
  }

    async function doRemove() {
    setBusy(true); setError(''); setMsg('')
    try {
      const result = await api.eaRemoveAccount(edit.external_id)
      setRemoveResult(result)
      setRemoveConfirm(false)
    } catch (e) {
      setError(e.message)
      setRemoveConfirm(false)
    } finally {
      setBusy(false)
    }
  }

    // Phase 12: fetch the count preview, then show the typing step.
  async function startDiscard() {
    setBusy(true); setError(''); setMsg('')
    try {
      const preview = await api.eaDiscardPreview(edit.external_id)
      setDiscardPreview(preview)
      setDiscardStep('typing')
      setDiscardConfirm('')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function doDiscard() {
    setBusy(true); setError(''); setMsg('')
    try {
      const result = await api.eaDiscardAccount(edit.external_id, discardConfirm)
      setDiscardResult(result)
      setDiscardStep(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  function cancelDiscard() {
    setDiscardStep(null)
    setDiscardPreview(null)
    setDiscardConfirm('')
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

                            {isSuperAdmin && (
                <div className="pt-3 mt-3 border-t border-slate-100 space-y-3">
                  {/* Reset password */}
                  <div>
                    <button
                      onClick={() => setResetConfirm(true)}
                      disabled={busy}
                      className="w-full bg-amber-600 hover:bg-amber-700 text-white rounded-lg py-2.5 text-sm font-medium disabled:opacity-50"
                    >
                      Reset Password to Default
                    </button>
                    <p className="text-[11px] text-slate-400 mt-1 text-center">
                      Super admin only. Resets to the employee code; user must change on next login.
                    </p>
                  </div>

                  {/* Remove employee */}
                  <div>
                    <button
                      onClick={() => setRemoveConfirm(true)}
                      disabled={busy}
                      className="w-full bg-red-600 hover:bg-red-700 text-white rounded-lg py-2.5 text-sm font-medium disabled:opacity-50"
                    >
                      Remove Employee
                    </button>
                    <p className="text-[11px] text-slate-400 mt-1 text-center">
                      Use this when the employee has left the company. Their past attendance stays in reports.
                    </p>
                  </div>

                                    {/* Discard account — hard delete */}
                  <div>
                    <button
                      onClick={startDiscard}
                      disabled={busy}
                      className="w-full bg-slate-900 hover:bg-black text-white rounded-lg py-2.5 text-sm font-medium disabled:opacity-50 border-2 border-red-700"
                    >
                      Discard Account
                    </button>
                    <p className="text-[11px] text-slate-400 mt-1 text-center">
                      ⚠️ Use ONLY if the account was created by mistake. All data is permanently deleted.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Reset confirmation popup. */}
        {resetConfirm && edit && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl p-6 max-w-sm w-full space-y-3">
              <p className="font-semibold text-slate-800 text-center">Reset password?</p>
              <p className="text-sm text-slate-600 text-center">
                This will reset <span className="font-semibold">{edit.display_name}</span>'s
                password to their employee code (<span className="font-mono">{edit.external_id}</span>).
                They will be required to change it on next login.
              </p>
              <div className="flex gap-2 pt-2">
                <button
                  onClick={() => setResetConfirm(false)}
                  disabled={busy}
                  className="flex-1 bg-slate-100 text-slate-800 rounded-lg py-2.5 text-sm font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={doReset}
                  disabled={busy}
                  className="flex-1 bg-amber-600 hover:bg-amber-700 text-white rounded-lg py-2.5 text-sm font-medium disabled:opacity-50"
                >
                  {busy ? 'Resetting…' : 'Reset'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Success popup. */}
        {resetResult && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl p-6 max-w-sm w-full space-y-3 text-center">
              <div className="text-5xl">✓</div>
              <p className="font-semibold text-slate-800">Password reset</p>
              <p className="text-sm text-slate-600">
                {resetResult.display_name}'s password is now their employee code:
              </p>
              <p className="font-mono text-base bg-slate-100 rounded-lg py-2 text-slate-800">
                {resetResult.default_password}
              </p>
              <p className="text-xs text-slate-500">
                Share this with them. They'll be asked to change it on next login.
              </p>
              <button
                onClick={() => setResetResult(null)}
                className="w-full bg-slate-900 text-white rounded-lg py-3 font-medium"
              >
                OK
              </button>
            </div>
          </div>
        )}
                {/* Remove employee confirmation. */}
        {removeConfirm && edit && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl p-6 max-w-sm w-full space-y-3">
              <div className="text-center text-4xl">⚠️</div>
              <p className="font-semibold text-slate-800 text-center">Remove this employee?</p>
              <div className="text-sm text-slate-600 space-y-2">
                <p>
                  <span className="font-semibold">{edit.display_name}</span> ({edit.external_id})
                  will be removed from the system.
                </p>
                <ul className="text-xs space-y-1 list-disc list-inside text-slate-500">
                  <li>They won't be able to log in</li>
                  <li>They won't appear in supervisor or EA lists</li>
                  <li>Cameras will stop recognizing them</li>
                  <li>Their past attendance stays visible in historical reports</li>
                </ul>
                <p className="text-xs text-slate-500 pt-1">
                  Use this when someone has left the company. If the account was created by mistake
                  and has no real attendance data, use <span className="font-semibold">Discard Account</span> instead
                  (coming soon).
                </p>
              </div>
              <div className="flex gap-2 pt-2">
                <button
                  onClick={() => setRemoveConfirm(false)}
                  disabled={busy}
                  className="flex-1 bg-slate-100 text-slate-800 rounded-lg py-2.5 text-sm font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={doRemove}
                  disabled={busy}
                  className="flex-1 bg-red-600 hover:bg-red-700 text-white rounded-lg py-2.5 text-sm font-medium disabled:opacity-50"
                >
                  {busy ? 'Removing…' : 'Remove'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Remove employee success popup. */}
        {removeResult && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl p-6 max-w-sm w-full space-y-3 text-center">
              <div className="text-5xl">✓</div>
              <p className="font-semibold text-slate-800">Employee removed</p>
              <p className="text-sm text-slate-600">
                {removeResult.display_name} ({removeResult.external_id}) is no longer active.
                Their past attendance remains visible in historical reports.
              </p>
              <button
                onClick={() => { setRemoveResult(null); setEdit(null) }}
                className="w-full bg-slate-900 text-white rounded-lg py-3 font-medium"
              >
                OK
              </button>
            </div>
          </div>
        )}
                {/* Discard Account typing-confirmation popup. */}
        {discardStep === 'typing' && discardPreview && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl p-6 max-w-sm w-full space-y-3">
              <div className="text-center text-4xl">🗑️</div>
              <p className="font-semibold text-slate-800 text-center">Discard this account?</p>
              <div className="text-sm text-slate-600 space-y-2">
                <p>
                  <span className="font-semibold">{discardPreview.display_name}</span> ({discardPreview.external_id})
                  will be <span className="font-semibold text-red-700">permanently deleted</span>.
                </p>
                <p className="text-xs">This will erase:</p>
                                <ul className="text-xs space-y-1 list-disc list-inside text-slate-500 bg-red-50 border border-red-100 rounded p-2">
                  <li>{discardPreview.attendance_events} attendance event{discardPreview.attendance_events === 1 ? '' : 's'}</li>
                  <li>{discardPreview.corrections} supervisor correction{discardPreview.corrections === 1 ? '' : 's'}</li>
                  <li>{discardPreview.disputes} dispute{discardPreview.disputes === 1 ? '' : 's'}</li>
                  <li>{discardPreview.leave_requests} leave request{discardPreview.leave_requests === 1 ? '' : 's'}</li>
                  <li>{discardPreview.delegated_tasks} delegated task{discardPreview.delegated_tasks === 1 ? '' : 's'}</li>
                  <li>{discardPreview.notifications} notification{discardPreview.notifications === 1 ? '' : 's'}</li>
                  <li>The employee's face template</li>
                  <li>The account itself</li>
                </ul>
                <p className="text-xs text-red-700 font-semibold pt-1">
                  This cannot be undone.
                </p>
                {discardPreview.attendance_events > 0 && (
                  <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
                    This account has real attendance data. If the employee has actually
                    left the company, use <span className="font-semibold">Remove Employee</span> instead
                    to keep history visible.
                  </p>
                )}
                <p className="text-xs pt-2">
                  To confirm, type <span className="font-mono font-semibold">DELETE</span> below:
                </p>
                <input
                  type="text"
                  value={discardConfirm}
                  onChange={(e) => setDiscardConfirm(e.target.value)}
                  placeholder="Type DELETE"
                  autoFocus
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm font-mono"
                />
              </div>
              <div className="flex gap-2 pt-2">
                <button
                  onClick={cancelDiscard}
                  disabled={busy}
                  className="flex-1 bg-slate-100 text-slate-800 rounded-lg py-2.5 text-sm font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={doDiscard}
                  disabled={busy || discardConfirm !== 'DELETE'}
                  className="flex-1 bg-red-700 hover:bg-red-800 text-white rounded-lg py-2.5 text-sm font-medium disabled:opacity-40"
                >
                  {busy ? 'Discarding…' : 'Discard forever'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Discard success popup. */}
        {discardResult && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl p-6 max-w-sm w-full space-y-3 text-center">
              <div className="text-5xl">🗑️</div>
              <p className="font-semibold text-slate-800">Account discarded</p>
              <p className="text-sm text-slate-600">
                {discardResult.display_name} ({discardResult.external_id}) and all their data
                have been permanently deleted.
              </p>
              <ul className="text-xs text-slate-500 text-left bg-slate-50 rounded p-2 space-y-0.5">
                <li>• {discardResult.attendance_events_deleted} attendance events</li>
                <li>• {discardResult.corrections_deleted} supervisor corrections</li>
                <li>• {discardResult.disputes_deleted} disputes</li>
                <li>• {discardResult.leave_requests_deleted} leave requests</li>
                <li>• {discardResult.delegated_tasks_deleted} delegated tasks</li>
                <li>• {discardResult.notifications_deleted} notifications</li>
              </ul>
              <button
                onClick={() => { setDiscardResult(null); setDiscardPreview(null); setEdit(null) }}
                className="w-full bg-slate-900 text-white rounded-lg py-3 font-medium"
              >
                OK
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
