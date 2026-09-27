import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api.js'
import AppHeader from '../components/AppHeader.jsx'
import { fmtDayLabel, fmtHours, fmtTime, statusClass, statusLabel } from '../lib/format.js'

// Build IST date ranges on the client (YYYY-MM-DD) for the period toggle.
function istToday() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date())
}
function ranges() {
  const today = istToday()
  const [y, m] = today.split('-').map(Number)
  const monthStart = `${y}-${String(m).padStart(2, '0')}-01`
  const weekStart = new Date(new Date(today).getTime() - 6 * 86400000).toISOString().slice(0, 10)
  return {
    month: [monthStart, today],
    week: [weekStart, today],
    day: [today, today],
  }
}

function StatCard({ label, value, tone }) {
  return (
    <div className="bg-white rounded-xl shadow-sm p-3 text-center">
      <div className={`text-2xl font-bold ${tone}`}>{value}</div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
    </div>
  )
}

// One entry/exit crossing — read-only. Employees view records; corrections are
// handled by a supervisor (reported in person), not via in-app disputes.
function LogRow({ event }) {
  const label =
    event.source === 'field' ? '📍 field'
    : event.source === 'manual' ? '✎ adjusted'
    : (event.direction ?? 'seen')

  return (
    <li className="text-xs text-slate-600">
      <div className="flex items-center justify-between">
        <span>{fmtTime(event.event_time)} · {event.camera_label}</span>
        <span className="text-slate-400">{label}</span>
      </div>
    </li>
  )
}

function DayRow({ day }) {
  const hasEvents = day.event_count > 0

  return (
    <li className="bg-white rounded-xl shadow-sm overflow-hidden">
      <div className="flex items-center justify-between p-3">
        <div>
          <div className="text-sm font-medium text-slate-800 flex items-center gap-1.5">
            {fmtDayLabel(day.date)}
            {day.adjusted && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-violet-50 text-violet-700">Adjusted</span>
            )}
            {day.has_anomaly && (
              <span
                title={day.anomalies.map((a) => a.message).join('\n')}
                className="text-[10px] px-1.5 py-0.5 rounded-full bg-orange-50 text-orange-700"
              >
                ⚠ Needs review
              </span>
            )}
          </div>
          <div className="text-xs text-slate-500">
            {hasEvents ? `${fmtTime(day.first_seen)} → ${fmtTime(day.last_seen)}` : '—'}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {hasEvents && (
            <div className="text-right">
              <div className="text-sm font-semibold text-slate-700">{fmtHours(day.hours_in_office)}</div>
              <div className="text-[11px] text-slate-400">{day.entry_count}↓ / {day.exit_count}↑</div>
            </div>
          )}
          <span className={`text-xs px-2 py-1 rounded-full ${statusClass(day.status)}`}>
            {statusLabel(day.status)}
          </span>
        </div>
      </div>

      {/* Always-visible crossings (no click needed). */}
      {hasEvents && (
        <div className="border-t border-slate-100 px-3 py-2 bg-slate-50 space-y-1.5">
          {day.adjusted && day.adjustment_reason && (
            <p className="text-xs text-violet-700">Supervisor note: {day.adjustment_reason}</p>
          )}
          {day.has_anomaly && (
            <p className="text-xs text-orange-700">⚠ {day.anomalies[0].message}</p>
          )}
          <ul className="space-y-1.5">
            {day.events.map((e) => (
              <LogRow key={e.id} event={e} />
            ))}
          </ul>
        </div>
      )}
    </li>
  )
}

export default function EmployeeDashboard({ back = '/employee' }) {
  const [period, setPeriod] = useState('month')
  const [days, setDays] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const r = useMemo(() => ranges(), [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    const [from, to] = r[period]
    try {
      const [s, st] = await Promise.all([api.summary(from, to), api.stats(from, to)])
      setDays(s)
      setStats(st)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [period, r])

  useEffect(() => { load() }, [load])

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="View My Attendance" back={back} />

      <main className="p-4 max-w-2xl mx-auto space-y-4">
        <div className="grid grid-cols-3 gap-2">
          <StatCard label="Present" value={stats?.present ?? '–'} tone="text-emerald-600" />
          <StatCard label="Absent" value={stats?.absent ?? '–'} tone="text-red-600" />
          <StatCard label="Attend %" value={stats ? `${stats.attendance_pct}%` : '–'} tone="text-slate-800" />
        </div>
        {stats && (
          <div className="text-xs text-slate-500 text-center">
            Total hours this {period}:{' '}
            <span className="font-semibold text-slate-700">{fmtHours(stats.total_hours)}</span>
          </div>
        )}

        <div className="flex bg-white rounded-xl shadow-sm p-1">
          {['day', 'week', 'month'].map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`flex-1 text-sm py-1.5 rounded-lg capitalize ${
                period === p ? 'bg-slate-900 text-white' : 'text-slate-600'
              }`}
            >
              {p}
            </button>
          ))}
        </div>

        {error && <p className="text-red-600 text-sm">{error}</p>}
        {loading ? (
          <div className="text-center text-slate-400 py-8">Loading…</div>
        ) : days.length === 0 ? (
          <p className="text-slate-500 text-sm text-center py-8">No records in this period.</p>
        ) : (
          <ul className="space-y-2">
            {days.map((day) => (
              <DayRow key={day.date} day={day} />
            ))}
          </ul>
        )}

        <p className="text-xs text-slate-400 text-center pt-2">
          Field attendance (face scan + GPS) arrives in Phase 3.
        </p>
      </main>
    </div>
  )
}
