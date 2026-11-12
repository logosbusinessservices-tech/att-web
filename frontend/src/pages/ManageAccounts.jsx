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

function isOther(list, id) {
  const sel = list.find((x) => String(x.id) === String(id))
  return !!(sel && sel.is_other)
}

// EA super-admin console: manage any account across all departments, including
// promoting an employee to departmental supervisor.
export default function ManageAccounts({ back = '/assistant' }) {
  const { user } = useAuth()
  const isSuperAdmin = user?.external_id === 'EA001'
  const [people, setPeople] = useState([])
  const [opts, setOpts] = useState({ departments: [], stations: [], designations: [], employment_types: [] })
  const [sups, setSups] = useState([])
  const [q, setQ] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')
  const [edit, setEdit] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  // Phase 15: Re-upload pictures.
  const [reuploadChoice, setReuploadChoice] = useState(false)  // showing camera-or-gallery popup?
  const [reuploadFiles, setReuploadFiles] = useState([])
  const [reuploadResult, setReuploadResult] = useState(null)
  

  // Phase 15: Reset password to default.
  const [resetConfirm, setResetConfirm] = useState(false)
  const [resetResult, setResetResult] = useState(null)

  // Phase 15: Remove employee (soft delete).
  const [removeConfirm, setRemoveConfirm] = useState(false)
  const [removeResult, setRemoveResult] = useState(null)

  // Phase 15: Discard account (hard delete).
  const [discardStep, setDiscardStep] = useState(null)   // null | 'typing'
  const [discardPreview, setDiscardPreview] = useState(null)
  const [discardConfirm, setDiscardConfirm] = useState('')
  const [discardResult, setDiscardResult] = useState(null)

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

    // Phase 15: Re-upload employee pictures. Replaces their face template.
  function onReuploadFilesChosen(e) {
    const chosen = Array.from(e.target.files || [])
    if (chosen.length === 0) return
    if (chosen.length > 10) {
      setError('Please select at most 10 photos.')
      return
    }
    setReuploadFiles(chosen)
    setError('')
  }

  async function doReupload() {
    if (reuploadFiles.length === 0) {
      setError('Add at least one photo.')
      return
    }
    setBusy(true); setError(''); setMsg('')
    try {
      const result = await api.reUploadEmployeePhotos(edit.external_id, reuploadFiles)
      setReuploadResult(result)
      setReuploadFiles([])
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  // Phase 15: Reset password to default (= employee code).
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

  // Phase 15: Remove employee (soft delete).
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

  // Phase 15: Discard account (hard delete) — fetch preview, then arm the typing step.
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

              {isSuperAdmin && (
                <div className="pt-3 mt-3 border-t border-slate-100 space-y-4">
                  <p className="text-[11px] text-slate-400 text-center uppercase tracking-wide">Super admin actions</p>

                  {/* Re-upload pictures */}
                  <div className="space-y-1">
                    {/* Hidden inputs — one for camera, one for gallery. */}
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      capture="user"
                      onChange={onReuploadFilesChosen}
                      className="hidden"
                      id={`reupload-camera-${edit.external_id}`}
                    />
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={onReuploadFilesChosen}
                      className="hidden"
                      id={`reupload-gallery-${edit.external_id}`}
                    />
                    <button
                      onClick={() => setReuploadChoice(true)}
                      className="block w-full text-center py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium"
                    >
                      📷 Re-upload Pictures ({reuploadFiles.length ? `${reuploadFiles.length} chosen` : 'choose photos'})
                    </button>
                    {reuploadFiles.length > 0 && (
                      <button
                        onClick={doReupload}
                        disabled={busy}
                        className="w-full bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg py-2 text-sm font-medium disabled:opacity-50"
                      >
                        {busy ? 'Uploading…' : 'Submit photos'}
                      </button>
                    )}
                    <p className="text-[11px] text-slate-400 text-center">
                      Replaces the employee's face template. Use clear, front-facing photos.
                    </p>
                  </div>

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
                      Resets to the employee code; user must change on next login.
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
                      Use this when the employee has left the company. Past attendance stays in reports.
                    </p>
                  </div>

                  {/* Discard account */}
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

                {/* Re-upload: choose camera or gallery. */}
        {reuploadChoice && edit && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl p-6 max-w-sm w-full space-y-3">
              <p className="font-semibold text-slate-800 text-center">Add pictures</p>
              <p className="text-xs text-slate-500 text-center">
                You can select multiple photos from either source.
              </p>
              <label
                htmlFor={`reupload-camera-${edit.external_id}`}
                onClick={() => setReuploadChoice(false)}
                className="block w-full text-center py-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium cursor-pointer"
              >
                📷 Take Photo
              </label>
              <label
                htmlFor={`reupload-gallery-${edit.external_id}`}
                onClick={() => setReuploadChoice(false)}
                className="block w-full text-center py-3 rounded-lg bg-slate-700 hover:bg-slate-800 text-white text-sm font-medium cursor-pointer"
              >
                🖼️ Choose from Gallery
              </label>
              <button
                onClick={() => setReuploadChoice(false)}
                className="w-full bg-slate-100 text-slate-800 rounded-lg py-2.5 text-sm font-medium"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
        
                {/* Re-upload success popup. */}
        {reuploadResult && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl p-6 max-w-sm w-full space-y-3 text-center">
              <div className="text-5xl">✓</div>
              <p className="font-semibold text-slate-800">Re-upload succeeded</p>
              <p className="text-sm text-slate-600">
                {reuploadResult.display_name} ({reuploadResult.external_id}) — {reuploadResult.photos_used} of {reuploadResult.photos_submitted} photos used.
              </p>
              {reuploadResult.notes && reuploadResult.notes.length > 0 && (
                <ul className="text-[11px] text-slate-400 text-left space-y-0.5">
                  {reuploadResult.notes.map((n, i) => <li key={i}>• {n}</li>)}
                </ul>
              )}
              <button
                onClick={() => setReuploadResult(null)}
                className="w-full bg-slate-900 text-white rounded-lg py-3 font-medium"
              >
                OK
              </button>
            </div>
          </div>
        )}

        {/* Reset password confirmation popup. */}
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

        {/* Reset password success popup. */}
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

        {/* Remove employee confirmation popup. */}
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
                onClick={() => { setRemoveResult(null); setEdit(null); loadList() }}
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
                <p className="text-xs text-red-700 font-semibold pt-1">This cannot be undone.</p>
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
              <button
                onClick={() => { setDiscardResult(null); setDiscardPreview(null); setEdit(null); loadList() }}
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
