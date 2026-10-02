import { useCallback, useEffect, useState } from 'react'
import AppHeader from '../components/AppHeader.jsx'
import AuthImage from '../components/AuthImage.jsx'
import { api } from '../lib/api.js'
import { fmtDayLabel, fmtTime } from '../lib/format.js'

function Card({ item, onDecide, selected, onToggle, onRecall }) {
  const [busy, setBusy] = useState(false)
  const km = item.distance_m != null ? (item.distance_m / 1000).toFixed(1) : null

  async function decide(kind) {
    setBusy(true)
    try { await onDecide(kind, item.event_id) } finally { setBusy(false) }
  }

  return (
    <div className={`bg-white rounded-xl shadow-sm p-3 ${item.delegated ? 'ring-1 ring-amber-300' : ''}`}>
      <div className="flex gap-3">
        <input type="checkbox" className="mt-1 w-5 h-5 accent-slate-900 shrink-0"
          checked={selected} onChange={() => onToggle(item.event_id)} disabled={item.delegated} />
        {item.selfie_url && (
          <AuthImage
            src={api.fieldSelfieUrl(item.event_id)}
            alt=""
            className="w-16 h-16 rounded-lg object-cover bg-slate-100 shrink-0"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-slate-800 flex items-center gap-2">
            {item.display_name}
            {item.delegated && (
              <span className="text-[10px] font-semibold uppercase text-amber-700 bg-amber-100 rounded px-1.5 py-0.5">Delegated</span>
            )}
          </div>
          <div className="text-xs text-slate-400">
            {item.external_id} · {fmtDayLabel(item.for_date)} · {fmtTime(item.event_time)} · {item.direction}
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {km != null && item.nearest_station_name
              ? `${km} km from ${item.nearest_station_name}`
              : 'Location unavailable'}
            {item.gps_accuracy_m != null && ` · ±${Math.round(item.gps_accuracy_m)} m`}
          </div>
        </div>
      </div>
      <div className="flex gap-2 mt-3">
        {item.delegated ? (
          <button onClick={() => onRecall(item.delegated_task_id)}
            className="flex-1 bg-amber-100 text-amber-800 text-sm py-2 rounded-lg">Recall from EA</button>
        ) : (
          <>
            <button onClick={() => decide('approve')} disabled={busy}
              className="flex-1 bg-emerald-600 text-white text-sm py-2 rounded-lg disabled:opacity-50">Approve</button>
            <button onClick={() => decide('reject')} disabled={busy}
              className="flex-1 bg-red-600 text-white text-sm py-2 rounded-lg disabled:opacity-50">Reject</button>
          </>
        )}
      </div>
    </div>
  )
}

export default function FieldApprovals({ back = '/supervisor' }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  const [sel, setSel] = useState(new Set())
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setError(''); setSel(new Set())
    try { setRows(await api.fieldApprovals('pending')) } catch (e) { setError(e.message) }
  }, [])

  useEffect(() => { load() }, [load])

  async function decide(kind, eventId) {
    try {
      if (kind === 'approve') await api.approveField(eventId)
      else await api.rejectField(eventId)
      setRows((r) => r.filter((x) => x.event_id !== eventId))
    } catch (e) {
      setError(e.message)
    }
  }

  function toggle(eventId) {
    setSel((s) => {
      const n = new Set(s)
      n.has(eventId) ? n.delete(eventId) : n.add(eventId)
      return n
    })
  }

  const selectable = (rows || []).filter((r) => !r.delegated)
  const allSelected = selectable.length > 0 && selectable.every((r) => sel.has(r.event_id))
  function toggleAll() {
    setSel(allSelected ? new Set() : new Set(selectable.map((r) => r.event_id)))
  }

  async function delegate() {
    if (sel.size === 0) { setError('Select at least one scan to delegate.'); return }
    setBusy(true); setError('')
    try {
      const res = await api.delegateFieldApprovals([...sel], comment.trim() || null)
      setComment('')
      await load()
      if (res.assistant) setError('')
    } catch (e) {
      setError(e.message)
    } finally { setBusy(false) }
  }

  async function recall(taskId) {
    try { await api.recallTask(taskId); await load() } catch (e) { setError(e.message) }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="Field Approvals" back={back} />
      <main className="p-4 max-w-md mx-auto space-y-3">
        {error && <p className="text-red-600 text-sm">{error}</p>}

        {selectable.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm p-3 space-y-2">
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input type="checkbox" className="w-5 h-5 accent-slate-900"
                checked={allSelected} onChange={toggleAll} />
              Select all ({selectable.length})
            </label>
            <input value={comment} onChange={(e) => setComment(e.target.value)}
              placeholder="Optional note for your EA"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm" />
            <button onClick={delegate} disabled={busy || sel.size === 0}
              className="w-full bg-slate-900 text-white text-sm py-2 rounded-lg disabled:opacity-50">
              {busy ? 'Delegating…' : `Delegate ${sel.size || ''} to EA`}
            </button>
          </div>
        )}

        {rows === null ? (
          <p className="text-center text-slate-400 py-8">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="text-center text-slate-500 py-10">
            <div className="text-4xl mb-2">✓</div>
            <p className="text-sm">No field scans awaiting approval.</p>
          </div>
        ) : (
          rows.map((it) => (
            <Card key={it.event_id} item={it} onDecide={decide}
              selected={sel.has(it.event_id)} onToggle={toggle} onRecall={recall} />
          ))
        )}
        <p className="text-[11px] text-slate-400 text-center pt-2">
          These scans were logged outside a station geofence or with uncertain GPS.
          Approve for special circumstances, reject to exclude, or delegate to your EA.
        </p>
      </main>
    </div>
  )
}

