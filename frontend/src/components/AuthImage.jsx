import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'

// Renders an auth-protected image. A plain <img src> can't send the bearer
// token, so we fetch the bytes with the token, turn them into an object URL,
// and revoke it on cleanup. While loading (or on failure) we show `fallback`.
export default function AuthImage({ src, alt = '', className = '', fallback }) {
  const [url, setUrl] = useState(null)

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

  if (!url) return fallback ?? <div className={className} aria-hidden />
  return <img src={url} alt={alt} className={className} />
}
