// Flush queued offline field scans to the server. The server runs the real
// (buffalo_s) face match on replay, so identity is confirmed at sync time.
import { api } from './api.js'
import { getAll, remove } from './offlineQueue.js'

let syncing = false

export async function syncFieldQueue() {
  if (syncing || !navigator.onLine) return { synced: 0, remaining: await safeCount() }
  syncing = true
  let synced = 0
  const failures = []
  try {
    const items = await getAll()
    for (const it of items) {
      try {
        await api.fieldCheckIn({
          selfie: it.blob,
          direction: it.direction,
          latitude: it.latitude,
          longitude: it.longitude,
          accuracy: it.accuracy,
          capturedAt: it.capturedAt,
        })
        await remove(it.id)
        synced += 1
      } catch (e) {
        // A validation error (e.g. face mismatch) shouldn't block the whole queue,
        // but a network error should stop and retry later.
        if (/Failed to fetch|NetworkError|load failed/i.test(e.message)) break
        // Drop items the server permanently rejects so the queue can drain.
        await remove(it.id)
        failures.push(e.message)
      }
    }
  } finally {
    syncing = false
  }
  return { synced, failures, remaining: await safeCount() }
}

async function safeCount() {
  try { return (await getAll()).length } catch { return 0 }
}
