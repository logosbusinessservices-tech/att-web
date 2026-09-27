import { useEffect, useState } from 'react'
import AppHeader from '../components/AppHeader.jsx'
import { api } from '../lib/api.js'
import { fmtDayLabel } from '../lib/format.js'

const META = {
  field_pending: { icon: '⏳', tone: 'bg-amber-50 border-amber-200 text-amber-800', tag: 'Awaiting approval' },
  field_approved: { icon: '✅', tone: 'bg-emerald-50 border-emerald-200 text-emerald-800', tag: 'Approved' },
  field_rejected: { icon: '⛔', tone: 'bg-red-50 border-red-200 text-red-800', tag: 'Rejected' },
}

export default function Inbox({ back = '/employee' }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.myNotifications()
      .then((r) => { setRows(r); api.markNotificationsRead().catch(() => {}) })
      .catch((e) => setError(e.message))
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
            <p className="text-sm">You're all caught up. No notifications yet.</p>
          </div>
        ) : (
          rows.map((n) => {
            const m = META[n.type] || { icon: '•', tone: 'bg-slate-50 border-slate-200 text-slate-700', tag: 'Alert' }
            return (
              <div key={n.id} className={`border rounded-xl p-3 ${m.tone} ${n.is_read ? 'opacity-70' : ''}`}>
                <div className="flex items-start gap-2">
                  <span className="text-lg leading-none">{m.icon}</span>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-semibold uppercase tracking-wide opacity-70">{m.tag}</span>
                      {n.for_date && <span className="text-[11px] opacity-70">{fmtDayLabel(n.for_date)}</span>}
                    </div>
                    <p className="text-sm mt-0.5">{n.message}</p>
                  </div>
                </div>
              </div>
            )
          })
        )}
      </main>
    </div>
  )
}
