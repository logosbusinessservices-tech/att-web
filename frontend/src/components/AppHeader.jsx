import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth.jsx'

// Reusable top bar. Shows user, optional back button, and sign out.
export default function AppHeader({ title, back }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const onChangePwPage = location.pathname.endsWith('/change-password')
  return (
    <>
      <header className="bg-slate-900 text-white px-4 py-3 flex items-center gap-3">
        <img src="/logo.svg" alt="RVNL" className="h-7 w-auto rounded bg-white/90 px-1.5 py-1 shrink-0" />
        {back && (
          <button onClick={() => navigate(back)} aria-label="Back" className="text-xl leading-none px-1">
            ‹
          </button>
        )}
        <div className="flex-1 min-w-0">
          <div className="font-semibold truncate">{title ?? user?.display_name}</div>
          <div className="text-xs text-slate-300 truncate">
            {user?.role === 'supervisor' ? 'Supervisor'
              : user?.role === 'chief' ? 'Chief Manager'
              : user?.role === 'assistant' ? 'Executive Assistant'
              : 'Employee'} · {user?.external_id}
          </div>
        </div>
        <button onClick={logout} className="text-sm underline shrink-0">Sign out</button>
      </header>

      {user?.must_change_password && !onChangePwPage && (
        <div className="bg-amber-100 text-amber-900 px-4 py-2 text-sm flex items-center justify-between gap-3">
          <span>You're using your default password. Please change it.</span>
          <button
            onClick={() => navigate(`/${user.role === 'supervisor' || user.role === 'chief' ? 'supervisor' : user.role === 'assistant' ? 'assistant' : 'employee'}/change-password`)}
            className="shrink-0 bg-amber-600 text-white text-xs font-medium px-3 py-1.5 rounded-lg"
          >
            Change now
          </button>
        </div>
      )}

      {user?.needs_attendance_photos && (
        <div className="bg-sky-100 text-sky-900 px-4 py-2 text-sm">
          Your attendance photos haven't been uploaded yet. Please ask your supervisor
          to take them within 3 days of activation.
        </div>
      )}
    </>
  )
}
