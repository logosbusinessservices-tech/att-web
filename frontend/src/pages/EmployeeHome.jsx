import AppHeader from '../components/AppHeader.jsx'
import MenuButton from '../components/MenuButton.jsx'
import { useAuth } from '../lib/auth.jsx'
import { BellIcon, CalendarIcon, CameraPinIcon, HolidayIcon, LeaveIcon, ProfileIcon } from '../components/icons.jsx'

export default function EmployeeHome() {
  const { user } = useAuth()
  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />
      <main className="p-6 max-w-md mx-auto">
        <h2 className="text-lg font-semibold text-slate-800 mb-6 text-center">
          What would you like to do?
        </h2>
        <div className="grid grid-cols-2 gap-y-8 gap-x-4 justify-items-center">
          <MenuButton icon={<CalendarIcon />} label="View My Attendance" to="/employee/attendance" />
          {user?.field_scan_enabled && (
            <MenuButton icon={<CameraPinIcon />} label="Field Attendance" to="/employee/field" />
          )}
          <MenuButton icon={<BellIcon />} label="Notifications" to="/employee/notifications" />
          <MenuButton icon={<ProfileIcon />} label="My Profile" to="/employee/profile" />
          <MenuButton icon={<LeaveIcon />} label="Apply Work From Home/Leave" to="/employee/leave" />
          <MenuButton icon={<HolidayIcon />} label="Holidays" to="/employee/holidays" />
        </div>
      </main>
    </div>
  )
}
