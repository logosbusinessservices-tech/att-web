import AppHeader from '../components/AppHeader.jsx'
import AuthImage from '../components/AuthImage.jsx'
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth.jsx'
import { api } from '../lib/api.js'

function Row({ label, value }) {
  return (
    <div className="flex justify-between py-2.5 border-b border-slate-100 last:border-0">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-sm font-medium text-slate-800 text-right">{value ?? '—'}</span>
    </div>
  )
}

// A profile row the employee can fill in / edit themselves. Blank fields show an
// "Add" affordance so optional details aren't left permanently empty.
function EditableRow({ label, value, field, type = 'text', onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function save() {
    setBusy(true); setError('')
    try {
      await onSave(field, draft)
      setEditing(false)
    } catch (e) {
      setError(e.message || 'Could not save')
    } finally { setBusy(false) }
  }

  return (
    <div className="py-2.5 border-b border-slate-100 last:border-0">
      <div className="flex justify-between items-center gap-2">
        <span className="text-sm text-slate-500">{label}</span>
        {editing ? (
          <div className="flex items-center gap-1.5">
            <input
              type={type} value={draft} autoFocus
              onChange={(e) => setDraft(e.target.value)}
              className="w-40 border border-slate-300 rounded-lg px-2 py-1 text-sm text-right"
            />
            <button onClick={save} disabled={busy}
              className="text-xs bg-brand-green text-brand-charcoal font-medium px-2 py-1 rounded-lg disabled:opacity-50">
              {busy ? '…' : 'Save'}
            </button>
            <button onClick={() => { setEditing(false); setDraft(value ?? ''); setError('') }}
              className="text-xs text-slate-400 px-1">✕</button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-800 text-right">{value || '—'}</span>
            <button onClick={() => { setDraft(value ?? ''); setEditing(true) }}
              className="text-xs text-brand-red font-medium underline">
              {value ? 'Edit' : 'Add'}
            </button>
          </div>
        )}
      </div>
      {error && <p className="text-[11px] text-red-600 text-right mt-1">{error}</p>}
    </div>
  )
}

export default function Profile({ back = '/employee' }) {
  const { user, refreshUser } = useAuth()
  const navigate = useNavigate()
  const fileRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // Cache-bust so a freshly uploaded avatar shows immediately.
  const [ver, setVer] = useState(0)
  const base = user?.role === 'supervisor' || user?.role === 'chief' ? '/supervisor'
    : user?.role === 'assistant' ? '/assistant'
    : '/employee'
  const roleLabel = user?.role === 'assistant' ? 'Executive Assistant'
    : user?.role === 'chief' ? 'Chief Manager'
    : user?.role
  const initials = user?.display_name?.split(' ').map((s) => s[0]).slice(0, 2).join('')
  const avatarSrc = user?.avatar_url ? `${api.avatarUrl(user.external_id)}?v=${ver}` : null

  async function saveField(field, value) {
    await api.updateProfile({ [field]: value })
    await refreshUser?.()
  }

  async function onPick(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setError(''); setBusy(true)
    try {
      await api.uploadAvatar(file)
      await refreshUser?.()
      setVer((v) => v + 1)
    } catch (err) {
      setError(err.message || 'Could not upload photo')
    } finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="My Profile" back={back} />
      <main className="p-4 max-w-md mx-auto">
        <div className="flex flex-col items-center py-6">
          <div className="w-20 h-20 rounded-full overflow-hidden bg-slate-900 text-white flex items-center justify-center text-2xl font-semibold">
            {avatarSrc
              ? <AuthImage src={avatarSrc} alt="" className="w-full h-full object-cover" fallback={initials} />
              : initials}
          </div>
          <button onClick={() => fileRef.current?.click()} disabled={busy}
            className="mt-2 text-xs text-slate-500 underline disabled:opacity-50">
            {busy ? 'Uploading…' : (avatarSrc ? 'Change photo' : 'Add a photo')}
          </button>
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onPick} />
          {error && <p className="text-xs text-red-600 mt-1">{error}</p>}
          <div className="mt-2 text-lg font-semibold text-slate-800">{user?.display_name}</div>
          <div className="text-sm text-slate-500 capitalize">{roleLabel}</div>
        </div>

        <div className="bg-white rounded-xl shadow-sm p-4">
          <Row label="Employee code" value={user?.external_id} />
          <Row label="Role" value={roleLabel} />
          {user?.role === 'assistant' && (
            <Row label="Supervisor" value={user?.manager_name} />
          )}
          <EditableRow label="Email" field="email" type="email" value={user?.email} onSave={saveField} />
          <EditableRow label="Phone" field="phone" type="tel" value={user?.phone} onSave={saveField} />
          <EditableRow label="Blood group" field="blood_group" value={user?.blood_group} onSave={saveField} />
          <Row label="Department" value={user?.department_name} />
          <Row label="Home station" value={user?.home_station_name} />
        </div>

        <button
          onClick={() => navigate(`${base}/change-password`)}
          className="mt-4 w-full bg-slate-900 text-white rounded-lg py-2.5 text-sm font-medium"
        >
          Change password
        </button>
      </main>
    </div>
  )
}
