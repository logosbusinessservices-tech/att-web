// On-device liveness via MediaPipe FaceLandmarker (Apache-2.0). Runs fully in the
// browser (offline once cached): detects a face + a real blink, so we auto-capture
// a live selfie instead of accepting an uploaded photo. Identity matching still
// happens on the server against the enrolled buffalo_s template.
import { FaceLandmarker, FilesetResolver } from '@mediapipe/tasks-vision'

let _landmarker = null

// Model + WASM are bundled under /public/mediapipe so this works with no internet.
export async function getFaceLandmarker() {
  if (_landmarker) return _landmarker
  const fileset = await FilesetResolver.forVisionTasks('/mediapipe/wasm')
  const opts = (delegate) => ({
    baseOptions: { modelAssetPath: '/mediapipe/face_landmarker.task', delegate },
    outputFaceBlendshapes: true,
    runningMode: 'VIDEO',
    numFaces: 1,
  })
  try {
    _landmarker = await FaceLandmarker.createFromOptions(fileset, opts('GPU'))
  } catch {
    _landmarker = await FaceLandmarker.createFromOptions(fileset, opts('CPU'))
  }
  return _landmarker
}

// Per-frame blink scores (0..1) for each eye, or null if no face.
export function blinkScores(result) {
  const cats = result?.faceBlendshapes?.[0]?.categories
  if (!cats) return null
  const get = (n) => cats.find((c) => c.categoryName === n)?.score ?? 0
  return { left: get('eyeBlinkLeft'), right: get('eyeBlinkRight') }
}

// Normalized face bounding box (presence + size + center), or null if no face.
export function faceBox(result) {
  const lm = result?.faceLandmarks?.[0]
  if (!lm) return null
  let minX = 1, minY = 1, maxX = 0, maxY = 0
  for (const p of lm) {
    if (p.x < minX) minX = p.x
    if (p.x > maxX) maxX = p.x
    if (p.y < minY) minY = p.y
    if (p.y > maxY) maxY = p.y
  }
  return { w: maxX - minX, h: maxY - minY, cx: (minX + maxX) / 2, cy: (minY + maxY) / 2 }
}
