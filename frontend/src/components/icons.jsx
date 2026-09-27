// Simple inline SVG icons (stroke = currentColor) so they inherit button color.
const base = {
  fill: 'none',
  viewBox: '0 0 24 24',
  strokeWidth: 1.8,
  stroke: 'currentColor',
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  className: 'w-full h-full',
}

export const CalendarIcon = () => (
  <svg {...base}>
    <rect x="3" y="4.5" width="18" height="16" rx="2" />
    <path d="M3 9h18M8 2.5v4M16 2.5v4M8 13h3M8 16.5h6" />
  </svg>
)

export const CameraPinIcon = () => (
  <svg {...base}>
    <path d="M4 8.5h3l1.2-2h3.6L16 8.5h1.5A2.5 2.5 0 0 1 20 11v3" />
    <circle cx="10.5" cy="12.5" r="3" />
    <path d="M18 15c1.7 0 3 1.3 3 3 0 2-3 4.5-3 4.5S15 20 15 18c0-1.7 1.3-3 3-3Z" />
    <circle cx="18" cy="18" r="0.8" />
  </svg>
)

export const LeaveIcon = () => (
  <svg {...base}>
    <path d="M4 20V6a2 2 0 0 1 2-2h8l6 6v10a0 0 0 0 1 0 0" />
    <path d="M14 4v6h6M9 14l2 2 4-4" />
  </svg>
)

export const DashboardIcon = () => (
  <svg {...base}>
    <rect x="3" y="3" width="8" height="8" rx="1.5" />
    <rect x="13" y="3" width="8" height="5" rx="1.5" />
    <rect x="13" y="11" width="8" height="10" rx="1.5" />
    <rect x="3" y="14" width="8" height="7" rx="1.5" />
  </svg>
)

export const UploadIcon = () => (
  <svg {...base}>
    <path d="M12 15V4M8 8l4-4 4 4" />
    <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
  </svg>
)

export const ClockIcon = () => (
  <svg {...base}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
)

export const ProfileIcon = () => (
  <svg {...base}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 20c0-3.5 3.6-6 8-6s8 2.5 8 6" />
  </svg>
)

export const DisputeIcon = () => (
  <svg {...base}>
    <path d="M21 11.5a8.5 8.5 0 0 1-12.3 7.6L3 21l1.9-5.7A8.5 8.5 0 1 1 21 11.5Z" />
    <path d="M12 8v4M12 15h.01" />
  </svg>
)

export const ApprovalsIcon = () => (
  <svg {...base}>
    <path d="M9 11l3 3 8-8" />
    <path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9" />
  </svg>
)

export const HolidayIcon = () => (
  <svg {...base}>
    <rect x="3" y="4.5" width="18" height="16" rx="2" />
    <path d="M3 9h18M8 2.5v4M16 2.5v4" />
    <path d="M9 15l1.5 1.5L14 13" />
  </svg>
)

export const ExportIcon = () => (
  <svg {...base}>
    <path d="M14 3v5h5" />
    <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
    <path d="M12 18v-6M9.5 14.5 12 12l2.5 2.5" />
  </svg>
)

export const UserPlusIcon = () => (
  <svg {...base}>
    <circle cx="9" cy="8" r="4" />
    <path d="M2 20c0-3.5 3.1-6 7-6 1.3 0 2.6.3 3.6.8" />
    <path d="M18 14v6M15 17h6" />
  </svg>
)

export const BellIcon = () => (
  <svg {...base}>
    <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z" />
    <path d="M10 20a2 2 0 0 0 4 0" />
  </svg>
)

export const KeyIcon = () => (
  <svg {...base}>
    <circle cx="8" cy="8" r="4" />
    <path d="M11 11l7 7M15.5 15.5l2-2M18 18l2-2" />
  </svg>
)

export const SettingsIcon = () => (
  <svg {...base}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
  </svg>
)

export const ChartIcon = () => (
  <svg {...base}>
    <path d="M4 20V4M4 20h16" />
    <rect x="7" y="12" width="3" height="5" rx="0.5" />
    <rect x="12" y="8" width="3" height="9" rx="0.5" />
    <rect x="17" y="5" width="3" height="12" rx="0.5" />
  </svg>
)

