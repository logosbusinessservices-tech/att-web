import { useEffect, useState } from 'react'
import AppHeader from '../components/AppHeader.jsx'
import { api } from '../lib/api.js'
import { fmtDayLabel } from '../lib/format.js'

const META = {
  password_reminder: { icon: '🔑', tone: 'bg-amber-50 border-amber-200 text-amber-800', tag: 'Password' },
  enroll_photos: { icon: '📸', tone: 'bg-sky-50 border-sky-200 text-sky-800', tag: 'Attendance photos' },
  camera_error: { icon: '📷', tone: 'bg-orange-50 border-orange-200 text-orange-800', tag: 'Camera check' },
}

export default function Notifications({ back = '/supervisor' }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.supervisorNotifications().then(setRows).catch((e) => setError(e.message))
  }, [])

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="Notifications" back={back} />
      <main className="p-4 max-w-md mx-auto space-y-3">
        {error && <p className="text-red-600 text-sm">{error}</p>}

        {rows === null ? (
          <p className="text-center text-slate-400 py-8">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="text-center text-slate-500 py-10">
            <div className="text-4xl mb-2">✓</div>
            <p className="text-sm">You're all caught up. No alerts right now.</p>
          </div>
        ) : (
          rows.map((n, i) => {
            const m = META[n.type] || { icon: '•', tone: 'bg-slate-50 border-slate-200 text-slate-700', tag: 'Alert' }
            return (
              <div key={i} className={`border rounded-xl p-3 ${m.tone}`}>
                <div className="flex items-start gap-2">
                  <span className="text-lg leading-none">{m.icon}</span>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-semibold uppercase tracking-wide opacity-70">{m.tag}</span>
                      {n.date && <span className="text-[11px] opacity-70">{fmtDayLabel(n.date)}</span>}
                    </div>
                    <p className="text-sm mt-0.5">{n.message}</p>
                    <p className="text-[11px] opacity-70 mt-0.5">{n.display_name} · {n.external_id}</p>
                  </div>
                </div>
              </div>
            )
          })
        )}

        <p className="text-xs text-slate-400 text-center pt-2">
          Alerts refresh each visit: unchanged default passwords, employees whose
          attendance photos aren't uploaded, and back-to-back entry/exit camera
          misses in your department.
        </p>
      </main>
    </div>
  )
}
