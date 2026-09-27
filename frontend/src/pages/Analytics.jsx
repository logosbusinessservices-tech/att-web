import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts'
import AppHeader from '../components/AppHeader.jsx'
import { api } from '../lib/api.js'
import { useAuth } from '../lib/auth.jsx'
import { downloadCsv, exportChartPng, exportDashboardPdf, exportDashboardPptx, exportMatrixXls } from '../lib/exporters.js'

function istToday() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date())
}
function monthStart() {
  const [y, m] = istToday().split('-')
  return `${y}-${m}-01`
}

const PIE_COLORS = { camera: '#3b82f6', field: '#10b981', manual: '#a855f7' }
const TYPE_OPTIONS = [['field', 'Field'], ['supervisor', 'Supervisors'], ['office', 'Office']]
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

// Department → employee matrix. Each department row expands (+) to reveal its
// employees. Aggregates are summed from the employee rollups so it always
// reflects the active filters.
function Matrix({ rows }) {
  const [open, setOpen] = useState({})
  const toggle = (id) => setOpen((o) => ({ ...o, [id]: !o[id] }))
  return (
    <div className="bg-white rounded-xl shadow-sm p-3">
      <h3 className="text-sm font-semibold text-slate-800 mb-2">Department matrix</h3>
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
            {rows.map((d) => {
              const isOpen = !!open[d.key]
              return (
                <FragmentRows key={d.key} d={d} isOpen={isOpen} toggle={() => toggle(d.key)} />
              )
            })}
            {rows.length === 0 && (
              <tr><td colSpan={6} className="text-center text-slate-400 py-4">No data.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function FragmentRows({ d, isOpen, toggle }) {
  return (
    <>
      <tr className="border-t border-slate-100 bg-slate-50/60 cursor-pointer" onClick={toggle}>
        <td className="px-2 py-1.5 font-medium text-slate-800">
          <span className="inline-flex items-center justify-center w-4 h-4 mr-1.5 rounded bg-brand-red text-white text-[11px] leading-none align-middle">
            {isOpen ? '−' : '+'}
          </span>
          {d.name}
        </td>
        <td className="px-2 py-1.5 text-right text-slate-700">{d.headcount}</td>
        <td className="px-2 py-1.5 text-right text-slate-700">{d.present}</td>
        <td className="px-2 py-1.5 text-right text-slate-700">{d.absent}</td>
        <td className="px-2 py-1.5 text-right text-slate-700">{d.attendance_pct}</td>
        <td className="px-2 py-1.5 text-right text-slate-700">{d.total_hours}</td>
      </tr>
      {isOpen && d.employees.map((e) => (
        <tr key={e.person_id ?? e.external_id} className="border-t border-slate-50">
          <td className="px-2 py-1.5 pl-8 text-slate-600">
            {e.display_name} <span className="text-slate-400">· {e.external_id}</span>
          </td>
          <td className="px-2 py-1.5 text-right text-slate-400">—</td>
          <td className="px-2 py-1.5 text-right text-slate-600">{e.present}</td>
          <td className="px-2 py-1.5 text-right text-slate-600">{e.absent}</td>
          <td className="px-2 py-1.5 text-right text-slate-600">{e.attendance_pct}</td>
          <td className="px-2 py-1.5 text-right text-slate-600">{e.total_hours}</td>
        </tr>
      ))}
    </>
  )
}

export default function Analytics({ back = '/supervisor' }) {
  const { user } = useAuth()
  const isChief = user?.role === 'chief'
  const [from, setFrom] = useState(monthStart())
  const [to, setTo] = useState(istToday())
  const [granularity, setGranularity] = useState('day')
  const [deptId, setDeptId] = useState('')
  const [types, setTypes] = useState([])   // [] = all employees
  const [depts, setDepts] = useState([])

  const [summary, setSummary] = useState(null)
  const [trend, setTrend] = useState([])
  const [byDept, setByDept] = useState([])
  const [split, setSplit] = useState(null)
  const [overview, setOverview] = useState([])
  const [lowest, setLowest] = useState([])
  const [error, setError] = useState('')

  const chartRefs = useRef({})
  const setChartRef = (key) => (el) => { chartRefs.current[key] = el }

  const typesParam = types.length ? types.join(',') : undefined

  useEffect(() => { api.departments().then(setDepts).catch(() => {}) }, [])

  const load = useCallback(async () => {
    setError('')
    const dept = deptId || undefined
    try {
      const [s, t, bd, sp, ov, lo] = await Promise.all([
        api.analyticsSummary(from, to, dept, typesParam),
        api.analyticsTrend(from, to, dept, granularity, typesParam),
        api.analyticsByDepartment(from, to, typesParam),
        api.analyticsSourceSplit(from, to, dept, typesParam),
        api.supervisorOverview(from, to, dept, typesParam),
        api.analyticsLowest(from, to, dept, 8, typesParam),
      ])
      setSummary(s); setTrend(t); setByDept(bd); setSplit(sp); setOverview(ov); setLowest(lo)
    } catch (e) {
      setError(e.message)
    }
  }, [from, to, granularity, deptId, typesParam])

  useEffect(() => { load() }, [load])

  function toggleType(t) {
    setTypes((cur) => cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t])
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

  // Group the employee rollups by department for the drill-down matrix.
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
  const meta = {
    title: 'Attendance Analytics',
    subtitle: `${from} to ${to}${deptName ? ` · ${deptName}` : ''}${types.length ? ` · ${types.join(', ')}` : ''}`,
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

          {/* Staff-type multiselect */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500">Staff type</span>
            <button onClick={() => setTypes([])}
              className={`text-xs px-3 py-1 rounded-full border ${types.length === 0 ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-600 border-slate-300'}`}>All</button>
            {TYPE_OPTIONS.map(([val, label]) => (
              <button key={val} onClick={() => toggleType(val)}
                className={`text-xs px-3 py-1 rounded-full border ${types.includes(val) ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white text-slate-600 border-slate-300'}`}>{label}</button>
            ))}

            {/* Export all */}
            <div className="ml-auto flex gap-1">
              <button onClick={() => exportMatrixXls(matrix, 'analytics.xls', meta)}
                className="text-xs px-3 py-1.5 rounded-lg bg-emerald-600 text-white font-medium">Excel</button>
              <button onClick={() => exportDashboardPdf(collectCharts(), 'analytics.pdf', meta)}
                className="text-xs px-3 py-1.5 rounded-lg bg-brand-red text-white font-medium">PDF</button>
              <button onClick={() => exportDashboardPptx(collectCharts(), 'analytics.pptx', meta)}
                className="text-xs px-3 py-1.5 rounded-lg bg-slate-900 text-white font-medium">PPT</button>
            </div>
          </div>
        </div>

        {error && <p className="text-red-600 text-sm">{error}</p>}

        {/* KPIs — react to every filter incl. staff type */}
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          <Kpi label="Attendance %" value={summary ? `${summary.attendance_pct}%` : '–'} tone="text-sky-600" />
          <Kpi label="Present" value={summary?.present ?? '–'} tone="text-emerald-600" />
          <Kpi label="Absent" value={summary?.absent ?? '–'} tone="text-red-600" />
          <Kpi label="Total hours" value={summary?.total_hours ?? '–'} />
          <Kpi label="Staff" value={summary?.active_employees ?? '–'} />
          <Kpi label="Field pending" value={summary?.pending_field_approvals ?? '–'} tone="text-amber-600" />
        </div>

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

          <Matrix rows={matrix} />

        <p className="text-[11px] text-slate-400 text-center pt-1">
          Filter by department + staff type. Export the charts (PDF / PPT), each visual (CSV / PNG),
          or the department matrix (Excel).
        </p>
      </main>
    </div>
  )
}
