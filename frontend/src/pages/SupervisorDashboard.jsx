import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api.js'
import AppHeader from '../components/AppHeader.jsx'
import FilterPicker from '../components/FilterPicker.jsx'
import { useAuth } from '../lib/auth.jsx'
import { fmtDayLabel, fmtHours, fmtTime, statusClass, statusLabel } from '../lib/format.js'

// Inline direct-override form for a single day in the drill-in.
function DayOverride({ ext, day, onDone }) {
  const [openForm, setOpenForm] = useState(false)
  const [newStatus, setNewStatus] = useState('present')
  const [entryTime, setEntryTime] = useState('')
  const [exitTime, setExitTime] = useState('')
  const [reason, setReason] = useState('')
  const [err, setErr] = useState('')

  async function save() {
    setErr('')
    try {
      await api.createOverride({
        external_id: ext,
        for_date: day.date,
        new_status: newStatus || null,
        entry_time: entryTime || null,
        exit_time: exitTime || null,
        reason: reason.trim() || null,
      })
      setOpenForm(false)
      onDone()
    } catch (e) {
      setErr(e.message)
    }
  }

  if (!openForm) {
    return (
      <button onClick={() => setOpenForm(true)} className="text-[11px] text-sky-700 underline">
        Adjust
      </button>
    )
  }
  return (
    <div className="mt-1 w-full space-y-1">
      <div className="flex gap-1">
        <select value={newStatus} onChange={(e) => setNewStatus(e.target.value)}
          className="flex-1 border border-slate-300 rounded px-1 py-1 text-xs">
          <option value="">(no change)</option>
          <option value="present">Present</option>
          <option value="absent">Absent</option>
        </select>
        <input type="time" value={entryTime} onChange={(e) => setEntryTime(e.target.value)}
          className="w-20 border border-slate-300 rounded px-1 py-1 text-xs" title="Entry" />
        <input type="time" value={exitTime} onChange={(e) => setExitTime(e.target.value)}
          className="w-20 border border-slate-300 rounded px-1 py-1 text-xs" title="Exit" />
      </div>
      <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason"
        className="w-full border border-slate-300 rounded px-1 py-1 text-xs" />
      {err && <p className="text-[11px] text-red-600">{err}</p>}
      <div className="flex gap-2">
        <button onClick={save} className="flex-1 bg-emerald-600 text-white text-xs py-1 rounded">Save</button>
        <button onClick={() => setOpenForm(false)} className="px-2 text-xs text-slate-400">cancel</button>
      </div>
    </div>
  )
}

// Delegate fixing this day to the supervisor's EA (comment mandatory).
function DelegateDay({ ext, day }) {
  const [open, setOpen] = useState(false)
  const [comment, setComment] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function send() {
    if (!comment.trim()) { setErr('A comment is required when delegating.'); return }
    setBusy(true); setErr('')
    try {
      const res = await api.delegateAttendanceEdit({ ext, forDate: day.date, comment: comment.trim() })
      setMsg(`Delegated to ${res.assistant || 'your EA'}`)
      setOpen(false); setComment('')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (msg) return <span className="text-[11px] text-emerald-700">{msg}</span>
  if (!open) {
    return (
      <button onClick={() => { setOpen(true); setErr('') }} className="text-[11px] text-amber-700 underline">
        Delegate
      </button>
    )
  }
  return (
    <div className="mt-1 w-full space-y-1">
      <input value={comment} onChange={(e) => setComment(e.target.value)}
        placeholder="Comment for EA (required)"
        className="w-full border border-slate-300 rounded px-1 py-1 text-xs" />
      {err && <p className="text-[11px] text-red-600">{err}</p>}
      <div className="flex gap-2">
        <button onClick={send} disabled={busy} className="flex-1 bg-amber-600 text-white text-xs py-1 rounded disabled:opacity-50">
          {busy ? 'Delegating…' : 'Delegate to EA'}
        </button>
        <button onClick={() => setOpen(false)} className="px-2 text-xs text-slate-400">cancel</button>
      </div>
    </div>
  )
}

function istToday() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date())
}

// One crossing with inline edit-time and delete (audit-friendly).
function CrossingRow({ event, onDay }) {
  const [editing, setEditing] = useState(false)
  const [time, setTime] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const canEdit = event.direction === 'entry' || event.direction === 'exit'

  async function save() {
    setBusy(true); setErr('')
    try { onDay(await api.editCrossing(event.id, time)); setEditing(false) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  async function remove() {
    setBusy(true); setErr('')
    try { onDay(await api.deleteCrossing(event.id)) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <li className="text-xs text-slate-500">
      <div className="flex items-center justify-between gap-2">
        <span>{fmtTime(event.event_time)} · {event.camera_label}</span>
        <span className="flex items-center gap-2">
          <span className="text-slate-400">{event.source === 'manual' ? '✎ adjusted' : (event.direction ?? 'seen')}</span>
          {canEdit && !editing && (
            <>
              <button onClick={() => { setEditing(true); setErr('') }} className="text-sky-700 underline">edit</button>
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
      {err && <p className="text-[11px] text-red-600 mt-0.5">{err}</p>}
    </li>
  )
}

// Add a new entry/exit crossing to a day.
function AddCrossing({ ext, date, onDay }) {
  const [open, setOpen] = useState(false)
  const [direction, setDirection] = useState('entry')
  const [time, setTime] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function add() {
    setBusy(true); setErr('')
    try { onDay(await api.addCrossing({ externalId: ext, forDate: date, direction, time })); setOpen(false); setTime('') }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (!open) {
    return <button onClick={() => { setOpen(true); setErr('') }} className="text-[11px] text-sky-700 underline mt-1">+ Add crossing</button>
  }
  return (
    <div className="mt-1 space-y-1">
      <div className="flex items-center gap-1">
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
      {err && <p className="text-[11px] text-red-600">{err}</p>}
    </div>
  )
}

// Day / week / month ranges so the supervisor can view hours per period.
function ranges() {
  const today = istToday()
  const [y, m] = today.split('-').map(Number)
  const monthStart = `${y}-${String(m).padStart(2, '0')}-01`
  const weekStart = new Date(new Date(today).getTime() - 6 * 86400000).toISOString().slice(0, 10)
  return { day: [today, today], week: [weekStart, today], month: [monthStart, today] }
}

export default function SupervisorDashboard({ back = '/supervisor' }) {
  const { user } = useAuth()
  const isChief = user?.role === 'chief'
  const r = useMemo(ranges, [])
  const [period, setPeriod] = useState('month')
  const [depts, setDepts] = useState([])
  const [people, setPeople] = useState([])   // all employees, for the filter dropdown
  const [deptId, setDeptId] = useState('')
  const [filter, setFilter] = useState('')   // '' | dept:<id> | emp:<ext>
  const [rows, setRows] = useState([])
  const [selected, setSelected] = useState(null) // { ext, name, days }
  const [error, setError] = useState('')

  const [from, to] = r[period]

  useEffect(() => {
    api.departments().then(setDepts).catch(() => {})
  }, [])

  // Full (unfiltered) employee list for the grouped "Filter by" dropdown.
  useEffect(() => {
    api.supervisorOverview(from, to).then(setPeople).catch(() => {})
  }, [from, to])

  const load = useCallback(async () => {
    setError('')
    try {
      setRows(await api.supervisorOverview(from, to, deptId || undefined))
    } catch (e) {
      setError(e.message)
    }
  }, [from, to, deptId])

  useEffect(() => { load() }, [load])

  const openEmployee = useCallback(async (ext, name) => {
    try {
      const days = await api.employeeSummary(ext, from, to)
      setSelected({ ext, name, days })
    } catch (e) {
      setError(e.message)
    }
  }, [from, to])

  // Merge an updated single-day summary (returned by a crossing edit) into view.
  const applyDay = useCallback((newDay) => {
    setSelected((s) => s && ({
      ...s,
      days: s.days.map((d) => (d.date === newDay.date ? newDay : d)),
    }))
  }, [])

  // Re-open the individual detail when the period changes while an employee is picked.
  useEffect(() => {
    if (filter.startsWith('emp:')) {
      const ext = filter.slice(4)
      const p = people.find((x) => x.external_id === ext)
      if (p) openEmployee(ext, p.display_name)
    }
  }, [from, to]) // eslint-disable-line react-hooks/exhaustive-deps

  function onFilterChange(value) {
    setFilter(value)
    setSelected(null)
    if (value.startsWith('dept:')) {
      setDeptId(value.slice(5))
    } else if (value.startsWith('emp:')) {
      const ext = value.slice(4)
      const p = people.find((x) => x.external_id === ext)
      setDeptId(p?.department_id ? String(p.department_id) : '')
      if (p) openEmployee(ext, p.display_name)
    } else {
      setDeptId('')
    }
  }

  // Return from an employee's detail view to the full list.
  function closeEmployee() {
    setSelected(null)
    if (filter.startsWith('emp:')) {
      setFilter('')
      setDeptId('')
    }
  }

  // Group employees by department (kept for potential grouping needs).
  const peopleByDept = useMemo(() => {
    const map = new Map()
    for (const p of people) {
      const key = p.department_id ?? 0
      if (!map.has(key)) map.set(key, [])
      map.get(key).push(p)
    }
    return map
  }, [people])
  void peopleByDept

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="Employee Attendance" back={back} />

      <main className="p-4 max-w-3xl mx-auto space-y-4">
        {/* Time-level filter */}
        <div className="flex bg-white rounded-xl shadow-sm p-1">
          {['day', 'week', 'month'].map((p) => (
            <button
              key={p}
              onClick={() => { setPeriod(p) }}
              className={`flex-1 text-sm py-1.5 rounded-lg capitalize ${
                period === p ? 'bg-slate-900 text-white' : 'text-slate-600'
              }`}
            >
              {p}
            </button>
          ))}
        </div>

        {error && <p className="text-red-600 text-sm">{error}</p>}

        {!selected && (
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-slate-800 flex-1">
            {deptId
              ? depts.find((d) => String(d.id) === String(deptId))?.name
              : 'All'} · this {period}
          </h2>
          <FilterPicker
            depts={depts}
            people={people}
            value={filter}
            onChange={onFilterChange}
            allowDept={isChief}
            allLabel={isChief ? 'All departments' : (user?.department_name || 'All departments')}
          />
        </div>
        )}

        {!selected && (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-slate-600 text-xs">
              <tr>
                <th className="text-left px-3 py-2">Employee</th>
                <th className="px-2 py-2">Present</th>
                <th className="px-2 py-2">Absent</th>
                <th className="px-2 py-2">%</th>
                <th className="px-2 py-2">Hours</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.person_id}
                  onClick={() => openEmployee(row.external_id, row.display_name)}
                  className="border-t border-slate-100 cursor-pointer hover:bg-slate-50"
                >
                  <td className="px-3 py-2">
                    <div className="font-medium text-slate-800">{row.display_name}</div>
                    <div className="text-xs text-slate-400">
                      {row.external_id}{row.department_name ? ` · ${row.department_name}` : ''}
                    </div>
                  </td>
                  <td className="text-center text-emerald-600">{row.present}</td>
                  <td className="text-center text-red-600">{row.absent}</td>
                  <td className="text-center font-medium">{row.attendance_pct}%</td>
                  <td className="text-center text-slate-600">{fmtHours(row.total_hours)}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan="5" className="text-center text-slate-400 py-6">No employees.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        )}

        {!selected && (
          <p className="text-xs text-slate-400 text-center">
            Tap an employee to view daily records, edit in/out times, or change absent → present. Corrections are logged.
          </p>
        )}

        {selected && (
          <div className="bg-white rounded-xl shadow-sm p-3">
            <button onClick={closeEmployee}
              className="flex items-center gap-1 text-sm text-slate-600 font-medium mb-2">
              <span className="text-lg leading-none">‹</span> All employees
            </button>
            <h3 className="font-semibold text-slate-800 mb-2">{selected.name} — daily (this {period})</h3>
            <ul className="space-y-2">
              {selected.days.filter((d) => d.event_count > 0 || d.status === 'absent' || d.adjusted).map((d) => (
                <li key={d.date} className="border border-slate-100 rounded-lg p-2">
                  <div className="flex flex-wrap items-center justify-between text-sm gap-y-1">
                    <span className="text-slate-700 flex items-center gap-1.5">
                      {fmtDayLabel(d.date)}
                      {d.adjusted && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-violet-50 text-violet-700">Adjusted</span>
                      )}
                      {d.has_anomaly && (
                        <span title={d.anomalies.map((a) => a.message).join('\n')}
                          className="text-[10px] px-1.5 py-0.5 rounded-full bg-orange-50 text-orange-700">⚠ review</span>
                      )}
                    </span>
                    <span className="flex items-center gap-3">
                      <span className="text-xs text-slate-500">{fmtHours(d.hours_in_office)} · {d.entry_count}↓/{d.exit_count}↑</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${statusClass(d.status)}`}>{statusLabel(d.status)}</span>
                      <DayOverride ext={selected.ext} day={d} onDone={() => openEmployee(selected.ext, selected.name)} />
                      <DelegateDay ext={selected.ext} day={d} />
                    </span>
                  </div>

                  {/* In/out crossings — edit time, delete, or add (audit-logged). */}
                  <div className="mt-1.5 pt-1.5 border-t border-slate-100">
                    {d.event_count > 0 && (
                      <ul className="space-y-0.5">
                        {d.events.map((e) => (
                          <CrossingRow key={e.id} event={e} onDay={applyDay} />
                        ))}
                      </ul>
                    )}
                    <AddCrossing ext={selected.ext} date={d.date} onDay={applyDay} />
                  </div>
                </li>
              ))}
              {selected.days.filter((d) => d.event_count > 0 || d.status === 'absent' || d.adjusted).length === 0 && (
                <li className="text-xs text-slate-400">No activity in this period.</li>
              )}
            </ul>
          </div>
        )}
      </main>
    </div>
  )
}
