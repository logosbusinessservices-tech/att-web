import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppHeader from '../components/AppHeader.jsx'
import { api } from '../lib/api.js'

// Max files per upload — matches the backend's enroll_max_photos (default 10).
const MAX_PHOTOS = 10

export default function ReUploadPhotos({ back = '/assistant' }) {
  const navigate = useNavigate()
  const [accounts, setAccounts] = useState(null)   // null = loading
  const [query, setQuery] = useState('')
  const [picked, setPicked] = useState(null)       // {external_id, display_name, role}
  const [showList, setShowList] = useState(false)
  const [files, setFiles] = useState([])           // File[]
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(null)     // { used, submitted, name, id }
  const fileRef = useRef(null)

  // Load every active account once on mount — small enough to filter in-browser.
    useEffect(() => {
    api.eaAccounts()
      .then((rows) => setAccounts(rows.filter((a) => a.status === 'active')))
      .catch((e) => setError(e.message || 'Could not load accounts'))
  }, [])

  // Filter accounts by the search text — matches ID or name, case-insensitive.
  const matches = useMemo(() => {
    if (!accounts) return []
    const q = query.trim().toLowerCase()
    if (!q) return accounts.slice(0, 50)   // cap the list for performance
    return accounts.filter((a) =>
      (a.external_id || '').toLowerCase().includes(q)
      || (a.display_name || '').toLowerCase().includes(q)
    ).slice(0, 50)
  }, [accounts, query])

  function onPick(acc) {
    setPicked(acc)
    setQuery(`${acc.display_name} · ${acc.external_id}`)
    setShowList(false)
    setError('')
  }

  function onFilesChosen(e) {
    const chosen = Array.from(e.target.files || [])
    if (chosen.length === 0) return
    if (chosen.length > MAX_PHOTOS) {
      setError(`Please select at most ${MAX_PHOTOS} photos.`)
      return
    }
    setFiles(chosen)
    setError('')
  }

  function removeFile(index) {
    setFiles((cur) => cur.filter((_, i) => i !== index))
  }

  async function onSubmit() {
    if (!picked) { setError('Pick an employee first.'); return }
    if (files.length === 0) { setError('Add at least one photo.'); return }
    setSubmitting(true)
    setError('')
    try {
      const result = await api.reUploadEmployeePhotos(picked.external_id, files)
      setSuccess({
        used: result.photos_used,
        submitted: result.photos_submitted,
        name: result.display_name,
        id: result.external_id,
        notes: result.notes || [],
      })
    } catch (e) {
      setError(e.message || 'Upload failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  function onOk() {
    navigate(back)
  }

  const canSubmit = picked && files.length > 0 && !submitting

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="Re-upload Employee Pictures" back={back} />
      <main className="p-4 max-w-md mx-auto space-y-4">
        <p className="text-xs text-slate-500">
          Replace an employee's face template with fresh photos. The new photos
          overwrite the old template; the employee's previous photos stay
          archived. Use this when the original photos were blurry, dark, or
          taken at an unusual angle.
        </p>

        {/* Employee picker */}
        <div className="bg-white rounded-xl shadow-sm p-3 space-y-2 relative">
          <label className="text-xs font-medium text-slate-600">Employee</label>
          <input
            type="text"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setShowList(true); setPicked(null) }}
            onFocus={() => setShowList(true)}
            placeholder={accounts === null ? 'Loading accounts…' : 'Search by name or employee ID'}
            disabled={accounts === null}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
          />
          {showList && accounts !== null && matches.length > 0 && (
            <ul className="absolute left-3 right-3 top-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-64 overflow-y-auto z-10">
              {matches.map((acc) => (
                <li
                  key={acc.external_id}
                  onClick={() => onPick(acc)}
                  className="px-3 py-2 text-sm hover:bg-slate-100 cursor-pointer border-b border-slate-100 last:border-b-0"
                >
                  <div className="font-medium text-slate-800">{acc.display_name}</div>
                  <div className="text-xs text-slate-500">
                    {acc.external_id}
                    {acc.role && acc.role !== 'employee' ? ` · ${acc.role}` : ''}
                    {acc.department_name ? ` · ${acc.department_name}` : ''}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {showList && accounts !== null && matches.length === 0 && query && (
            <div className="absolute left-3 right-3 top-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg p-3 text-sm text-slate-500 z-10">
              No matches.
            </div>
          )}
        </div>

        {/* Photo picker */}
        <div className="bg-white rounded-xl shadow-sm p-3 space-y-2">
          <label className="text-xs font-medium text-slate-600">Photos</label>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            capture="user"
            onChange={onFilesChosen}
            className="hidden"
            id="photo-input"
          />
          <label
            htmlFor="photo-input"
            className="block w-full text-center py-3 rounded-lg bg-slate-100 text-slate-700 text-sm font-medium cursor-pointer hover:bg-slate-200"
          >
            📷 Take or choose photos
          </label>
          <p className="text-[11px] text-slate-400">
            Up to {MAX_PHOTOS} photos. Clear, front-facing shots work best.
          </p>
          {files.length > 0 && (
            <ul className="space-y-1 pt-1">
              {files.map((f, i) => (
                <li key={i} className="flex items-center justify-between text-xs text-slate-600 bg-slate-50 rounded px-2 py-1">
                  <span className="truncate">{f.name}</span>
                  <button
                    onClick={() => removeFile(i)}
                    className="text-slate-400 hover:text-red-600 text-lg leading-none px-1"
                    aria-label="Remove"
                  >×</button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <button
          onClick={onSubmit}
          disabled={!canSubmit}
          className={`w-full py-3 rounded-lg font-medium text-white ${
            canSubmit ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-slate-300 cursor-not-allowed'
          }`}
        >
          {submitting ? 'Re-uploading…' : 'Submit'}
        </button>

        {/* Success overlay. Shown when upload succeeded. */}
        {success && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl p-6 max-w-sm w-full space-y-3 text-center">
              <div className="text-5xl">✓</div>
              <p className="font-semibold text-slate-800">Re-upload succeeded</p>
              <p className="text-sm text-slate-600">
                {success.name} ({success.id}) — {success.used} of {success.submitted} photos used.
              </p>
              {success.notes.length > 0 && (
                <ul className="text-[11px] text-slate-400 text-left space-y-0.5">
                  {success.notes.map((n, i) => <li key={i}>• {n}</li>)}
                </ul>
              )}
              <button
                onClick={onOk}
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