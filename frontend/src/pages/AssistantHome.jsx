import AppHeader from '../components/AppHeader.jsx'
import MenuButton from '../components/MenuButton.jsx'
import { useAuth } from '../lib/auth.jsx'
import {
  ApprovalsIcon, BellIcon, CalendarIcon, DashboardIcon, HolidayIcon, LeaveIcon, ProfileIcon,
} from '../components/icons.jsx'

export default function AssistantHome() {
  const { user } = useAuth()
  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />
      <main className="p-6 max-w-md mx-auto">
        <h2 className="text-lg font-semibold text-slate-800 mb-1 text-center">
          Executive Assistant
        </h2>
        {user?.manager_name && (
          <p className="text-center text-xs text-slate-500 mb-6">
            Assisting {user.manager_name}
            {user.manager_external_id ? ` · ${user.manager_external_id}` : ''}
          </p>
        )}
        <div className="grid grid-cols-2 gap-y-8 gap-x-4 justify-items-center">
          <MenuButton icon={<ApprovalsIcon />} label="Approve Sign-ups" to="/assistant/signups" />
          <MenuButton icon={<ProfileIcon />} label="Manage Accounts" to="/assistant/accounts" />
          <MenuButton icon={<DashboardIcon />} label="Delegated Tasks" to="/assistant/tasks" />
          <MenuButton icon={<CalendarIcon />} label="View My Attendance" to="/assistant/attendance" />
          <MenuButton icon={<BellIcon />} label="Notifications" to="/assistant/notifications" />
          <MenuButton icon={<ProfileIcon />} label="My Profile" to="/assistant/profile" />
          <MenuButton icon={<LeaveIcon />} label="Apply Work From Home/Leave" to="/assistant/leave" />
          <MenuButton icon={<HolidayIcon />} label="Holidays" to="/assistant/holidays" />
        </div>
      </main>
    </div>
  )
}
