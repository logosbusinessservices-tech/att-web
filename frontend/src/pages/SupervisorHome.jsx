import AppHeader from '../components/AppHeader.jsx'
import MenuButton from '../components/MenuButton.jsx'
import { useAuth } from '../lib/auth.jsx'
import {
  ApprovalsIcon, BellIcon, CalendarIcon, ChartIcon, DashboardIcon,
  HolidayIcon, LeaveIcon, ProfileIcon, SettingsIcon, UploadIcon,
} from '../components/icons.jsx'

export default function SupervisorHome() {
  const { user } = useAuth()
  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />
      <main className="p-6 max-w-md mx-auto">
        <h2 className="text-lg font-semibold text-slate-800 mb-6 text-center">
          Supervisor menu
        </h2>
        <div className="grid grid-cols-2 gap-y-8 gap-x-4 justify-items-center">
          <MenuButton icon={<CalendarIcon />} label="View My Attendance" to="/supervisor/attendance" />
          {user?.field_scan_enabled && (
            <MenuButton icon={<UploadIcon />} label="Field Attendance" to="/supervisor/field" />
          )}
          <MenuButton icon={<DashboardIcon />} label="Employee Attendance" to="/supervisor/dashboards" />
          <MenuButton icon={<ChartIcon />} label="Analytics" to="/supervisor/analytics" />
          <MenuButton icon={<ApprovalsIcon />} label="Field Approvals" to="/supervisor/field-approvals" />
          <MenuButton icon={<SettingsIcon />} label="Employee Settings" to="/supervisor/employee-settings" />
          <MenuButton icon={<BellIcon />} label="Notifications" to="/supervisor/notifications" />
          <MenuButton icon={<ProfileIcon />} label="My Profile" to="/supervisor/profile" />
          <MenuButton icon={<LeaveIcon />} label="Apply Work From Home/Leave" to="/supervisor/leave" />
          <MenuButton icon={<HolidayIcon />} label="Holidays" to="/supervisor/holidays" />
        </div>
      </main>
    </div>
  )
}
