import { useEffect, useMemo, useRef, useState } from 'react'

// A compact "Filter by" control with two levels:
//   level 1  →  choose Department or Employee (or clear to All)
//   level 2  →  a text-searchable list of departments or employees
//
// value: '' | `dept:<id>` | `emp:<externalId>`
// allowDept: when false the Department level is hidden (e.g. a supervisor locked
// to their own department, who should not see a cross-department filter).
// allLabel: text shown for the empty (unfiltered) selection.
export default function FilterPicker({ depts, people, value, onChange, allowDept = true, allLabel = 'All departments' }) {
  const [open, setOpen] = useState(false)
  const [level, setLevel] = useState('root') // root | dept | emp
  const [q, setQ] = useState('')
  const ref = useRef(null)

  // Close on outside click.
  useEffect(() => {
    function onDoc(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  // Reset to the root level whenever the panel is opened.
  useEffect(() => {
    if (open) { setLevel('root'); setQ('') }
  }, [open])

  const label = useMemo(() => {
    if (value.startsWith('dept:')) {
      const d = depts.find((x) => String(x.id) === value.slice(5))
      return d ? d.name : 'Department'
    }
    if (value.startsWith('emp:')) {
      const p = people.find((x) => x.external_id === value.slice(4))
      return p ? p.display_name : 'Employee'
    }
    return allLabel
  }, [value, depts, people, allLabel])

  const deptName = (id) => depts.find((d) => String(d.id) === String(id))?.name

  const filteredDepts = useMemo(() => {
    const s = q.trim().toLowerCase()
    return depts.filter((d) => !s || d.name.toLowerCase().includes(s))
  }, [depts, q])

  const filteredPeople = useMemo(() => {
    const s = q.trim().toLowerCase()
    return people.filter((p) => {
      if (!s) return true
      return (
        p.display_name.toLowerCase().includes(s) ||
        p.external_id.toLowerCase().includes(s) ||
        (deptName(p.department_id) || '').toLowerCase().includes(s)
      )
    })
  }, [people, q]) // eslint-disable-line react-hooks/exhaustive-deps

  function pick(v) {
    onChange(v)
    setOpen(false)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 border border-slate-300 rounded-lg px-3 py-1.5 text-sm bg-white max-w-[13rem]"
      >
        <span className="text-slate-400 text-xs">Filter by</span>
        <span className="font-medium text-slate-800 truncate">{label}</span>
        <span className="text-slate-400">▾</span>
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-1 w-64 bg-white border border-slate-200 rounded-xl shadow-lg overflow-hidden">
          {level === 'root' && (
            <ul className="py-1 text-sm">
              <li>
                <button onClick={() => pick('')}
                  className="w-full text-left px-3 py-2 hover:bg-slate-50 text-slate-700">
                  {allLabel}
                </button>
              </li>
              {allowDept && (
                <li>
                  <button onClick={() => { setLevel('dept'); setQ('') }}
                    className="w-full text-left px-3 py-2 hover:bg-slate-50 flex items-center justify-between">
                    <span>Department</span><span className="text-slate-400">›</span>
                  </button>
                </li>
              )}
              <li>
                <button onClick={() => { setLevel('emp'); setQ('') }}
                  className="w-full text-left px-3 py-2 hover:bg-slate-50 flex items-center justify-between">
                  <span>Employee</span><span className="text-slate-400">›</span>
                </button>
              </li>
            </ul>
          )}

          {level !== 'root' && (
            <div>
              <div className="flex items-center gap-2 px-2 py-2 border-b border-slate-100">
                <button onClick={() => setLevel('root')} className="text-slate-400 px-1">‹</button>
                <input
                  autoFocus
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder={level === 'dept' ? 'Search departments…' : 'Search employees…'}
                  className="flex-1 text-sm outline-none"
                />
              </div>
              <ul className="max-h-60 overflow-y-auto py-1 text-sm">
                {level === 'dept' && filteredDepts.map((d) => (
                  <li key={d.id}>
                    <button onClick={() => pick(`dept:${d.id}`)}
                      className="w-full text-left px-3 py-2 hover:bg-slate-50 text-slate-700">
                      {d.name}
                    </button>
                  </li>
                ))}
                {level === 'dept' && filteredDepts.length === 0 && (
                  <li className="px-3 py-2 text-slate-400">No departments.</li>
                )}

                {level === 'emp' && filteredPeople.map((p) => (
                  <li key={p.external_id}>
                    <button onClick={() => pick(`emp:${p.external_id}`)}
                      className="w-full text-left px-3 py-2 hover:bg-slate-50">
                      <div className="text-slate-800">{p.display_name}</div>
                      <div className="text-[11px] text-slate-400">
                        {p.external_id}{p.department_id ? ` · ${deptName(p.department_id)}` : ''}
                      </div>
                    </button>
                  </li>
                ))}
                {level === 'emp' && filteredPeople.length === 0 && (
                  <li className="px-3 py-2 text-slate-400">No employees.</li>
                )}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
