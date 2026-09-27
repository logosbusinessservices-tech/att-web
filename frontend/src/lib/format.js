// Date/time formatting helpers. Storage is UTC; we always render in IST.
const IST = 'Asia/Kolkata'

const timeFmt = new Intl.DateTimeFormat('en-IN', {
  timeZone: IST, hour: '2-digit', minute: '2-digit',
})
const dayFmt = new Intl.DateTimeFormat('en-IN', {
  timeZone: IST, weekday: 'short', day: '2-digit', month: 'short',
})

export function fmtTime(iso) {
  if (!iso) return '—'
  return timeFmt.format(new Date(asUtc(iso)))
}

// Backend stores naive UTC. If a timestamp arrives without a timezone offset,
// JS `new Date()` would treat it as LOCAL time (wrong). Tag bare strings as UTC.
function asUtc(iso) {
  if (typeof iso !== 'string') return iso
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso)
  return hasTz ? iso : `${iso}Z`
}

// A summary's `date` is an IST calendar date string (YYYY-MM-DD); render it directly.
export function fmtDayLabel(isoDate) {
  const [y, m, d] = isoDate.split('-').map(Number)
  return dayFmt.format(new Date(Date.UTC(y, m - 1, d, 6))) // noon-ish IST, avoids TZ rollover
}

export function fmtHours(h) {
  if (!h) return '0h'
  const hours = Math.floor(h)
  const mins = Math.round((h - hours) * 60)
  return mins ? `${hours}h ${mins}m` : `${hours}h`
}

const STATUS_STYLES = {
  present: 'bg-emerald-50 text-emerald-700',
  absent: 'bg-red-50 text-red-700',
  weekend: 'bg-slate-100 text-slate-500',
  upcoming: 'bg-slate-50 text-slate-400',
}

export function statusClass(status) {
  return STATUS_STYLES[status] ?? 'bg-slate-100 text-slate-600'
}

export function statusLabel(status) {
  return {
    present: 'Present', absent: 'Absent',
    weekend: 'Weekend', upcoming: 'Upcoming',
  }[status] ?? status
}

const DISPUTE_STYLES = {
  open: 'bg-amber-50 text-amber-700',
  under_review: 'bg-sky-50 text-sky-700',
  resolved: 'bg-emerald-50 text-emerald-700',
  rejected: 'bg-red-50 text-red-700',
}

export function disputeClass(status) {
  return DISPUTE_STYLES[status] ?? 'bg-slate-100 text-slate-600'
}

export function disputeLabel(status) {
  return {
    open: 'Open', under_review: 'Under review',
    resolved: 'Resolved', rejected: 'Rejected',
  }[status] ?? status
}
