// Thin API client. In dev, Vite proxies /api -> backend (see vite.config.js).
// In production set VITE_API_BASE to the deployed backend URL.
const BASE = import.meta.env.VITE_API_BASE ?? '/api'

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// Build a query string from defined params only.
function _q(params) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') p.set(k, v)
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

async function handle(res) {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return res.status === 204 ? null : res.json()
}

// Fetch an auth-protected image/binary with the bearer token and hand back an
// object URL. `<img src>` can't send the Authorization header, so protected
// images must be loaded this way (see AuthImage). Caller revokes the URL.
async function blobUrl(url) {
  const res = await fetch(url, { headers: authHeaders() })
  if (!res.ok) throw new Error(res.statusText || 'Could not load image')
  return URL.createObjectURL(await res.blob())
}

export const api = {
  async health() {
    return handle(await fetch(`${BASE}/health`))
  },
  // Load an auth-protected image as an object URL (used by AuthImage).
  blobUrl,

  // OAuth2 password form: backend expects form-encoded username/password.
  async login(username, password) {
    const body = new URLSearchParams({ username, password })
    return handle(
      await fetch(`${BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      })
    )
  },

  async me() {
    return handle(await fetch(`${BASE}/auth/me`, { headers: authHeaders() }))
  },

  // ── Change password (current password or mobile OTP) ──
  async requestPasswordOtp() {
    return handle(
      await fetch(`${BASE}/auth/password/otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({}),
      })
    )
  },

  async changePassword({ newPassword, oldPassword = null, otpCode = null }) {
    return handle(
      await fetch(`${BASE}/auth/password/change`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          new_password: newPassword,
          old_password: oldPassword,
          otp_code: otpCode,
        }),
      })
    )
  },

  async updateProfile(patch) {
    return handle(
      await fetch(`${BASE}/employees/profile`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(patch),
      })
    )
  },

  async supervisorNotifications() {
    return handle(await fetch(`${BASE}/supervisor/notifications`, { headers: authHeaders() }))
  },

  // ── Personal notification inbox (employee / EA) ──
  async myNotifications() {
    return handle(await fetch(`${BASE}/notifications`, { headers: authHeaders() }))
  },
  async markNotificationsRead() {
    return handle(await fetch(`${BASE}/notifications/read`, {
      method: 'POST', headers: authHeaders(),
    }))
  },

  // ── OTP login ──
  async requestOtp(phone) {
    return handle(
      await fetch(`${BASE}/auth/otp/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone }),
      })
    )
  },

  async verifyOtp(phone, code) {
    return handle(
      await fetch(`${BASE}/auth/otp/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, code }),
      })
    )
  },

  // ── Self sign-up (public) ──
  async signupOptions() {
    return handle(await fetch(`${BASE}/auth/signup/options`))
  },
  async signupRequestOtp(phone) {
    return handle(
      await fetch(`${BASE}/auth/signup/otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone }),
      })
    )
  },
  async signup(payload) {
    return handle(
      await fetch(`${BASE}/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    )
  },

  // ── Self sign-up onboarding (Executive Assistant, global queue) ──
  async pendingSignups(status = 'worklist') {
    return handle(await fetch(`${BASE}/assistant/signups?status=${status}`, { headers: authHeaders() }))
  },
  async approveSignup(id, payload) {
    return handle(
      await fetch(`${BASE}/assistant/signups/${id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(payload),
      })
    )
  },
  async rejectSignup(id, reason = null) {
    return handle(
      await fetch(`${BASE}/assistant/signups/${id}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ reason }),
      })
    )
  },
  async onboardSignupPhotos(id, files) {
    const form = new FormData()
    for (const f of files) form.append('photos', f)
    return handle(
      await fetch(`${BASE}/assistant/signups/${id}/photos`, {
        method: 'POST',
        headers: { ...authHeaders() },
        body: form,
      })
    )
  },

  // ── Executive Assistant: profile + delegated tasks ──
  async assistantProfile() {
    return handle(await fetch(`${BASE}/assistant/profile`, { headers: authHeaders() }))
  },
  async assistantTasks(type) {
    const q = type ? `?type=${type}` : ''
    return handle(await fetch(`${BASE}/assistant/tasks${q}`, { headers: authHeaders() }))
  },
  async assistantApproveFieldTask(taskId, reason = null) {
    return handle(await fetch(`${BASE}/assistant/tasks/${taskId}/field/approve`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ reason }),
    }))
  },
  async assistantRejectFieldTask(taskId, reason = null) {
    return handle(await fetch(`${BASE}/assistant/tasks/${taskId}/field/reject`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ reason }),
    }))
  },
  assistantFieldSelfieUrl(eventId) {
    return `${BASE}/assistant/field/selfie/${eventId}`
  },
  async assistantTaskDay(taskId) {
    return handle(await fetch(`${BASE}/assistant/tasks/${taskId}/day`, { headers: authHeaders() }))
  },
  async assistantTaskEditCrossing(taskId, eventId, time) {
    return handle(await fetch(`${BASE}/assistant/tasks/${taskId}/events/${eventId}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ time }),
    }))
  },
  async assistantTaskDeleteCrossing(taskId, eventId, reason) {
    const q = reason ? `?reason=${encodeURIComponent(reason)}` : ''
    return handle(await fetch(`${BASE}/assistant/tasks/${taskId}/events/${eventId}${q}`, {
      method: 'DELETE', headers: authHeaders(),
    }))
  },
  async assistantTaskAddCrossing(taskId, { externalId, forDate, direction, time }) {
    return handle(await fetch(`${BASE}/assistant/tasks/${taskId}/events`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ external_id: externalId, for_date: forDate, direction, time }),
    }))
  },
  async assistantTaskOverride(taskId, body) {
    return handle(await fetch(`${BASE}/assistant/tasks/${taskId}/override`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }))
  },
  async assistantCompleteTask(taskId) {
    return handle(await fetch(`${BASE}/assistant/tasks/${taskId}/complete`, {
      method: 'POST', headers: authHeaders(),
    }))
  },

  // ── Supervisor: delegation to the EA ──
  async delegateFieldApprovals(eventIds, comment = null) {
    return handle(await fetch(`${BASE}/supervisor/field/approvals/delegate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ event_ids: eventIds, comment }),
    }))
  },
  async delegateAttendanceEdit({ externalId, forDate, comment }) {
    return handle(await fetch(`${BASE}/supervisor/attendance/delegate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ external_id: externalId, for_date: forDate, comment }),
    }))
  },
  async recallTask(taskId) {
    return handle(await fetch(`${BASE}/supervisor/tasks/${taskId}/recall`, {
      method: 'POST', headers: authHeaders(),
    }))
  },
  async myAssistant() {
    return handle(await fetch(`${BASE}/supervisor/assistant`, { headers: authHeaders() }))
  },

  // ── Profile avatar ──
  async uploadAvatar(file) {
    const form = new FormData()
    form.append('photo', file)
    return handle(
      await fetch(`${BASE}/employees/avatar`, {
        method: 'POST',
        headers: { ...authHeaders() },
        body: form,
      })
    )
  },
  avatarUrl(externalId) {
    return `${BASE}/employees/${externalId}/avatar`
  },

  // ── Onboarding (supervisor) ──
  async createEmployee(payload) {
    return handle(
      await fetch(`${BASE}/supervisor/employees`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(payload),
      })
    )
  },

  async enrollEmployee(externalId, files) {
    const form = new FormData()
    for (const f of files) form.append('photos', f)
    return handle(
      await fetch(`${BASE}/supervisor/employees/${externalId}/enroll`, {
        method: 'POST',
        headers: { ...authHeaders() },  // browser sets multipart boundary
        body: form,
      })
    )
  },

  // ── Field attendance (face + GPS) ──
  async fieldStatus() {
    return handle(await fetch(`${BASE}/attendance/field/status`, { headers: authHeaders() }))
  },

  async stations() {
    return handle(await fetch(`${BASE}/attendance/field/stations`, { headers: authHeaders() }))
  },

  // ── Supervisor analytics ──
  async analyticsSummary(from, to, dept, types) {
    const q = _q({ from_date: from, to_date: to, department_id: dept, types })
    return handle(await fetch(`${BASE}/supervisor/analytics/summary${q}`, { headers: authHeaders() }))
  },
  async analyticsTrend(from, to, dept, granularity = 'day', types) {
    const q = _q({ from_date: from, to_date: to, department_id: dept, granularity, types })
    return handle(await fetch(`${BASE}/supervisor/analytics/trend${q}`, { headers: authHeaders() }))
  },
  async analyticsByDepartment(from, to, types) {
    const q = _q({ from_date: from, to_date: to, types })
    return handle(await fetch(`${BASE}/supervisor/analytics/by-department${q}`, { headers: authHeaders() }))
  },
  async analyticsSourceSplit(from, to, dept, types) {
    const q = _q({ from_date: from, to_date: to, department_id: dept, types })
    return handle(await fetch(`${BASE}/supervisor/analytics/source-split${q}`, { headers: authHeaders() }))
  },
  async analyticsLowest(from, to, dept, limit = 10, types) {
    const q = _q({ from_date: from, to_date: to, department_id: dept, limit, types })
    return handle(await fetch(`${BASE}/supervisor/analytics/lowest-attendance${q}`, { headers: authHeaders() }))
  },

  async fieldCheckIn({ selfie, direction, latitude, longitude, accuracy, capturedAt }) {
    const form = new FormData()
    form.append('selfie', selfie, 'selfie.jpg')
    form.append('direction', direction)
    if (latitude != null) form.append('latitude', String(latitude))
    if (longitude != null) form.append('longitude', String(longitude))
    if (accuracy != null) form.append('accuracy_m', String(accuracy))
    if (capturedAt) form.append('captured_at', capturedAt)
    return handle(
      await fetch(`${BASE}/attendance/field`, {
        method: 'POST',
        headers: { ...authHeaders() },
        body: form,
      })
    )
  },

  // ── Supervisor: field approvals ──
  async fieldApprovals(status = 'pending') {
    return handle(await fetch(`${BASE}/supervisor/field/approvals?status=${status}`, { headers: authHeaders() }))
  },
  async approveField(eventId, reason = null) {
    return handle(await fetch(`${BASE}/supervisor/field/approvals/${eventId}/approve`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ reason }),
    }))
  },
  async rejectField(eventId, reason = null) {
    return handle(await fetch(`${BASE}/supervisor/field/approvals/${eventId}/reject`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ reason }),
    }))
  },
  fieldSelfieUrl(eventId) {
    return `${BASE}/supervisor/field/selfie/${eventId}`
  },

  // ── Supervisor: employee settings/permissions ──
  async getEmployeeSettings(externalId) {
    return handle(await fetch(`${BASE}/supervisor/employees/${externalId}/settings`, { headers: authHeaders() }))
  },
  async updateEmployeeSettings(externalId, patch) {
    return handle(await fetch(`${BASE}/supervisor/employees/${externalId}/settings`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(patch),
    }))
  },

  async myAttendance(limit = 100) {
    return handle(
      await fetch(`${BASE}/attendance/me?limit=${limit}`, { headers: authHeaders() })
    )
  },

  async summary(fromDate, toDate) {
    const q = fromDate && toDate ? `?from_date=${fromDate}&to_date=${toDate}` : ''
    return handle(await fetch(`${BASE}/attendance/summary${q}`, { headers: authHeaders() }))
  },

  async stats(fromDate, toDate) {
    const q = fromDate && toDate ? `?from_date=${fromDate}&to_date=${toDate}` : ''
    return handle(await fetch(`${BASE}/attendance/stats${q}`, { headers: authHeaders() }))
  },

  async dayDetail(day) {
    return handle(await fetch(`${BASE}/attendance/day/${day}`, { headers: authHeaders() }))
  },

  // Supervisor
  async supervisorOverview(fromDate, toDate, departmentId, types) {
    const p = new URLSearchParams()
    if (fromDate && toDate) { p.set('from_date', fromDate); p.set('to_date', toDate) }
    if (departmentId) p.set('department_id', departmentId)
    if (types) p.set('types', types)
    const q = p.toString() ? `?${p}` : ''
    return handle(await fetch(`${BASE}/supervisor/attendance/overview${q}`, { headers: authHeaders() }))
  },

  async departments() {
    return handle(await fetch(`${BASE}/supervisor/departments`, { headers: authHeaders() }))
  },

  async supervisors() {
    return handle(await fetch(`${BASE}/supervisor/supervisors`, { headers: authHeaders() }))
  },

  async employeeSummary(externalId, fromDate, toDate) {
    const q = fromDate && toDate ? `?from_date=${fromDate}&to_date=${toDate}` : ''
    return handle(
      await fetch(`${BASE}/supervisor/employee/${externalId}/summary${q}`, { headers: authHeaders() })
    )
  },

  // ── Disputes (employee) ──
  async createDispute(forDate, { message = null, targetKind = 'day', eventId = null } = {}) {
    return handle(
      await fetch(`${BASE}/disputes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          for_date: forDate, message, target_kind: targetKind, event_id: eventId,
        }),
      })
    )
  },

  async myDisputes() {
    return handle(await fetch(`${BASE}/disputes/me`, { headers: authHeaders() }))
  },

  async updateDispute(id, message) {
    return handle(
      await fetch(`${BASE}/disputes/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ message }),
      })
    )
  },

  // ── Disputes & overrides (supervisor) ──
  async supervisorDisputes(status = 'open') {
    return handle(
      await fetch(`${BASE}/supervisor/disputes?status=${status}`, { headers: authHeaders() })
    )
  },

  async supervisorAnomalies() {
    return handle(await fetch(`${BASE}/supervisor/anomalies`, { headers: authHeaders() }))
  },

  async approveDispute(id, body) {
    return handle(
      await fetch(`${BASE}/supervisor/disputes/${id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(body),
      })
    )
  },

  async rejectDispute(id, resolutionNote) {
    return handle(
      await fetch(`${BASE}/supervisor/disputes/${id}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ resolution_note: resolutionNote }),
      })
    )
  },

  async createOverride(body) {
    return handle(
      await fetch(`${BASE}/supervisor/overrides`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(body),
      })
    )
  },

  // ── Granular crossing edits (supervisor) ──
  async editCrossing(eventId, time) {
    return handle(await fetch(`${BASE}/supervisor/events/${eventId}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ time }),
    }))
  },
  async deleteCrossing(eventId, reason) {
    const q = reason ? `?reason=${encodeURIComponent(reason)}` : ''
    return handle(await fetch(`${BASE}/supervisor/events/${eventId}${q}`, {
      method: 'DELETE', headers: authHeaders(),
    }))
  },
  async addCrossing({ externalId, forDate, direction, time }) {
    return handle(await fetch(`${BASE}/supervisor/events`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ external_id: externalId, for_date: forDate, direction, time }),
    }))
  },

  // Triggers a browser download of the Excel report.
  async exportOverview(fromDate, toDate, departmentId) {
    const p = new URLSearchParams()
    if (fromDate && toDate) { p.set('from_date', fromDate); p.set('to_date', toDate) }
    if (departmentId) p.set('department_id', departmentId)
    const q = p.toString() ? `?${p}` : ''
    const res = await fetch(`${BASE}/supervisor/attendance/export${q}`, { headers: authHeaders() })
    if (!res.ok) throw new Error('Export failed')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `attendance_${fromDate ?? ''}_${toDate ?? ''}.xlsx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
}
