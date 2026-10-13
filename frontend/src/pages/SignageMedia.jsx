import { useCallback, useEffect, useRef, useState } from 'react'
import AppHeader from '../components/AppHeader.jsx'
import { api } from '../lib/api.js'

const MAX_SLIDES = 8
const MAX_MB = 100
const ACCEPT = 'image/jpeg,image/png,video/mp4'

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function MediaPreview({ item, token }) {
  const src = api.signageMediaPreviewUrl(item.id)
  const headers = token ? { Authorization: `Bearer ${token}` } : {}

  if (item.media_type === 'video') {
    return (
      <video
        className="w-full h-32 object-contain rounded-lg bg-black"
        muted
        preload="metadata"
        onLoadStart={(e) => {
          // Videos loaded via src won't send auth headers, so we use a blob URL
        }}
        ref={(el) => {
          if (!el || el.dataset.loaded === String(item.id)) return
          el.dataset.loaded = String(item.id)
          fetch(src, { headers })
            .then((r) => r.blob())
            .then((blob) => { el.src = URL.createObjectURL(blob) })
            .catch(() => {})
        }}
      />
    )
  }

  return (
    <img
      alt={item.original_filename}
      className="w-full h-32 object-contain rounded-lg bg-slate-100"
      ref={(el) => {
        if (!el || el.dataset.loaded === String(item.id)) return
        el.dataset.loaded = String(item.id)
        fetch(src, { headers })
          .then((r) => r.blob())
          .then((blob) => { el.src = URL.createObjectURL(blob) })
          .catch(() => {})
      }}
    />
  )
}

function MediaRow({ item, index, total, busy, onMove, onRemove, token }) {
  return (
    <li className="bg-white rounded-xl shadow-sm p-3 space-y-2">
      <MediaPreview item={item} token={token} />
      <div className="flex items-center gap-2">
        <div className="flex flex-col shrink-0">
          <button onClick={() => onMove(index, -1)} disabled={busy || index === 0}
            aria-label="Move up"
            className="text-slate-500 leading-none px-1.5 py-0.5 rounded hover:bg-slate-100 disabled:opacity-25">▲</button>
          <button onClick={() => onMove(index, 1)} disabled={busy || index === total - 1}
            aria-label="Move down"
            className="text-slate-500 leading-none px-1.5 py-0.5 rounded hover:bg-slate-100 disabled:opacity-25">▼</button>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-slate-800 truncate">{item.original_filename}</p>
          <p className="text-xs text-slate-400">
            {item.media_type === 'video' ? '🎬 Video' : '🖼️ Image'} · {formatSize(item.file_size)}
          </p>
        </div>
        <button onClick={() => onRemove(item)} disabled={busy}
          aria-label="Remove"
          className="text-slate-400 hover:text-red-600 text-xl leading-none px-1 shrink-0 disabled:opacity-50">×</button>
      </div>
    </li>
  )
}

export default function SignageMedia({ back = '/assistant' }) {
  const [items, setItems] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef(null)
  const token = localStorage.getItem('token')

  const load = useCallback(async () => {
    try { setItems(await api.signageMedia()) } catch (e) { setError(e.message) }
  }, [])

  useEffect(() => { load() }, [load])

  async function run(action) {
    setBusy(true); setError('')
    try {
      await action()
      return true
    } catch (e) {
      setError(e.message)
      await load()
      return false
    } finally {
      setBusy(false)
    }
  }

  const full = items !== null && items.length >= MAX_SLIDES

  async function handleUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    // Reset so the same file can be re-selected
    if (fileRef.current) fileRef.current.value = ''

    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`File is too large (${formatSize(file.size)}). Maximum is ${MAX_MB} MB.`)
      return
    }

    setUploading(true); setError('')
    try {
      const created = await api.uploadSignageMedia(file)
      setItems((list) => [...(list || []), created])
    } catch (e) {
      setError(e.message)
      await load()
    } finally {
      setUploading(false)
    }
  }

  function remove(item) {
    if (!window.confirm(`Remove "${item.original_filename}" from the gate screens?`)) return
    run(async () => {
      await api.removeSignageMedia(item.id)
      setItems((list) => list.filter((m) => m.id !== item.id))
    })
  }

  function move(index, delta) {
    const ids = items.map((m) => m.id)
    const target = index + delta
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    run(async () => setItems(await api.reorderSignageMedia(ids)))
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="Signage Media" back={back} />
      <main className="p-4 max-w-md mx-auto space-y-3">
        <p className="text-xs text-slate-500">
          Upload images (JPG, PNG) or videos (MP4) to display on the gate screens.
          Each image shows for 10 seconds; videos play to the end. Up to {MAX_SLIDES} slides,
          {MAX_MB} MB each. Changes sync within about a minute.
        </p>

        {/* Upload button */}
        <div className="bg-white rounded-xl shadow-sm p-3">
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT}
            onChange={handleUpload}
            disabled={full || uploading || busy}
            className="hidden"
            id="media-upload"
          />
          <label
            htmlFor="media-upload"
            className={`block w-full text-center py-3 rounded-lg text-sm font-medium cursor-pointer transition
              ${full || uploading || busy
                ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                : 'bg-brand-red text-white hover:bg-red-700'}`}
          >
            {uploading ? 'Uploading…' : full ? `Slide limit reached (${MAX_SLIDES})` : '+ Upload Image or Video'}
          </label>
        </div>

        {error && <p className="text-red-600 text-sm">{error}</p>}

        {items === null ? (
          <p className="text-center text-slate-400 py-8">Loading…</p>
        ) : items.length === 0 ? (
          <div className="text-center text-slate-500 py-10">
            <p className="text-sm">No media slides. Only the welcome page and announcements are shown.</p>
          </div>
        ) : (
          <>
            <div className="text-xs text-slate-400">
              {items.length} of {MAX_SLIDES} slides
            </div>
            <ol className="space-y-2">
              {items.map((item, i) => (
                <MediaRow key={item.id} item={item} index={i} total={items.length}
                  busy={busy || uploading} onMove={move} onRemove={remove} token={token} />
              ))}
            </ol>
          </>
        )}
      </main>
    </div>
  )
}
