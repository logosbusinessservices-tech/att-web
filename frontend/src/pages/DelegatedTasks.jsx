import { useCallback, useEffect, useState } from 'react'
import AppHeader from '../components/AppHeader.jsx'
import AuthImage from '../components/AuthImage.jsx'
import { api } from '../lib/api.js'
import { fmtDayLabel, fmtHours, fmtTime, statusClass, statusLabel } from '../lib/format.js'

// ── Field-approval task card ─────────────────────────────────────────────────
function FieldTaskCard({ task, onDone, setError }) {
  const [busy, setBusy] = useState(false)
  const f = task.field
  const km = f?.distance_m != null ? (f.distance_m / 1000).toFixed(1) : null

  async function decide(kind) {
    setBusy(true); setError('')
    try {
      if (kind === 'approve') await api.assistantApproveFieldTask(task.id)
      else await api.assistantRejectFieldTask(task.id)
      onDone(task.id)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (!f) return null
  return (
    <div className="bg-white rounded-xl shadow-sm p-3">
      <div className="flex gap-3">
        {f.selfie_url && (
          <AuthImage src={api.assistantFieldSelfieUrl(f.event_id)} alt=""
            className="w-16 h-16 rounded-lg object-cover bg-slate-100 shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-slate-800">{f.display_name}</div>
          <div className="text-xs text-slate-400">
            {f.external_id} · {fmtDayLabel(f.for_date)} · {fmtTime(f.event_time)} · {f.direction}
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {km != null && f.nearest_station_name
              ? `${km} km from ${f.nearest_station_name}` : 'Location unavailable'}
            {f.gps_accuracy_m != null && ` · ±${Math.round(f.gps_accuracy_m)} m`}
          </div>
        </div>
      </div>
      {task.comment && (
        <p className="text-xs text-slate-600 mt-2 bg-slate-50 rounded-lg px-2 py-1.5">
          <span className="font-medium text-slate-500">{task.supervisor_name}:</span> {task.comment}
        </p>
      )}
      <div className="flex gap-2 mt-3">
        <button onClick={() => decide('approve')} disabled={busy}
          className="flex-1 bg-emerald-600 text-white text-sm py-2 rounded-lg disabled:opacity-50">Approve</button>
        <button onClick={() => decide('reject')} disabled={busy}
          className="flex-1 bg-red-600 text-white text-sm py-2 rounded-lg disabled:opacity-50">Reject</button>
      </div>
    </div>
  )
}

// ── One crossing with inline edit-time and delete (scoped to the task) ───────
function CrossingRow({ taskId, event, onDay, setError }) {
  const [editing, setEditing] = useState(false)
  const [time, setTime] = useState('')
  const [busy, setBusy] = useState(false)
  const canEdit = event.direction === 'entry' || event.direction === 'exit'

  async function save() {
    setBusy(true); setError('')
    try { onDay(await api.assistantTaskEditCrossing(taskId, event.id, time)); setEditing(false) }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function remove() {
    setBusy(true); setError('')
    try { onDay(await api.assistantTaskDeleteCrossing(taskId, event.id)) }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <li className="text-xs text-slate-500">
      <div className="flex items-center justify-between gap-2">
        <span>{fmtTime(event.event_time)} · {event.camera_label}</span>
        <span className="flex items-center gap-2">
          <span className="text-slate-400">{event.source === 'manual' ? '✎ adjusted' : (event.direction ?? 'seen')}</span>
          {canEdit && !editing && (
            <>
              <button onClick={() => setEditing(true)} className="text-sky-700 underline">edit</button>
              <button onClick={remove} disabled={busy} className="text-red-600 underline disabled:opacity-50">delete</button>
            </>
          )}
        </span>
      </div>
      {editing && (
        <div className="flex items-center gap-1 mt-1">
          <input type="time" value={time} onChange={(e) => setTime(e.target.value)}
            className="border border-slate-300 rounded px-1 py-0.5 text-xs" />
          <button onClick={save} disabled={busy || !time} className="bg-emerald-600 text-white text-xs px-2 py-0.5 rounded disabled:opacity-50">save</button>
          <button onClick={() => setEditing(false)} className="text-slate-400 text-xs px-1">cancel</button>
        </div>
      )}
    </li>
  )
}

function AddCrossing({ task, onDay, setError }) {
  const [open, setOpen] = useState(false)
  const [direction, setDirection] = useState('entry')
  const [time, setTime] = useState('')
  const [busy, setBusy] = useState(false)

  async function add() {
    setBusy(true); setError('')
    try {
      onDay(await api.assistantTaskAddCrossing(task.id, {
        externalId: task.external_id, forDate: task.for_date, direction, time,
      }))
      setOpen(false); setTime('')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (!open) {
    return <button onClick={() => setOpen(true)} className="text-[11px] text-sky-700 underline mt-1">+ Add crossing</button>
  }
  return (
    <div className="mt-1 flex items-center gap-1">
      <select value={direction} onChange={(e) => setDirection(e.target.value)}
        className="border border-slate-300 rounded px-1 py-0.5 text-xs">
        <option value="entry">Entry</option>
        <option value="exit">Exit</option>
      </select>
      <input type="time" value={time} onChange={(e) => setTime(e.target.value)}
        className="border border-slate-300 rounded px-1 py-0.5 text-xs" />
      <button onClick={add} disabled={busy || !time} className="bg-emerald-600 text-white text-xs px-2 py-0.5 rounded disabled:opacity-50">add</button>
      <button onClick={() => setOpen(false)} className="text-slate-400 text-xs px-1">cancel</button>
    </div>
  )
}

// ── Attendance-edit task card ────────────────────────────────────────────────
function AttendanceTaskCard({ task, onDone, setError }) {
  const [day, setDay] = useState(task.day)
  const [busy, setBusy] = useState(false)

  async function complete() {
    setBusy(true); setError('')
    try { await api.assistantCompleteTask(task.id); onDone(task.id) }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="bg-white rounded-xl shadow-sm p-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-slate-800">{task.display_name}</div>
          <div className="text-xs text-slate-400">{task.external_id} · {fmtDayLabel(task.for_date)}</div>
        </div>
        {day && (
          <span className="flex items-center gap-2 text-xs">
            <span className="text-slate-500">{fmtHours(day.hours_in_office)} · {day.entry_count}↓/{day.exit_count}↑</span>
            <span className={`px-2 py-0.5 rounded-full ${statusClass(day.status)}`}>{statusLabel(day.status)}</span>
          </span>
        )}
      </div>

      <p className="text-xs text-slate-600 mt-2 bg-amber-50 rounded-lg px-2 py-1.5">
        <span className="font-medium text-slate-500">{task.supervisor_name}:</span> {task.comment}
      </p>

      <div className="mt-2 pt-2 border-t border-slate-100">
        {day && day.events && day.events.length > 0 ? (
          <ul className="space-y-0.5">
            {day.events.map((e) => (
              <CrossingRow key={e.id} taskId={task.id} event={e} onDay={setDay} setError={setError} />
            ))}
          </ul>
        ) : (
          <p className="text-xs text-slate-400">No crossings recorded for this day.</p>
        )}
        <AddCrossing task={task} onDay={setDay} setError={setError} />
      </div>

      <button onClick={complete} disabled={busy}
        className="w-full mt-3 bg-brand-red text-white text-sm py-2 rounded-lg disabled:opacity-50">
        {busy ? 'Completing…' : 'Mark complete'}
      </button>
    </div>
  )
}

export default function DelegatedTasks({ back = '/assistant' }) {
  const [tab, setTab] = useState('field_approval')
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError(''); setRows(null)
    try { setRows(await api.assistantTasks(tab)) } catch (e) { setError(e.message) }
  }, [tab])

  useEffect(() => { load() }, [load])

  function removeRow(id) {
    setRows((r) => r.filter((x) => x.id !== id))
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="Delegated Tasks" back={back} />
      <main className="p-4 max-w-md mx-auto space-y-3">
        <div className="flex bg-white rounded-xl shadow-sm p-1">
          <button onClick={() => setTab('field_approval')}
            className={`flex-1 text-sm py-1.5 rounded-lg ${tab === 'field_approval' ? 'bg-slate-900 text-white' : 'text-slate-600'}`}>
            Field Approvals
          </button>
          <button onClick={() => setTab('attendance_edit')}
            className={`flex-1 text-sm py-1.5 rounded-lg ${tab === 'attendance_edit' ? 'bg-slate-900 text-white' : 'text-slate-600'}`}>
            Attendance Changes
          </button>
        </div>

        {error && <p className="text-red-600 text-sm">{error}</p>}

        {rows === null ? (
          <p className="text-center text-slate-400 py-8">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="text-center text-slate-500 py-10">
            <div className="text-4xl mb-2">✓</div>
            <p className="text-sm">No {tab === 'field_approval' ? 'field approvals' : 'attendance changes'} delegated to you.</p>
          </div>
        ) : (
          rows.map((t) => (
            tab === 'field_approval'
              ? <FieldTaskCard key={t.id} task={t} onDone={removeRow} setError={setError} />
              : <AttendanceTaskCard key={t.id} task={t} onDone={removeRow} setError={setError} />
          ))
        )}
      </main>
    </div>
  )
}
