import { useCallback, useEffect, useState } from 'react'
import AppHeader from '../components/AppHeader.jsx'
import { api } from '../lib/api.js'

// Mirrors the backend limits (display_message_max_chars / _max_count); the
// server enforces them, these only drive the counter and disabled states.
const MAX_CHARS = 150
const MAX_MESSAGES = 8

// Same normalization and character count as the server (collapsed whitespace,
// one count per Unicode code point).
const normalize = (text) => text.replace(/\s+/g, ' ').trim()
const charCount = (text) => [...normalize(text)].length

function CharCount({ text }) {
  const n = charCount(text)
  return (
    <span className={`text-xs ${n > MAX_CHARS ? 'text-red-600 font-medium' : 'text-slate-400'}`}>
      {n}/{MAX_CHARS}
    </span>
  )
}

function MessageRow({ msg, index, total, busy, onMove, onSave, onRemove }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(msg.text)
  const draftLen = charCount(draft)
  const canSave = draftLen > 0 && draftLen <= MAX_CHARS && normalize(draft) !== msg.text

  async function save() {
    if (await onSave(msg.id, draft)) setEditing(false)
  }

  function startEdit() {
    setDraft(msg.text)
    setEditing(true)
  }

  if (editing) {
    return (
      <li className="bg-white rounded-xl shadow-sm p-3">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          autoFocus
          className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm resize-none"
        />
        <div className="flex items-center justify-between mt-2">
          <CharCount text={draft} />
          <div className="flex gap-2">
            <button onClick={() => setEditing(false)} disabled={busy}
              className="text-sm text-slate-500 px-3 py-1.5">Cancel</button>
            <button onClick={save} disabled={busy || !canSave}
              className="bg-emerald-600 text-white text-sm px-4 py-1.5 rounded-lg disabled:opacity-50">
              Save
            </button>
          </div>
        </div>
      </li>
    )
  }

  return (
    <li className="bg-white rounded-xl shadow-sm p-3 flex items-start gap-2">
      <div className="flex flex-col shrink-0">
        <button onClick={() => onMove(index, -1)} disabled={busy || index === 0}
          aria-label="Move up"
          className="text-slate-500 leading-none px-1.5 py-0.5 rounded hover:bg-slate-100 disabled:opacity-25">▲</button>
        <button onClick={() => onMove(index, 1)} disabled={busy || index === total - 1}
          aria-label="Move down"
          className="text-slate-500 leading-none px-1.5 py-0.5 rounded hover:bg-slate-100 disabled:opacity-25">▼</button>
      </div>
      <p className="flex-1 min-w-0 text-sm text-slate-800 break-words pt-1">{msg.text}</p>
      <button onClick={startEdit} disabled={busy}
        className="text-xs text-sky-700 underline shrink-0 pt-1.5 disabled:opacity-50">Edit</button>
      <button onClick={() => onRemove(msg)} disabled={busy}
        aria-label="Remove message"
        className="text-slate-400 hover:text-red-600 text-xl leading-none px-1 shrink-0 disabled:opacity-50">×</button>
    </li>
  )
}

export default function DisplayMessages({ back = '/assistant' }) {
  const [messages, setMessages] = useState(null)
  const [newText, setNewText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try { setMessages(await api.displayMessages()) } catch (e) { setError(e.message) }
  }, [])

  useEffect(() => { load() }, [load])

  // Runs a change; on failure shows the reason and reloads, since a failure
  // often means another EA changed the list meanwhile.
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

  const full = messages !== null && messages.length >= MAX_MESSAGES
  const newLen = charCount(newText)
  const canAdd = !busy && !full && newLen > 0 && newLen <= MAX_CHARS

  async function add(e) {
    e.preventDefault()
    if (!canAdd) return
    const ok = await run(async () => {
      const created = await api.addDisplayMessage(newText)
      setMessages((list) => [...list, created])
    })
    if (ok) setNewText('')
  }

  function save(id, text) {
    return run(async () => {
      const updated = await api.editDisplayMessage(id, text)
      setMessages((list) => list.map((m) => (m.id === id ? updated : m)))
    })
  }

  function remove(msg) {
    if (!window.confirm(`Remove this message from the gate screens?\n\n"${msg.text}"`)) return
    run(async () => {
      await api.removeDisplayMessage(msg.id)
      setMessages((list) => list.filter((m) => m.id !== msg.id))
    })
  }

  function move(index, delta) {
    const ids = messages.map((m) => m.id)
    const target = index + delta
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    run(async () => setMessages(await api.reorderDisplayMessages(ids)))
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader title="Display Messages" back={back} />
      <main className="p-4 max-w-md mx-auto space-y-3">
        <p className="text-xs text-slate-500">
          Announcements shown on both gate screens, in this order. Changes appear
          within about a minute. Up to {MAX_MESSAGES} messages, {MAX_CHARS} characters each.
        </p>

        <form onSubmit={add} className="bg-white rounded-xl shadow-sm p-3">
          <textarea
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) add(e)
            }}
            rows={2}
            disabled={full}
            placeholder={full ? `The board is full (${MAX_MESSAGES} messages). Remove one to add another.` : 'Type an announcement…'}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm resize-none disabled:bg-slate-100"
          />
          <div className="flex items-center justify-between mt-2">
            <CharCount text={newText} />
            <button type="submit" disabled={!canAdd}
              className="bg-brand-red text-white text-sm px-4 py-1.5 rounded-lg disabled:opacity-50">
              Add
            </button>
          </div>
        </form>

        {error && <p className="text-red-600 text-sm">{error}</p>}

        {messages === null ? (
          <p className="text-center text-slate-400 py-8">Loading…</p>
        ) : messages.length === 0 ? (
          <div className="text-center text-slate-500 py-10">
            <p className="text-sm">No announcements. The gate screens show only the welcome page.</p>
          </div>
        ) : (
          <>
            <div className="text-xs text-slate-400">
              {messages.length} of {MAX_MESSAGES} messages
            </div>
            <ol className="space-y-2">
              {messages.map((m, i) => (
                <MessageRow key={m.id} msg={m} index={i} total={messages.length} busy={busy}
                  onMove={move} onSave={save} onRemove={remove} />
              ))}
            </ol>
          </>
        )}
      </main>
    </div>
  )
}
