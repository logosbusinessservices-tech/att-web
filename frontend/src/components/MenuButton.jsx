import { useNavigate } from 'react-router-dom'

// A large, round, tappable menu button with an icon and readable label.
// All menu icons use the brand red for a consistent look.
export default function MenuButton({ icon, label, to, onClick }) {
  const navigate = useNavigate()
  return (
    <button
      onClick={onClick ?? (() => navigate(to))}
      className="flex flex-col items-center gap-3 focus:outline-none group"
    >
      <span
        className="bg-brand-red text-white w-24 h-24 sm:w-28 sm:h-28 rounded-full flex items-center justify-center shadow-lg transition-transform group-active:scale-95 group-hover:scale-105"
      >
        <span className="w-11 h-11 sm:w-12 sm:h-12">{icon}</span>
      </span>
      <span className="text-sm sm:text-base font-medium text-slate-700 text-center max-w-[7rem] leading-tight">
        {label}
      </span>
    </button>
  )
}
