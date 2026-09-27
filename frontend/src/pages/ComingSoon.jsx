import AppHeader from '../components/AppHeader.jsx'

// Placeholder for features not yet built.
export default function ComingSoon({ title, back }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title={title} back={back} />
      <main className="p-6 max-w-md mx-auto flex flex-col items-center justify-center text-center mt-16">
        <div className="w-20 h-20 rounded-full bg-slate-200 flex items-center justify-center text-3xl mb-4">
          🚧
        </div>
        <h2 className="text-lg font-semibold text-slate-800">{title}</h2>
        <p className="text-sm text-slate-500 mt-2">
          This feature is coming soon.
        </p>
      </main>
    </div>
  )
}
