// Small, dependency-free exporters for the dashboards.

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// rows: array of flat objects. Columns are inferred from the first row.
export function downloadCsv(filename, rows) {
  if (!rows || rows.length === 0) return
  const cols = Object.keys(rows[0])
  const esc = (v) => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))]
  triggerDownload(new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' }), filename)
}

function htmlEsc(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

// Export the department→employee matrix as an Excel-openable .xls (HTML table,
// no extra dependency). Department rows are bold aggregates; employees indent.
export function exportMatrixXls(matrix, filename = 'analytics.xls', meta = {}) {
  const head =
    '<tr style="background:#25201c;color:#fff;font-weight:bold">' +
    '<th>Department / Employee</th><th>Code</th><th>Staff</th>' +
    '<th>Present</th><th>Absent</th><th>Attendance %</th><th>Hours</th></tr>'
  const body = (matrix || []).map((d) => {
    const dept =
      '<tr style="background:#e4e1d8;font-weight:bold">' +
      `<td>${htmlEsc(d.name)}</td><td></td><td>${d.headcount}</td>` +
      `<td>${d.present}</td><td>${d.absent}</td><td>${d.attendance_pct}</td><td>${d.total_hours}</td></tr>`
    const emps = (d.employees || []).map((e) =>
      '<tr>' +
      `<td>&nbsp;&nbsp;&nbsp;&nbsp;${htmlEsc(e.display_name)}</td><td>${htmlEsc(e.external_id)}</td><td></td>` +
      `<td>${e.present}</td><td>${e.absent}</td><td>${e.attendance_pct}</td><td>${e.total_hours}</td></tr>`,
    ).join('')
    return dept + emps
  }).join('')
  const caption = meta.subtitle ? `<caption style="text-align:left">${htmlEsc(meta.subtitle)}</caption>` : ''
  const html =
    '<html xmlns:o="urn:schemas-microsoft-com:office:office" ' +
    'xmlns:x="urn:schemas-microsoft-com:office:excel"><head><meta charset="utf-8"></head><body>' +
    `<table border="1" cellspacing="0">${caption}${head}${body}</table></body></html>`
  triggerDownload(new Blob([html], { type: 'application/vnd.ms-excel' }), filename)
}

// Serialize an <svg> (e.g. a Recharts chart) to a PNG and download it.
export async function downloadSvgPng(svgEl, filename, scale = 2) {
  if (!svgEl) return
  const rect = svgEl.getBoundingClientRect()
  const w = rect.width || 600
  const h = rect.height || 320
  const clone = svgEl.cloneNode(true)
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  // White background so the PNG isn't transparent.
  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  bg.setAttribute('width', '100%')
  bg.setAttribute('height', '100%')
  bg.setAttribute('fill', '#ffffff')
  clone.insertBefore(bg, clone.firstChild)
  const svgStr = new XMLSerializer().serializeToString(clone)
  const svgBlob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(svgBlob)
  try {
    const img = new Image()
    await new Promise((resolve, reject) => {
      img.onload = resolve
      img.onerror = reject
      img.src = url
    })
    const canvas = document.createElement('canvas')
    canvas.width = w * scale
    canvas.height = h * scale
    const ctx = canvas.getContext('2d')
    ctx.scale(scale, scale)
    ctx.drawImage(img, 0, 0, w, h)
    await new Promise((resolve) => canvas.toBlob((b) => { triggerDownload(b, filename); resolve() }, 'image/png'))
  } finally {
    URL.revokeObjectURL(url)
  }
}

// Find the first <svg> inside a container ref and export it.
export function exportChartPng(containerEl, filename) {
  const svg = containerEl?.querySelector('svg')
  return downloadSvgPng(svg, filename)
}

// Rasterize an <svg> to a PNG data URL (for embedding in PDF/PPTX).
async function svgToPngDataUrl(svgEl, scale = 2) {
  const rect = svgEl.getBoundingClientRect()
  const w = rect.width || 600
  const h = rect.height || 320
  const clone = svgEl.cloneNode(true)
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  bg.setAttribute('width', '100%'); bg.setAttribute('height', '100%'); bg.setAttribute('fill', '#ffffff')
  clone.insertBefore(bg, clone.firstChild)
  const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml;charset=utf-8' }))
  try {
    const img = new Image()
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url })
    const canvas = document.createElement('canvas')
    canvas.width = w * scale; canvas.height = h * scale
    const ctx = canvas.getContext('2d')
    ctx.scale(scale, scale)
    ctx.drawImage(img, 0, 0, w, h)
    return { dataUrl: canvas.toDataURL('image/png'), width: w, height: h }
  } finally {
    URL.revokeObjectURL(url)
  }
}

// charts: [{ title, el }]. Builds a multi-page PDF of the chart images.
export async function exportDashboardPdf(charts, filename = 'analytics.pdf', meta = {}) {
  const { jsPDF } = await import('jspdf')
  const pdf = new jsPDF({ orientation: 'portrait', unit: 'pt', format: 'a4' })
  const pageW = pdf.internal.pageSize.getWidth()
  const pageH = pdf.internal.pageSize.getHeight()
  const margin = 40
  pdf.setFontSize(16); pdf.text(meta.title || 'Attendance Analytics', margin, margin)
  let y = margin + 20
  if (meta.subtitle) { pdf.setFontSize(10); pdf.setTextColor(120); pdf.text(meta.subtitle, margin, y); pdf.setTextColor(0); y += 20 }
  for (const c of charts) {
    const svg = c.el?.querySelector('svg')
    if (!svg) continue
    const img = await svgToPngDataUrl(svg)
    const w = pageW - margin * 2
    const h = (img.height / img.width) * w
    if (y + h + 24 > pageH - margin) { pdf.addPage(); y = margin }
    pdf.setFontSize(12); pdf.text(c.title, margin, y); y += 10
    pdf.addImage(img.dataUrl, 'PNG', margin, y, w, h); y += h + 28
  }
  pdf.save(filename)
}

// charts: [{ title, el }]. One slide per chart.
export async function exportDashboardPptx(charts, filename = 'analytics.pptx', meta = {}) {
  const Pptx = (await import('pptxgenjs')).default
  const p = new Pptx()
  p.layout = 'LAYOUT_WIDE'
  const title = p.addSlide()
  title.addText(meta.title || 'Attendance Analytics', { x: 0.5, y: 1.2, fontSize: 30, bold: true })
  if (meta.subtitle) title.addText(meta.subtitle, { x: 0.5, y: 2.2, fontSize: 16, color: '666666' })
  for (const c of charts) {
    const svg = c.el?.querySelector('svg')
    if (!svg) continue
    const img = await svgToPngDataUrl(svg)
    const s = p.addSlide()
    s.addText(c.title, { x: 0.5, y: 0.3, fontSize: 22, bold: true })
    const ratio = img.height / img.width
    let w = 9, h = w * ratio
    const maxH = 5.6
    if (h > maxH) { h = maxH; w = h / ratio }
    s.addImage({ data: img.dataUrl, x: (13.33 - w) / 2, y: 1.1, w, h })
  }
  await p.writeFile({ fileName: filename })
}
