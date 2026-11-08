import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts'
import AppHeader from '../components/AppHeader.jsx'
import AuthImage from '../components/AuthImage.jsx'
import { api } from '../lib/api.js'
import { useAuth } from '../lib/auth.jsx'
import { fmtDayLabel, fmtHours, fmtTime, statusClass, statusLabel } from '../lib/format.js'
import { downloadCsv, exportChartPng, exportDashboardPdf, exportDashboardPptx } from '../lib/exporters.js'

function istToday() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date())
}
function monthStart() {
  const [y, m] = istToday().split('-')
  return `${y}-${m}-01`
}

const PIE_COLORS = { camera: '#3b82f6', field: '#10b981', manual: '#a855f7' }

const CAPTURE_TYPES = [
  ['camera', 'Camera'],
  ['field', 'Field'],
  ['manual', 'Manual'],
]
const ROLES = [
  ['employee', 'Employee'],
  ['supervisor', 'Supervisor'],
]
const ALL_SOURCES = CAPTURE_TYPES.map(([v]) => v)
const DEFAULT_ROLES = ['employee']

// Short source icons used in the drill-down timeline.
const SOURCE_BADGE = {
  camera: { icon: '📷', label: 'Camera', color: 'bg-sky-100 text-sky-700' },
  field: { icon: '📍', label: 'Field', color: 'bg-emerald-100 text-emerald-700' },
  manual: { icon: '✎', label: 'Manual', color: 'bg-violet-100 text-violet-700' },
}

const CHART_ORDER = [
  ['trend', 'Attendance % trend'],
  ['pa', 'Present vs Absent'],
  ['dept', 'Attendance % by department'],
  ['split', 'Camera vs Field vs Manual'],
  ['hours', 'Hours by employee'],
  ['low', 'Lowest attendance'],
]

function Kpi({ label, value, tone = 'text-slate-800' }) {
  return (
    <div className="bg-white rounded-xl shadow-sm p-3 text-center">
      <div className={`text-2xl font-bold ${tone}`}>{value}</div>
      <div className="text-[11px] text-slate-500 mt-0.5">{label}</div>
    </div>
  )
}

function CheckPill({ label, checked, onToggle }) {
  return (
    <label className={`inline-flex items-center gap-1.5 text-xs px-3 py-1 rounded-full border cursor-pointer select-none ${
      checked ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white text-slate-700 border-slate-300'
    }`}>
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        className="w-3 h-3 accent-white cursor-pointer"
      />
      {label}
    </label>
  )
}

function AttributeTable({ title, rows, csvName }) {
  return (
    <div className="bg-white rounded-xl shadow-sm p-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        <button onClick={() => downloadCsv(`${csvName}.csv`, rows)}
          className="text-[11px] px-2 py-1 rounded bg-slate-100 text-slate-600 hover:bg-slate-200">CSV</button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-slate-100 text-slate-600">
            <tr>
              <th className="text-left px-2 py-1.5 font-medium">Group</th>
              <th className="text-right px-2 py-1.5 font-medium">Staff</th>
              <th className="text-right px-2 py-1.5 font-medium">Present</th>
              <th className="text-right px-2 py-1.5 font-medium">Absent</th>
              <th className="text-right px-2 py-1.5 font-medium">Attend %</th>
              <th className="text-right px-2 py-1.5 font-medium">Hours</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-t border-slate-100">
                <td className="px-2 py-1.5 text-slate-700">{r.key}</td>
                <td className="px-2 py-1.5 text-right">{r.headcount}</td>
                <td className="px-2 py-1.5 text-right text-emerald-600">{r.present}</td>
                <td className="px-2 py-1.5 text-right text-red-600">{r.absent}</td>
                <td className="px-2 py-1.5 text-right">{r.attendance_pct}%</td>
                <td className="px-2 py-1.5 text-right">{r.total_hours}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={6} className="text-center text-slate-400 py-4">No data.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ChartCard({ title, csvName, csvRows, innerRef, children }) {
  const localRef = useRef(null)
  const setRef = (el) => { localRef.current = el; innerRef?.(el) }
  return (
    <div className="bg-white rounded-xl shadow-sm p-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        <div className="flex gap-1">
          {csvRows && (
            <button onClick={() => downloadCsv(`${csvName}.csv`, csvRows())}
              className="text-[11px] px-2 py-1 rounded bg-slate-100 text-slate-600 hover:bg-slate-200">CSV</button>
          )}
          <button onClick={() => exportChartPng(localRef.current, `${csvName}.png`)}
            className="text-[11px] px-2 py-1 rounded bg-slate-100 text-slate-600 hover:bg-slate-200">PNG</button>
        </div>
      </div>
      <div ref={setRef}>{children}</div>
    </div>
  )
}

// ── Drill-down panel (Phase 2) ───────────────────────────────────────────
// One row showing a single attendance event with its metadata and (for camera
// events with a saved crop) a clickable face-crop thumbnail.
function EventRow({ event }) {
  const badge = SOURCE_BADGE[event.source] || SOURCE_BADGE.camera
  const time = fmtTime(event.event_time)
  const direction = event.direction || 'seen'
  const sim = event.similarity != null ? ` · match ${(event.similarity * 100).toFixed(0)}%` : ''
  const review = event.review_status && event.review_status !== 'approved'
    ? ` · ${event.review_status}`
    : ''

  return (
    <li className="flex items-center gap-3 py-1.5 border-t border-slate-50">
      {/* Thumbnail: camera events with a saved crop get a real image,
          otherwise an icon placeholder. */}
      <div className="flex-shrink-0 w-12 h-12">
        {event.source === 'camera' && event.crop_path ? (
          <AuthImage
            src={api.eventCropUrl(event.id)}
            alt={`Face at ${time}`}
            className="w-12 h-12 rounded object-cover border border-slate-200"
            fallback={
              <div className="w-12 h-12 rounded bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-300 text-lg">
                ⋯
              </div>
            }
            zoomable
          />
        ) : (
          <div className="w-12 h-12 rounded bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-300 text-xl"
               title={event.source === 'camera' ? 'Crop not available' : 'No crop for non-camera events'}>
            {badge.icon}
          </div>
        )}
      </div>

      {/* Details. */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-slate-800 tabular-nums">{time}</span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${badge.color}`}>
            {badge.icon} {badge.label}
          </span>
          <span className="text-xs text-slate-500">{direction}{sim}{review}</span>
        </div>
        <div className="text-[11px] text-slate-400 truncate">
          {event.camera_label}
          {event.source === 'field' && event.distance_m != null && (
            <span> · {Math.round(event.distance_m)} m from station</span>
          )}
        </div>
      </div>
    </li>
  )
}

// A single day card inside the drill-down.
function DayCard({ day }) {
  const events = day.events || []
  return (
    <div className="bg-white rounded-lg border border-slate-100 p-3">
      <div className="flex items-center justify-between flex-wrap gap-y-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-700">{fmtDayLabel(day.date)}</span>
          <span className={`text-[10px] px-2 py-0.5 rounded-full ${statusClass(day.status)}`}>
            {statusLabel(day.status)}
          </span>
          {day.adjusted && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-violet-50 text-violet-700"
                  title={day.adjustment_reason || 'A supervisor correction was applied to this day'}>
              Adjusted
            </span>
          )}
          {day.has_anomaly && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-orange-50 text-orange-700"
                  title={day.anomalies.map((a) => a.message).join('\n')}>
              ⚠ Review
            </span>
          )}
        </div>
        <span className="text-xs text-slate-500 tabular-nums">
          {fmtHours(day.hours_in_office)} · {day.entry_count}↓/{day.exit_count}↑
        </span>
      </div>
      {events.length > 0 ? (
        <ul className="mt-1.5">
          {events.map((e) => <EventRow key={e.id} event={e} />)}
        </ul>
      ) : (
        <p className="text-xs text-slate-400 mt-2 italic">No events on this day.</p>
      )}
    </div>
  )
}

// The drill-down block that appears inline under a clicked employee.
// Loads the employee's day-by-day timeline for the current date range and
// shows EVERY event — ignoring the capture-type filter on purpose.
function EmployeeDrilldown({ externalId, name, from, to }) {
  const [days, setDays] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    let active = true
    setErr('')
    setDays(null)
    api.supervisorEmployeeSummary(externalId, from, to)
      .then((d) => { if (active) setDays(d) })
      .catch((e) => { if (active) setErr(e.message) })
    return () => { active = false }
  }, [externalId, from, to])

  if (err) return <p className="text-xs text-red-600 p-3">{err}</p>
  if (days === null) return <p className="text-xs text-slate-400 p-3">Loading timeline…</p>

  // Hide weekends / upcoming days — only days with activity or absence noise
  // are useful in a drill-down.
  const visible = days.filter((d) => d.event_count > 0 || d.status === 'absent' || d.adjusted)

  return (
    <div className="bg-slate-50 p-3 border-t border-slate-200">
      <div className="mb-2 text-[11px] text-slate-500">
        Full timeline for <span className="font-medium text-slate-700">{name}</span>
        {' '}· {from} to {to} · ignores the capture-type filter
      </div>
      {visible.length > 0 ? (
        <div className="space-y-2">
          {visible.map((d) => <DayCard key={d.date} day={d} />)}
        </div>
      ) : (
        <p className="text-xs text-slate-400 italic">No activity in this period.</p>
      )}
    </div>
  )
}

// Department → employee matrix. Each department row expands to show its
// employees; each employee row expands further to show the full drill-down.
function Matrix({ rows, from, to, deptId, roles, sources }) {
  const [openDept, setOpenDept] = useState({})
  const [openEmp, setOpenEmp] = useState({})
  const [exporting, setExporting] = useState(false)
  const [exportErr, setExportErr] = useState('')
  const toggleDept = (id) => setOpenDept((o) => ({ ...o, [id]: !o[id] }))
  const toggleEmp = (ext) => setOpenEmp((o) => ({ ...o, [ext]: !o[ext] }))

  async function onExport() {
    setExporting(true)
    setExportErr('')
    try {
      await api.exportMatrix(from, to, deptId || undefined, { roles, sources })
    } catch (e) {
      setExportErr(e.message || 'Export failed')
    } finally {
      setExporting(false)
    }
  }
  
  return (
    <div className="bg-white rounded-xl shadow-sm p-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-slate-800">Department matrix</h3>
        <button
          onClick={onExport}
          disabled={exporting}
          className="text-[11px] px-2 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
          title="Download as Excel (.xlsx) — matches current filters"
        >
          {exporting ? 'Exporting…' : '⬇ Export matrix'}
        </button>
      </div>
      {exportErr && <p className="text-[11px] text-red-600 mb-2">{exportErr}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-slate-100 text-slate-600">
            <tr>
              <th className="text-left px-2 py-1.5 font-medium">Department / Employee</th>
              <th className="text-right px-2 py-1.5 font-medium">Staff</th>
              <th className="text-right px-2 py-1.5 font-medium">Present</th>
              <th className="text-right px-2 py-1.5 font-medium">Absent</th>
              <th className="text-right px-2 py-1.5 font-medium">Attend %</th>
              <th className="text-right px-2 py-1.5 font-medium">Hours</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <FragmentRows
                key={d.key}
                d={d}
                isDeptOpen={!!openDept[d.key]}
                toggleDept={() => toggleDept(d.key)}
                openEmp={openEmp}
                toggleEmp={toggleEmp}
                from={from}
                to={to}
              />
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={6} className="text-center text-slate-400 py-4">No data.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-slate-400 mt-2 text-center">
        Click an employee to see their raw day-by-day timeline, with every event (camera, field, manual).
      </p>
    </div>
  )
}

function FragmentRows({ d, isDeptOpen, toggleDept, openEmp, toggleEmp, from, to }) {
  return (
    <>
      <tr className="border-t border-slate-100 bg-slate-50/60 cursor-pointer" onClick={toggleDept}>
        <td className="px-2 py-1.5 font-medium text-slate-800">
          <span className="inline-flex items-center justify-center w-4 h-4 mr-1.5 rounded bg-brand-red text-white text-[11px] leading-none align-middle">
            {isDeptOpen ? '−' : '+'}
          </span>
          {d.name}
        </td>
        <td className="px-2 py-1.5 text-right text-slate-700">{d.headcount}</td>
        <td className="px-2 py-1.5 text-right text-slate-700">{d.present}</td>
        <td className="px-2 py-1.5 text-right text-slate-700">{d.absent}</td>
        <td className="px-2 py-1.5 text-right text-slate-700">{d.attendance_pct}</td>
        <td className="px-2 py-1.5 text-right text-slate-700">{d.total_hours}</td>
      </tr>
      {isDeptOpen && d.employees.map((e) => {
        const isEmpOpen = !!openEmp[e.external_id]
        return (
          <FragmentEmployee
            key={e.person_id ?? e.external_id}
            e={e}
            isOpen={isEmpOpen}
            onToggle={() => toggleEmp(e.external_id)}
            from={from}
            to={to}
          />
        )
      })}
    </>
  )
}

function FragmentEmployee({ e, isOpen, onToggle, from, to }) {
  return (
    <>
      <tr
        className={`border-t border-slate-50 cursor-pointer hover:bg-slate-50 ${isOpen ? 'bg-slate-50' : ''}`}
        onClick={onToggle}
        title="Click to see the full timeline"
      >
        <td className="px-2 py-1.5 pl-8 text-slate-600">
          <span className="inline-block w-3 text-slate-400 mr-1 text-[10px]">
            {isOpen ? '▾' : '▸'}
          </span>
          {e.display_name} <span className="text-slate-400">· {e.external_id}</span>
        </td>
        <td className="px-2 py-1.5 text-right text-slate-400">—</td>
        <td className="px-2 py-1.5 text-right text-slate-600">{e.present}</td>
        <td className="px-2 py-1.5 text-right text-slate-600">{e.absent}</td>
        <td className="px-2 py-1.5 text-right text-slate-600">{e.attendance_pct}</td>
        <td className="px-2 py-1.5 text-right text-slate-600">{e.total_hours}</td>
      </tr>
      {isOpen && (
        <tr className="border-t border-slate-100">
          <td colSpan={6} className="p-0">
            <EmployeeDrilldown
              externalId={e.external_id}
              name={e.display_name}
              from={from}
              to={to}
            />
          </td>
        </tr>
      )}
    </>
  )
}

// ── Visitor Details (Phase 3, chief-only) ──────────────────────────────
// A per-event row showing the visitor's time + direction + clickable crop.
function VisitorEventRow({ event }) {
  const time = fmtTime(event.event_time)
  const direction = event.direction || 'seen'
  const sim = event.similarity != null ? ` · ${(event.similarity * 100).toFixed(0)}%` : ''
  return (
    <li className="flex items-center gap-3 py-1.5 border-t border-slate-50">
      <div className="flex-shrink-0 w-12 h-12">
        {event.crop_path ? (
          <AuthImage
            src={api.visitorCropUrl(event.id)}
            alt={`Visitor at ${time}`}
            className="w-12 h-12 rounded object-cover border border-slate-200"
            fallback={
              <div className="w-12 h-12 rounded bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-300 text-lg">
                ⋯
              </div>
            }
            zoomable
          />
        ) : (
          <div className="w-12 h-12 rounded bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-300 text-xl"
               title="Crop not available">
            👤
          </div>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-slate-800 tabular-nums">{time}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700">
            Visitor
          </span>
          <span className="text-xs text-slate-500">{direction}{sim}</span>
        </div>
        <div className="text-[11px] text-slate-400 truncate">{event.camera_label}</div>
      </div>
    </li>
  )
}

// One day's visitor events, collapsed by default. Click the header to expand.
function VisitorDayCard({ day }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="bg-white rounded-lg border border-slate-100">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 p-3 text-left hover:bg-slate-50"
      >
        <div className="flex items-center gap-2">
          <span className="text-slate-400 text-xs">{open ? '▾' : '▸'}</span>
          <span className="text-sm font-medium text-slate-700">{fmtDayLabel(day.date)}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-600 tabular-nums">
          <span>{day.total_events} visitors</span>
          <span className="text-emerald-600">↓ {day.entries} in</span>
          <span className="text-sky-600">↑ {day.exits} out</span>
        </div>
      </button>
      {open && (
        <div className="px-3 pb-3">
          {day.events.length > 0 ? (
            <ul>
              {day.events.map((e) => <VisitorEventRow key={e.id} event={e} />)}
            </ul>
          ) : (
            <p className="text-xs text-slate-400 italic pt-2">No events.</p>
          )}
        </div>
      )}
    </div>
  )
}

// Full Visitor Details matrix — the new section below the department matrix.
function VisitorMatrix({ from, to }) {
  const [days, setDays] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    let active = true
    setErr('')
    setDays(null)
    api.visitorsByDay(from, to)
      .then((d) => { if (active) setDays(d) })
      .catch((e) => { if (active) setErr(e.message) })
    return () => { active = false }
  }, [from, to])

  return (
    <div className="bg-white rounded-xl shadow-sm p-3">
      <h3 className="text-sm font-semibold text-slate-800 mb-2">Visitor details</h3>
      <p className="text-[11px] text-slate-400 mb-2">
        Every visitor the cameras caught, grouped by day. Click a day to see individual events.
      </p>
      {err && <p className="text-xs text-red-600">{err}</p>}
      {days === null && !err && (
        <p className="text-xs text-slate-400">Loading…</p>
      )}
      {days && days.length === 0 && (
        <p className="text-xs text-slate-400 italic">No visitors in this period.</p>
      )}
      {days && days.length > 0 && (
        <div className="space-y-2">
          {days.map((d) => <VisitorDayCard key={d.date} day={d} />)}
        </div>
      )}
    </div>
  )
}

export default function Analytics({ back = '/supervisor' }) {
  const { user } = useAuth()
  const isChief = user?.role === 'chief'
  const [from, setFrom] = useState(monthStart())
  const [to, setTo] = useState(istToday())
  const [granularity, setGranularity] = useState('day')
  const [deptId, setDeptId] = useState('')
  const [sources, setSources] = useState(ALL_SOURCES)
  const [roles, setRoles] = useState(DEFAULT_ROLES)
  const [depts, setDepts] = useState([])

  const [summary, setSummary] = useState(null)
  const [visitorSummary, setVisitorSummary] = useState(null)
  const [trend, setTrend] = useState([])
  const [byDept, setByDept] = useState([])
  const [byDesignation, setByDesignation] = useState([])
  const [byEmployment, setByEmployment] = useState([])
  const [split, setSplit] = useState(null)
  const [overview, setOverview] = useState([])
  const [lowest, setLowest] = useState([])
  const [error, setError] = useState('')

  const chartRefs = useRef({})
  const setChartRef = (key) => (el) => { chartRefs.current[key] = el }

  const sourcesParam = sources.length === ALL_SOURCES.length ? undefined : sources.join(',')
  const rolesParam = roles.length ? roles.join(',') : undefined

  useEffect(() => { api.departments().then(setDepts).catch(() => {}) }, [])

    const load = useCallback(async () => {
    setError('')
    const dept = deptId || undefined
    try {
      const [s, t, bd, sp, ov, lo, bdz, bet] = await Promise.all([
        api.analyticsSummary(from, to, dept, { roles: rolesParam, sources: sourcesParam }),
        api.analyticsTrend(from, to, dept, granularity, { roles: rolesParam, sources: sourcesParam }),
        api.analyticsByDepartment(from, to, { roles: rolesParam, sources: sourcesParam }),
        api.analyticsSourceSplit(from, to, dept, { roles: rolesParam, sources: sourcesParam }),
        api.supervisorOverview(from, to, dept, { roles: rolesParam, sources: sourcesParam }),
        api.analyticsLowest(from, to, dept, 8, { roles: rolesParam, sources: sourcesParam }),
        api.analyticsByAttribute('designation', from, to, dept, { roles: rolesParam, sources: sourcesParam }),
        api.analyticsByAttribute('employment_type', from, to, dept, { roles: rolesParam, sources: sourcesParam }),
      ])
      setSummary(s); setTrend(t); setByDept(bd); setSplit(sp); setOverview(ov); setLowest(lo)
      setByDesignation(bdz); setByEmployment(bet)

      // Chief-only: visitor KPIs. Safe to skip quietly for other supervisors.
      if (isChief) {
        try {
          setVisitorSummary(await api.visitorsSummary(from, to))
        } catch {
          setVisitorSummary(null)
        }
      }
    } catch (e) {
      setError(e.message)
    }
  }, [from, to, granularity, deptId, rolesParam, sourcesParam, isChief])

  useEffect(() => { load() }, [load])

  function toggleSource(v) {
    setSources((cur) => {
      const next = cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]
      return next.length === 0 ? ALL_SOURCES.slice() : next
    })
  }
  function toggleRole(v) {
    setRoles((cur) => {
      const next = cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]
      return next.length === 0 ? DEFAULT_ROLES.slice() : next
    })
  }

  const hoursByEmployee = useMemo(
    () => [...overview].sort((a, b) => b.total_hours - a.total_hours).slice(0, 12)
      .map((r) => ({ name: r.display_name, hours: r.total_hours })),
    [overview],
  )
  const splitRows = useMemo(
    () => (split ? Object.entries(split).map(([k, v]) => ({ source: k, count: v })).filter((r) => r.count > 0) : []),
    [split],
  )

  const matrix = useMemo(() => {
    const groups = new Map()
    for (const r of overview) {
      const key = r.department_id ?? 'none'
      if (!groups.has(key)) {
        groups.set(key, {
          key, name: r.department_name || '—', employees: [],
          present: 0, absent: 0, total_hours: 0,
        })
      }
      const g = groups.get(key)
      g.employees.push(r)
      g.present += r.present || 0
      g.absent += r.absent || 0
      g.total_hours += r.total_hours || 0
    }
    return [...groups.values()].map((g) => {
      const occurred = g.present + g.absent
      return {
        ...g,
        headcount: g.employees.length,
        attendance_pct: occurred ? Math.round((1000 * g.present) / occurred) / 10 : 0,
        total_hours: Math.round(g.total_hours * 10) / 10,
      }
    }).sort((a, b) => a.name.localeCompare(b.name))
  }, [overview])

  const deptName = deptId ? depts.find((d) => String(d.id) === String(deptId))?.name : null
  const filterBits = []
  if (sources.length < ALL_SOURCES.length) {
    filterBits.push(`capture: ${sources.map((s) => CAPTURE_TYPES.find(([v]) => v === s)[1]).join(', ')}`)
  }
  if (!(roles.length === DEFAULT_ROLES.length && roles.includes('employee'))) {
    filterBits.push(`role: ${roles.map((r) => ROLES.find(([v]) => v === r)[1]).join(', ')}`)
  }
  const meta = {
    title: 'Attendance Analytics',
    subtitle: `${from} to ${to}${deptName ? ` · ${deptName}` : ''}${filterBits.length ? ` · ${filterBits.join(' · ')}` : ''}`,
  }
  function collectCharts() {
    return CHART_ORDER.map(([k, t]) => ({ title: t, el: chartRefs.current[k] })).filter((c) => c.el)
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="Analytics" back={back} />
      <main className="p-4 max-w-4xl mx-auto space-y-4">
        {/* Filters */}
        <div className="bg-white rounded-xl shadow-sm p-3 space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-slate-500">From
              <input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)}
                className="mt-1 block border border-slate-300 rounded-lg px-2 py-1.5 text-sm" />
            </label>
            <label className="text-xs text-slate-500">To
              <input type="date" value={to} min={from} max={istToday()} onChange={(e) => setTo(e.target.value)}
                className="mt-1 block border border-slate-300 rounded-lg px-2 py-1.5 text-sm" />
            </label>
            {isChief && (
              <label className="text-xs text-slate-500">Department
                <select value={deptId} onChange={(e) => setDeptId(e.target.value)}
                  className="mt-1 block border border-slate-300 rounded-lg px-2 py-1.5 text-sm bg-white">
                  <option value="">All</option>
                  {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </label>
            )}
            <div className="text-xs text-slate-500">
              Group by
              <div className="mt-1 flex bg-slate-100 rounded-lg p-0.5">
                {['day', 'week', 'month'].map((g) => (
                  <button key={g} onClick={() => setGranularity(g)}
                    className={`px-3 py-1 rounded-md text-xs capitalize ${granularity === g ? 'bg-white shadow-sm font-medium text-slate-800' : 'text-slate-500'}`}>{g}</button>
                ))}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500 w-20">Capture type</span>
            {CAPTURE_TYPES.map(([val, label]) => (
              <CheckPill key={val} label={label}
                checked={sources.includes(val)} onToggle={() => toggleSource(val)} />
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500 w-20">Role</span>
            {ROLES.map(([val, label]) => (
              <CheckPill key={val} label={label}
                checked={roles.includes(val)} onToggle={() => toggleRole(val)} />
            ))}

                        <div className="ml-auto flex gap-1">
              <button onClick={() => exportDashboardPdf(collectCharts(), 'analytics.pdf', meta)}
                className="text-xs px-3 py-1.5 rounded-lg bg-brand-red text-white font-medium"
                title="Export all charts as PDF">PDF</button>
              <button onClick={() => exportDashboardPptx(collectCharts(), 'analytics.pptx', meta)}
                className="text-xs px-3 py-1.5 rounded-lg bg-slate-900 text-white font-medium"
                title="Export all charts as PowerPoint">PPT</button>
            </div>
          </div>
        </div>

        {error && <p className="text-red-600 text-sm">{error}</p>}

        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          <Kpi label="Attendance %" value={summary ? `${summary.attendance_pct}%` : '–'} tone="text-sky-600" />
          <Kpi label="Present" value={summary?.present ?? '–'} tone="text-emerald-600" />
          <Kpi label="Absent" value={summary?.absent ?? '–'} tone="text-red-600" />
          <Kpi label="Total hours" value={summary?.total_hours ?? '–'} />
          <Kpi label="Staff" value={summary?.active_employees ?? '–'} />
          <Kpi label="Field pending" value={summary?.pending_field_approvals ?? '–'} tone="text-amber-600" />
        </div>

        {/* Chief-only: visitor KPI row. */}
        {isChief && (
          <div className="grid grid-cols-3 gap-2">
            <Kpi label="Visitors" value={visitorSummary?.total_events ?? '–'} tone="text-amber-600" />
            <Kpi label="Visitor entries" value={visitorSummary?.entries ?? '–'} tone="text-emerald-600" />
            <Kpi label="Visitor exits" value={visitorSummary?.exits ?? '–'} tone="text-sky-600" />
          </div>
        )}

        <div className="grid md:grid-cols-2 gap-4">
          <ChartCard title="Attendance % trend" csvName="attendance_trend" csvRows={() => trend} innerRef={setChartRef('trend')}>
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={trend} margin={{ top: 5, right: 10, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Area type="monotone" dataKey="attendance_pct" name="Attendance %" stroke="#0ea5e9" fill="#bae6fd" />
              </AreaChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Present vs Absent" csvName="present_absent" csvRows={() => trend} innerRef={setChartRef('pa')}>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={trend} margin={{ top: 5, right: 10, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip /><Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="present" name="Present" stackId="a" fill="#22c55e" />
                <Bar dataKey="absent" name="Absent" stackId="a" fill="#ef4444" />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Attendance % by department" csvName="by_department" csvRows={() => byDept} innerRef={setChartRef('dept')}>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={byDept} margin={{ top: 5, right: 10, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="attendance_pct" name="Attendance %" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Camera vs Field vs Manual" csvName="source_split" csvRows={() => splitRows} innerRef={setChartRef('split')}>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={splitRows} dataKey="count" nameKey="source" cx="50%" cy="50%" outerRadius={90} label>
                  {splitRows.map((r) => <Cell key={r.source} fill={PIE_COLORS[r.source] || '#94a3b8'} />)}
                </Pie>
                <Tooltip /><Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Hours by employee (top 12)" csvName="hours_by_employee" csvRows={() => hoursByEmployee} innerRef={setChartRef('hours')}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={hoursByEmployee} layout="vertical" margin={{ top: 5, right: 10, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 10 }} />
                <Tooltip />
                <Bar dataKey="hours" name="Hours" fill="#0ea5e9" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Lowest attendance" csvName="lowest_attendance" csvRows={() => lowest} innerRef={setChartRef('low')}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={lowest.map((r) => ({ name: r.display_name, pct: r.attendance_pct }))}
                layout="vertical" margin={{ top: 5, right: 10, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 10 }} />
                <Tooltip />
                <Bar dataKey="pct" name="Attendance %" fill="#f59e0b" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>

               <Matrix rows={matrix} from={from} to={to}
                deptId={deptId} roles={rolesParam} sources={sourcesParam} />

        {isChief && <VisitorMatrix from={from} to={to} />}

        <div className="grid md:grid-cols-2 gap-4">
          <AttributeTable title="By designation" rows={byDesignation} csvName="by_designation" />
          <AttributeTable title="By employment type" rows={byEmployment} csvName="by_employment_type" />
        </div>

                <p className="text-[11px] text-slate-400 text-center pt-1">
          Capture type is how attendance was logged (camera / field / manual).
          Role is who the person is. Both default to showing everything.
          Export the charts (PDF / PPT), each visual (CSV / PNG), or the matrix (Export matrix button above).
        </p>
      </main>
    </div>
  )
}