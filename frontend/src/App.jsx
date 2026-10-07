import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './lib/auth.jsx'
import Login from './pages/Login.jsx'
import Signup from './pages/Signup.jsx'
import SignupApprovals from './pages/SignupApprovals.jsx'
import EmployeeHome from './pages/EmployeeHome.jsx'
import SupervisorHome from './pages/SupervisorHome.jsx'
import AssistantHome from './pages/AssistantHome.jsx'
import DelegatedTasks from './pages/DelegatedTasks.jsx'
import EmployeeDashboard from './pages/EmployeeDashboard.jsx'
import SupervisorDashboard from './pages/SupervisorDashboard.jsx'
import ComingSoon from './pages/ComingSoon.jsx'
import Profile from './pages/Profile.jsx'
import Notifications from './pages/Notifications.jsx'
import ChangePassword from './pages/ChangePassword.jsx'
import FieldAttendance from './pages/FieldAttendance.jsx'
import FieldApprovals from './pages/FieldApprovals.jsx'
import EmployeeSettings from './pages/EmployeeSettings.jsx'
import ManageAccounts from './pages/ManageAccounts.jsx'
import DisplayMessages from './pages/DisplayMessages.jsx'
import Inbox from './pages/Inbox.jsx'
// Charts (recharts) are heavy; load the Analytics page only when opened.
const Analytics = lazy(() => import('./pages/Analytics.jsx'))

function Protected({ children, role }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="p-8 text-center text-slate-500">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  // The chief manager has supervisor-level access to all supervisor screens.
  const ok = !role || user.role === role || (role === 'supervisor' && user.role === 'chief')
  if (!ok) return <Navigate to="/" replace />
  return children
}

function Home() {
  const { user, loading } = useAuth()
  if (loading) return null
  if (!user) return <Navigate to="/login" replace />
  const dest =
    user.role === 'supervisor' || user.role === 'chief' ? '/supervisor'
    : user.role === 'assistant' ? '/assistant'
    : '/employee'
  return <Navigate to={dest} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />

      {/* ── Employee ── */}
      <Route path="/employee" element={<Protected role="employee"><EmployeeHome /></Protected>} />
      <Route
        path="/employee/attendance"
        element={<Protected role="employee"><EmployeeDashboard back="/employee" /></Protected>}
      />
      <Route
        path="/employee/field"
        element={<Protected role="employee"><FieldAttendance back="/employee" /></Protected>}
      />
      <Route
        path="/employee/leave"
        element={<Protected role="employee"><ComingSoon title="Apply Work From Home / Leave" back="/employee" /></Protected>}
      />
      <Route
        path="/employee/profile"
        element={<Protected role="employee"><Profile back="/employee" /></Protected>}
      />
      <Route
        path="/employee/change-password"
        element={<Protected role="employee"><ChangePassword back="/employee" /></Protected>}
      />
      <Route
        path="/employee/notifications"
        element={<Protected role="employee"><Inbox back="/employee" /></Protected>}
      />
      <Route
        path="/employee/holidays"
        element={<Protected role="employee"><ComingSoon title="Holidays" back="/employee" /></Protected>}
      />

      {/* ── Supervisor ── */}
      <Route path="/supervisor" element={<Protected role="supervisor"><SupervisorHome /></Protected>} />
      <Route
        path="/supervisor/attendance"
        element={<Protected role="supervisor"><EmployeeDashboard back="/supervisor" /></Protected>}
      />
      <Route
        path="/supervisor/field"
        element={<Protected role="supervisor"><FieldAttendance back="/supervisor" /></Protected>}
      />
      <Route
        path="/supervisor/leave"
        element={<Protected role="supervisor"><ComingSoon title="Apply Work From Home / Leave" back="/supervisor" /></Protected>}
      />
      <Route
        path="/supervisor/dashboards"
        element={<Protected role="supervisor"><SupervisorDashboard back="/supervisor" /></Protected>}
      />
      <Route
        path="/supervisor/analytics"
        element={<Protected role="supervisor"><Suspense fallback={<div className="p-8 text-center text-slate-500">Loading charts…</div>}><Analytics back="/supervisor" /></Suspense></Protected>}
      />
      <Route
        path="/supervisor/notifications"
        element={<Protected role="supervisor"><Notifications back="/supervisor" /></Protected>}
      />
      <Route
        path="/supervisor/field-approvals"
        element={<Protected role="supervisor"><FieldApprovals back="/supervisor" /></Protected>}
      />
      <Route
        path="/supervisor/employee-settings"
        element={<Protected role="supervisor"><EmployeeSettings back="/supervisor" /></Protected>}
      />
      <Route
        path="/supervisor/change-password"
        element={<Protected role="supervisor"><ChangePassword back="/supervisor" /></Protected>}
      />
      <Route
        path="/supervisor/profile"
        element={<Protected role="supervisor"><Profile back="/supervisor" /></Protected>}
      />
      <Route
        path="/supervisor/holidays"
        element={<Protected role="supervisor"><ComingSoon title="Holidays" back="/supervisor" /></Protected>}
      />

      {/* ── Executive Assistant ── */}
      <Route path="/assistant" element={<Protected role="assistant"><AssistantHome /></Protected>} />
      <Route
        path="/assistant/attendance"
        element={<Protected role="assistant"><EmployeeDashboard back="/assistant" /></Protected>}
      />
      <Route
        path="/assistant/signups"
        element={<Protected role="assistant"><SignupApprovals back="/assistant" /></Protected>}
      />
      <Route
        path="/assistant/accounts"
        element={<Protected role="assistant"><ManageAccounts back="/assistant" /></Protected>}
      />
      <Route
        path="/assistant/tasks"
        element={<Protected role="assistant"><DelegatedTasks back="/assistant" /></Protected>}
      />
      <Route
        path="/assistant/profile"
        element={<Protected role="assistant"><Profile back="/assistant" /></Protected>}
      />
      <Route
        path="/assistant/change-password"
        element={<Protected role="assistant"><ChangePassword back="/assistant" /></Protected>}
      />
      <Route
        path="/assistant/notifications"
        element={<Protected role="assistant"><Inbox back="/assistant" /></Protected>}
      />
      <Route
        path="/assistant/leave"
        element={<Protected role="assistant"><ComingSoon title="Apply Work From Home / Leave" back="/assistant" /></Protected>}
      />
      <Route
        path="/assistant/holidays"
        element={<Protected role="assistant"><ComingSoon title="Holidays" back="/assistant" /></Protected>}
      />
      <Route
        path="/assistant/display-messages"
        element={<Protected role="assistant"><DisplayMessages back="/assistant" /></Protected>}
      />
    </Routes>
  )
}
