import { useEffect, useRef, useState } from 'react'
import AppHeader from '../components/AppHeader.jsx'
import { api } from '../lib/api.js'

// Onboarding worklist. Each new hire needs two steps, doable at separate times:
//   1) Approve & assign employee number   2) Onboard attendance photos
// Cards are light green; they turn light red once 3 days pass since the request
// without both steps done. An item drops off when approved AND enrolled.
const DAY = 86400000

export default function SignupApprovals({ back = '/assistant' }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')

  function load() {
    setError('')
    api.pendingSignups().then(setRows).catch((e) => setError(e.message))
  }
  useEffect(load, [])

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="Approve Sign-ups" back={back} />
      <main className="p-4 max-w-md mx-auto space-y-3">
        {error && <p className="text-red-600 text-sm">{error}</p>}

        {rows === null ? (
          <p className="text-center text-slate-400 py-8">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="text-center text-slate-500 py-10">
            <div className="text-4xl mb-2">✓</div>
            <p className="text-sm">No employees waiting to be onboarded.</p>
          </div>
        ) : (
          rows.map((s) => <SignupCard key={s.id} s={s} onChange={load} setError={setError} />)
        )}
      </main>
    </div>
  )
}

function SignupCard({ s, onChange, setError }) {
  const [mode, setMode] = useState(null)   // null | 'approve' | 'photos'
  const [code, setCode] = useState('')
  const [fieldScan, setFieldScan] = useState(false)
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)

  const overdue = (!s.is_approved || !s.is_enrolled)
    && Date.now() - new Date(s.created_at).getTime() > 3 * DAY
  const tone = overdue ? 'bg-red-50 border-red-200' : 'bg-emerald-50 border-emerald-200'

  async function approve() {
    if (!code.trim()) { setError('Assign an employee code.'); return }
    setBusy(true); setError('')
    try {
      await api.approveSignup(s.id, { external_id: code.trim(), field_scan_enabled: fieldScan })
      setMode(null); onChange()
    } catch (e) {
      setError(e.message || 'Could not approve')
    } finally { setBusy(false) }
  }

  async function reject() {
    const reason = window.prompt(`Reject ${s.display_name}'s sign-up? Optional reason:`)
    if (reason === null) return
    setBusy(true); setError('')
    try {
      await api.rejectSignup(s.id, reason || null)
      onChange()
    } catch (e) {
      setError(e.message || 'Could not reject')
    } finally { setBusy(false) }
  }

  async function uploadPhotos() {
    if (files.length === 0) { setError('Add at least one photo.'); return }
    setBusy(true); setError('')
    try {
      await api.onboardSignupPhotos(s.id, files)
      setFiles([]); setMode(null); onChange()
    } catch (e) {
      setError(e.message || 'Could not upload photos')
    } finally { setBusy(false) }
  }

  function pick(e) {
    const picked = Array.from(e.target.files || [])
    setFiles((prev) => [...prev, ...picked].slice(0, 10))
    e.target.value = ''
  }

  return (
    <div className={`border rounded-xl p-3 ${tone}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-medium text-slate-800">{s.display_name}</div>
          <div className="text-xs text-slate-500 mt-0.5 space-y-0.5">
            <div>📱 {s.phone || '—'}{s.email ? ` · ✉️ ${s.email}` : ''}</div>
            <div>{s.department_name || '—'}{s.home_station_name ? ` · ${s.home_station_name}` : ''}{s.blood_group ? ` · ${s.blood_group}` : ''}</div>
          </div>
        </div>
        {overdue && <span className="shrink-0 text-[10px] font-semibold uppercase text-red-700 bg-red-100 rounded px-1.5 py-0.5">Overdue</span>}
      </div>

      {/* Step progress chips */}
      <div className="flex gap-2 mt-2 text-[11px]">
        <span className={`rounded-full px-2 py-0.5 ${s.is_approved ? 'bg-emerald-600 text-white' : 'bg-white text-slate-500 border border-slate-200'}`}>
          {s.is_approved ? `✓ ${s.external_id}` : '1 · Not approved'}
        </span>
        <span className={`rounded-full px-2 py-0.5 ${s.is_enrolled ? 'bg-emerald-600 text-white' : 'bg-white text-slate-500 border border-slate-200'}`}>
          {s.is_enrolled ? '✓ Photos added' : '2 · No photos'}
        </span>
      </div>

      {/* Step 1: approve & assign */}
      {mode === 'approve' && (
        <div className="mt-3 space-y-2 border-t border-black/5 pt-3">
          <input className={inputCls} placeholder="Assign employee code (e.g. EMP010)"
            value={code} onChange={(e) => setCode(e.target.value)} />
          <label className="flex items-center justify-between py-1">
            <span className="text-xs font-medium text-slate-500">Allow field attendance (face + GPS)</span>
            <input type="checkbox" className="w-5 h-5 accent-emerald-600"
              checked={fieldScan} onChange={(e) => setFieldScan(e.target.checked)} />
          </label>
          <div className="flex gap-2">
            <button disabled={busy} onClick={approve}
              className="flex-1 bg-brand-red text-white rounded-lg py-2 text-sm font-medium disabled:opacity-50">
              {busy ? 'Approving…' : 'Approve & activate'}
            </button>
            <button onClick={() => setMode(null)}
              className="px-3 bg-slate-200 text-slate-700 rounded-lg py-2 text-sm">Cancel</button>
          </div>
          <p className="text-[11px] text-slate-400">Default password is the employee code; they'll be asked to change it.</p>
        </div>
      )}

      {/* Step 2: photos */}
      {mode === 'photos' && (
        <div className="mt-3 space-y-2 border-t border-black/5 pt-3">
          {files.length > 0 && (
            <div className="grid grid-cols-4 gap-1.5">
              {files.map((f, i) => (
                <div key={i} className="relative aspect-square rounded-lg overflow-hidden border border-slate-200">
                  <img src={URL.createObjectURL(f)} alt="" className="w-full h-full object-cover" />
                  <button onClick={() => setFiles((p) => p.filter((_, j) => j !== i))}
                    className="absolute top-0.5 right-0.5 bg-black/60 text-white rounded-full w-4 h-4 text-[10px] leading-none">×</button>
                </div>
              ))}
            </div>
          )}
          <div className="grid grid-cols-2 gap-2">
            <label className="cursor-pointer text-center bg-slate-900 text-white rounded-lg py-2 text-sm font-medium">
              Take photo
              <input type="file" accept="image/*" capture="user" multiple className="hidden" onChange={pick} />
            </label>
            <label className="cursor-pointer text-center bg-slate-200 text-slate-700 rounded-lg py-2 text-sm font-medium">
              Choose files
              <input type="file" accept="image/*" multiple className="hidden" onChange={pick} />
            </label>
          </div>
          <div className="flex gap-2">
            <button disabled={busy || files.length === 0} onClick={uploadPhotos}
              className="flex-1 bg-brand-red text-white rounded-lg py-2 text-sm font-medium disabled:opacity-50">
              {busy ? 'Uploading…' : `Onboard ${files.length || ''} photo${files.length === 1 ? '' : 's'}`}
            </button>
            <button onClick={() => { setMode(null); setFiles([]) }}
              className="px-3 bg-slate-200 text-slate-700 rounded-lg py-2 text-sm">Cancel</button>
          </div>
        </div>
      )}

      {/* Action buttons */}
      {mode === null && (
        <div className="flex flex-wrap gap-2 mt-3">
          {!s.is_approved ? (
            <>
              <button onClick={() => { setCode(''); setFieldScan(s.field_scan_enabled); setMode('approve') }}
                className="flex-1 bg-brand-red text-white rounded-lg py-2 text-sm font-medium">
                Approve &amp; assign #
              </button>
              <button disabled={busy} onClick={reject}
                className="px-3 bg-white text-red-700 border border-red-200 rounded-lg py-2 text-sm font-medium disabled:opacity-50">Reject</button>
            </>
          ) : (
            <span className="flex-1 text-center bg-white/60 text-emerald-700 rounded-lg py-2 text-sm font-medium">Approved · {s.external_id}</span>
          )}
          <button onClick={() => setMode('photos')}
            className={`flex-1 rounded-lg py-2 text-sm font-medium ${s.is_enrolled ? 'bg-white/60 text-emerald-700' : 'bg-slate-900 text-white'}`}>
            {s.is_enrolled ? 'Re-upload photos' : 'Onboard photos'}
          </button>
        </div>
      )}
    </div>
  )
}

const inputCls = 'w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white'
