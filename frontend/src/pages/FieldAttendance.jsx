import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppHeader from '../components/AppHeader.jsx'
import { api } from '../lib/api.js'
import { useAuth } from '../lib/auth.jsx'
import { getFaceLandmarker, blinkScores, faceBox } from '../lib/liveness.js'
import { enqueue, count as queueCount } from '../lib/offlineQueue.js'
import { syncFieldQueue } from '../lib/fieldSync.js'

// Liveness thresholds: a blink = eye-blink score rises above HIGH then falls below LOW.
const BLINK_HIGH = 0.55
const BLINK_LOW = 0.25
const MIN_FACE_W = 0.20    // face must fill enough of the frame (normalized width)
const CENTER_MIN = 0.30    // face centre must sit within the middle of the frame
const CENTER_MAX = 0.70
const STEADY_FRAMES = 4    // hold a good, centred face this many frames before we trust it
const DETECT_INTERVAL_MS = 90  // throttle detection so mobile GPUs don't choke
// Fallback liveness: if a clear, steady face is held this long without a detected
// blink (poor light / phone camera), capture anyway so the user is never stuck.
const BLINK_FALLBACK_MS = 4000

const isNetworkErr = (m) => /Failed to fetch|NetworkError|load failed/i.test(m || '')

export default function FieldAttendance({ back }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const home = user?.role === 'supervisor' ? '/supervisor' : '/employee'
  const enabled = !!user?.field_scan_enabled

  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const rafRef = useRef(0)
  const streamRef = useRef(null)
  const capturedRef = useRef(false)  // guard against double-capture

  // Liveness loop bookkeeping (refs so the camera effect never re-runs on change).
  const blinkArmed = useRef(false)   // saw eyes-open, waiting for a blink
  const steadyRef = useRef(0)        // consecutive good frames
  const goodSinceRef = useRef(0)     // timestamp a clear face first appeared (fallback timer)

  // Latest GPS/direction, read by the capture closure without re-arming the camera.
  const gpsRef = useRef(null)
  const directionRef = useRef('entry')

  const [phase, setPhase] = useState(enabled ? 'loading' : 'blocked') // loading|scanning|submitting|done|error
  const [direction, setDirection] = useState('entry')
  const [hint, setHint] = useState('Loading face scanner…')
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [gps, setGps] = useState(null) // { lat, lon, accuracy } | null
  const [pending, setPending] = useState(0)   // queued offline scans
  const [syncMsg, setSyncMsg] = useState('')
  const [restartKey, setRestartKey] = useState(0) // bump to re-arm the camera on retry

  const refreshPending = useCallback(async () => {
    try { setPending(await queueCount()) } catch { /* ignore */ }
  }, [])

  const runSync = useCallback(async () => {
    if (!navigator.onLine) return
    setSyncMsg('Syncing…')
    const r = await syncFieldQueue()
    await refreshPending()
    setSyncMsg(r.synced ? `Synced ${r.synced} scan${r.synced === 1 ? '' : 's'}.` : '')
  }, [refreshPending])

  const stopCamera = useCallback(() => {
    cancelAnimationFrame(rafRef.current)
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
  }, [])

  const queueOffline = useCallback(async (payload) => {
    try {
      await enqueue({
        blob: payload.selfie, direction: payload.direction,
        latitude: payload.latitude, longitude: payload.longitude,
        accuracy: payload.accuracy, capturedAt: payload.capturedAt,
      })
      await refreshPending()
      setResult({ review_status: 'queued', message: "Saved offline — it'll sync when you're back online." })
      setPhase('done')
    } catch (e) {
      setError('Could not save offline: ' + e.message)
      setPhase('error')
    }
  }, [refreshPending])

  // Submit reads GPS/direction from refs so it's stable and never re-arms the camera.
  const submit = useCallback(async (blob) => {
    setPhase('submitting')
    setHint('Verifying…')
    const g = gpsRef.current
    const payload = {
      selfie: blob,
      direction: directionRef.current,
      latitude: g?.lat ?? null,
      longitude: g?.lon ?? null,
      accuracy: g?.accuracy ?? null,
      capturedAt: new Date().toISOString(),  // real capture time, for offline replay
    }
    if (!navigator.onLine) { return queueOffline(payload) }
    try {
      const res = await api.fieldCheckIn(payload)
      setResult(res)
      setPhase('done')
    } catch (e) {
      if (isNetworkErr(e.message)) return queueOffline(payload)
      setError(e.message)
      setPhase('error')
    }
  }, [queueOffline])

  const capture = useCallback(() => {
    if (capturedRef.current) return
    capturedRef.current = true
    cancelAnimationFrame(rafRef.current)
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return
    // Snap the full frame (face + background) before tearing the camera down.
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0)
    stopCamera()
    canvas.toBlob((blob) => { if (blob) submit(blob) }, 'image/jpeg', 0.9)
  }, [stopCamera, submit])

  // Keep the latest capture closure reachable from the (stable) detection loop.
  const captureRef = useRef(capture)
  useEffect(() => { captureRef.current = capture }, [capture])

  // Start GPS (parallel — server marks the scan pending if it's missing/coarse).
  useEffect(() => {
    if (!enabled || !navigator.geolocation) return
    const id = navigator.geolocation.watchPosition(
      (pos) => {
        const g = { lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy }
        gpsRef.current = g
        setGps(g)
      },
      () => { gpsRef.current = null; setGps(null) },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 },
    )
    return () => navigator.geolocation.clearWatch(id)
  }, [enabled])

  // Sync queued offline scans on open and whenever connectivity returns.
  useEffect(() => {
    refreshPending()
    runSync()
    const onOnline = () => runSync()
    window.addEventListener('online', onOnline)
    return () => window.removeEventListener('online', onOnline)
  }, [refreshPending, runSync])

  // Load model + fetch next direction, then start camera + liveness loop.
  // Depends only on [enabled, restartKey] so GPS/direction updates never tear the
  // camera down (that was the cause of the flicker / black-screen).
  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    capturedRef.current = false
    blinkArmed.current = false
    steadyRef.current = 0
    goodSinceRef.current = 0

    async function start() {
      try {
        const [landmarker, status] = await Promise.all([getFaceLandmarker(), api.fieldStatus().catch(() => null)])
        if (cancelled) return
        if (status?.next_direction) {
          directionRef.current = status.next_direction
          setDirection(status.next_direction)
        }

        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false })
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return }
        streamRef.current = stream
        const video = videoRef.current
        video.srcObject = stream
        await video.play()
        setPhase('scanning')
        setHint('Center your face in the frame')

        let lastDetect = 0
        const loop = () => {
          if (cancelled || capturedRef.current) return
          rafRef.current = requestAnimationFrame(loop)

          const now = performance.now()
          if (now - lastDetect < DETECT_INTERVAL_MS) return
          if (video.readyState < 2 || !video.videoWidth) return  // frame not ready yet
          lastDetect = now

          const res = landmarker.detectForVideo(video, now)
          const box = faceBox(res)
          const blink = blinkScores(res)

          const centred = box && box.cx > CENTER_MIN && box.cx < CENTER_MAX
            && box.cy > CENTER_MIN && box.cy < CENTER_MAX

          if (!box) {
            setHint('No face detected — center your face')
            blinkArmed.current = false; steadyRef.current = 0; goodSinceRef.current = 0
            return
          }
          if (box.w < MIN_FACE_W) {
            setHint('Move a little closer')
            blinkArmed.current = false; steadyRef.current = 0; goodSinceRef.current = 0
            return
          }
          if (!centred) {
            setHint('Center your face in the frame')
            blinkArmed.current = false; steadyRef.current = 0; goodSinceRef.current = 0
            return
          }

          // Clear, centred face — need it held steady before we trust it.
          steadyRef.current += 1
          if (steadyRef.current < STEADY_FRAMES) {
            setHint('Hold still…')
            return
          }
          if (goodSinceRef.current === 0) goodSinceRef.current = now

          // Primary liveness: a real blink (eyes open, then closed).
          if (blink) {
            const score = Math.max(blink.left, blink.right)
            if (score < BLINK_LOW) blinkArmed.current = true
            if (blinkArmed.current && score > BLINK_HIGH) {
              setHint('Got it! Capturing…')
              captureRef.current()
              return
            }
          }

          // Fallback liveness: clear steady face held long enough without a blink.
          if (now - goodSinceRef.current > BLINK_FALLBACK_MS) {
            setHint('Capturing…')
            captureRef.current()
            return
          }
          setHint('Blink to confirm you\u2019re live')
        }
        rafRef.current = requestAnimationFrame(loop)
      } catch (e) {
        if (cancelled) return
        setError(e?.message || 'Could not start the camera. Check permissions.')
        setPhase('error')
      }
    }
    start()
    return () => { cancelled = true; stopCamera() }
  }, [enabled, restartKey, stopCamera])

  function reset() {
    capturedRef.current = false
    blinkArmed.current = false
    steadyRef.current = 0
    goodSinceRef.current = 0
    setResult(null)
    setError('')
    setHint('Loading face scanner…')
    setPhase('loading')
    setRestartKey((k) => k + 1)  // re-arm the camera in place (no page reload)
  }

  const title = `Field ${direction === 'exit' ? 'Check-out' : 'Check-in'}`

  return (
    <div className="min-h-screen bg-slate-900">
      <AppHeader title="Field Attendance" back={back || home} />
      <main className="p-4 max-w-md mx-auto">
        {phase === 'blocked' && (
          <div className="bg-white rounded-2xl p-6 text-center space-y-3 mt-6">
            <div className="text-4xl">🔒</div>
            <p className="font-semibold text-slate-800">Field attendance isn’t enabled</p>
            <p className="text-sm text-slate-500">Ask your supervisor to allow field scan on your account.</p>
          </div>
        )}

        {phase !== 'blocked' && (
          <div className="space-y-4">
            {(pending > 0 || syncMsg) && (
              <div className="flex items-center justify-between gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-800">
                <span>
                  {pending > 0
                    ? `${pending} scan${pending === 1 ? '' : 's'} waiting to sync${navigator.onLine ? '' : ' (offline)'}`
                    : syncMsg}
                </span>
                {pending > 0 && navigator.onLine && (
                  <button onClick={runSync} className="underline font-medium">Sync now</button>
                )}
              </div>
            )}

            <div className="text-center text-white">
              <div className="text-lg font-semibold">{title}</div>
              <div className="text-xs text-slate-300">
                {gps ? `Location ±${Math.round(gps.accuracy)} m` : 'Locating…'}
                {!navigator.onLine && ' · offline'}
              </div>
            </div>

            <div className="relative aspect-[3/4] w-full rounded-2xl overflow-hidden bg-black">
              {/* Mirror the preview so it feels like a selfie. Stays visible the whole
                  time — we only overlay a translucent caption, never a black screen. */}
              <video ref={videoRef} playsInline muted className="w-full h-full object-cover -scale-x-100" />
              <canvas ref={canvasRef} className="hidden" />

              {/* Loading: only shown briefly before the stream is live. */}
              {phase === 'loading' && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/60 text-white text-sm">
                  <span className="animate-pulse">{hint}</span>
                </div>
              )}

              {/* Framing guide + live instructions while scanning. */}
              {phase === 'scanning' && (
                <>
                  <div className="absolute inset-0 border-[3px] border-white/40 rounded-2xl m-8 pointer-events-none" />
                  <div className="absolute bottom-3 inset-x-0 text-center text-white text-sm bg-black/40 py-1.5">
                    {hint}
                  </div>
                </>
              )}

              {/* Verifying: keep the (frozen) captured frame visible under a slim band. */}
              {phase === 'submitting' && (
                <div className="absolute bottom-3 inset-x-0 flex items-center justify-center gap-2 text-white text-sm bg-black/50 py-1.5">
                  <span className="inline-block w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                  {hint}
                </div>
              )}

              {phase === 'done' && result && (
                <div className={`absolute inset-0 flex flex-col items-center justify-center text-white p-4 text-center ${
                  result.review_status === 'approved' ? 'bg-emerald-700/85'
                  : result.review_status === 'queued' ? 'bg-indigo-700/85'
                  : 'bg-amber-700/85'}`}>
                  <div className="text-5xl mb-2">{
                    result.review_status === 'approved' ? '✓'
                    : result.review_status === 'queued' ? '☁'
                    : '⏳'}</div>
                  <p className="font-semibold">{result.message}</p>
                  {result.review_status === 'pending' && (
                    <p className="text-xs mt-1 opacity-90">Your photo was sent to your supervisor for approval.</p>
                  )}
                </div>
              )}

              {phase === 'error' && (
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-red-800/85 text-white p-4 text-center">
                  <div className="text-4xl mb-2">⚠</div>
                  <p className="text-sm">{error}</p>
                </div>
              )}
            </div>

            {(phase === 'done' || phase === 'error') && (
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    if (phase === 'error') { reset(); return }
                    stopCamera()
                    navigate(back || home)
                  }}
                  className="flex-1 bg-white text-slate-900 rounded-lg py-2.5 font-medium">
                  {phase === 'error' ? 'Try again' : 'Done'}
                </button>
              </div>
            )}

            <p className="text-[11px] text-slate-400 text-center">
              Your face is checked on our server against your enrolled profile. A live blink is required.
            </p>
          </div>
        )}
      </main>
    </div>
  )
}
