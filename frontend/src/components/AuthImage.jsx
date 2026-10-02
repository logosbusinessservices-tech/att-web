import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'

// Renders an auth-protected image. A plain <img src> can't send the bearer
// token, so we fetch the bytes with the token, turn them into an object URL,
// and revoke it on cleanup. While loading (or on failure) we show `fallback`.
// Pass `zoomable` to let the user click the image to inspect it full-screen.
export default function AuthImage({ src, alt = '', className = '', fallback, zoomable = false }) {
  const [url, setUrl] = useState(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!src) { setUrl(null); return }
    let active = true
    let objUrl = null
    setUrl(null)
    api.blobUrl(src)
      .then((u) => {
        if (active) { objUrl = u; setUrl(u) }
        else URL.revokeObjectURL(u)
      })
      .catch(() => { if (active) setUrl(null) })
    return () => { active = false; if (objUrl) URL.revokeObjectURL(objUrl) }
  }, [src])

  // Close the lightbox on Escape.
  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  if (!url) return fallback ?? <div className={className} aria-hidden />

  if (!zoomable) return <img src={url} alt={alt} className={className} />

  return (
    <>
      <img
        src={url} alt={alt}
        className={`${className} cursor-zoom-in`}
        onClick={() => setOpen(true)}
      />
      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => setOpen(false)}
        >
          <img
            src={url} alt={alt}
            className="max-w-full max-h-full object-contain rounded-lg cursor-zoom-out"
          />
          <button
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/90 text-slate-900 text-xl font-semibold flex items-center justify-center"
          >
            ✕
          </button>
        </div>
      )}
    </>
  )
}
