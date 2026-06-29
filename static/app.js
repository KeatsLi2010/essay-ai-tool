const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

let appState = null;
let pollTimer = null;
let confirmResolver = null;
const SCORE_MAX = 60;
const ACTIVITY_WEEKS = 9;
let recentSort = { key: "createdAt", dir: "desc" };
let selectedAssignmentId = null;
let selectedStudentId = null;
let assignmentSubTab = "submissions";
let radarSubTab = "final";
let currentReportPath = null;
const RADAR_DIMENSIONS = [
  { key: "topic", label: "审题立意" },
  { key: "genre", label: "文体适配" },
  { key: "material", label: "内容材料" },
  { key: "structure", label: "结构层次" },
  { key: "language", label: "语言表达" },
  { key: "rhythm", label: "韵律节奏" },
  { key: "development", label: "发展亮点" },
  { key: "norm", label: "规范表现" },
];
const CHART_COLORS = ["#13735b", "#d86f45", "#3b75a6", "#9b6a30", "#6c7a3b", "#8b5f93", "#2f8f88", "#bf526a"];

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function setBusy(active) {
  $("#busy").classList.toggle("hidden", !active);
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 3200);
}

async function api(path, options = {}) {
  const { quiet = false, ...fetchOptions } = options;
  if (!quiet) setBusy(true);
  try {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...fetchOptions,
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "请求失败");
    if (data.state) {
      appState = data.state;
      render();
    }
    if (data.message) toast(data.message.split("\n")[0]);
    return data;
  } finally {
    if (!quiet) setBusy(false);
  }
}

async function refresh(quiet = false) {
  const data = await api("/api/state", { method: "GET", headers: {}, quiet });
  appState = data.state;
  render();
}

function scoreText(score) {
  return score === null || score === undefined ? "未评分" : Number(score).toFixed(Number(score) % 1 ? 1 : 0);
}

function isReadOnly() {
  return Boolean(appState?.config?.readOnly);
}

function activateTab(name) {
  $$(".tab").forEach(item => item.classList.toggle("active", item.dataset.tab === name));
  $$(".tab-panel").forEach(item => item.classList.toggle("active", item.dataset.panel === name));
}

function render() {
  if (!appState) return;
  const { assignments, students, recentSubmissions, submissions = recentSubmissions, jobs = [], config, undo, generatedReports = [] } = appState;
  const activeJobs = jobs.filter(job => ["queued", "running"].includes(job.status));
  let selectedAssignment = assignments.find(item => item.id === selectedAssignmentId);
  if (selectedAssignmentId && !selectedAssignment) {
    selectedAssignmentId = null;
    selectedAssignment = null;
  }
  let selectedStudent = students.find(item => item.student === selectedStudentId);
  if (selectedStudentId && !selectedStudent) {
    selectedStudentId = null;
    selectedStudent = null;
  }
  const assignmentMode = Boolean(selectedAssignment);
  const studentMode = Boolean(selectedStudent);
  const detailMode = assignmentMode || studentMode;
  const readOnly = Boolean(config.readOnly);

  document.body.classList.toggle("guest-mode", readOnly);
  if (readOnly && ["assignment", "analytics", "style"].includes($(".tab.active")?.dataset.tab)) {
    activateTab("radar");
  }

  $("#keyStatus").textContent = config.hasApiKey ? "已配置" : "未配置";
  $("#keyStatus").classList.toggle("ready", config.hasApiKey);
  $("#model").value = config.model || "deepseek-v4-pro";
  $("#apiBase").value = config.apiBase || "https://api.deepseek.com";

  $("#assignmentCount").textContent = assignments.length;
  $("#studentCount").textContent = students.length;
  $("#metricAssignments").textContent = assignments.length;
  $("#metricStudents").textContent = students.length;
  $("#metricSubmissions").textContent = submissions.length;
  $("#metricJobs").textContent = activeJobs.length;
  $("#undoBtn").disabled = readOnly || !undo.count;
  $("#undoBtn").title = undo.last || "没有可撤销操作";

  $(".workspace").classList.toggle("assignment-detail-mode", assignmentMode);
  $(".workspace").classList.toggle("student-detail-mode", studentMode);
  $("#backToWorkspace").classList.toggle("hidden", !detailMode);
  $("#workspaceEyebrow").textContent = assignmentMode ? "Assignment Tasks" : (studentMode ? "Student Profile" : "Gaokao Essay Console");
  $("#workspaceTitle").textContent = assignmentMode ? selectedAssignment.title : (studentMode ? selectedStudent.student : "作文批阅工作台");
  $("#recentTitle").textContent = assignmentMode ? `《${selectedAssignment.title}》评分任务` : "最近提交与评分任务";
  $("#recentSubtitle").textContent = assignmentMode
    ? `${selectedAssignment.submissionCount} 篇提交 · 均分 ${scoreText(selectedAssignment.avgScore)}`
    : "报告完成后开放查看";

  if (readOnly && assignmentSubTab === "submit") assignmentSubTab = "submissions";
  placeSubmissionForm(assignmentMode);
  renderAssignmentDetail(selectedAssignment, readOnly);
  renderStudentDetail(selectedStudent, submissions);
  $(".lower-grid").classList.toggle("hidden", studentMode || (assignmentMode && assignmentSubTab !== "submissions"));
  renderAssignments(assignments);
  renderStudents(students);
  renderAssignmentSelect(assignments);
  renderStyleReports(generatedReports);
  renderRecent(assignmentMode ? submissions : recentSubmissions, jobs, assignmentMode ? selectedAssignment.id : null);
  renderSparkline(assignmentMode ? submissions.filter(row => row.assignmentId === selectedAssignment.id) : recentSubmissions);
  renderRadarOverview(submissions, students);  ensurePolling(activeJobs.length > 0);
}

function placeSubmissionForm(detailMode) {
  const form = $("#submissionForm");
  const target = detailMode ? $("#detailSubmitPanel") : $("#globalSubmissionSlot");
  if (form && target && form.parentElement !== target) target.appendChild(form);
  form.classList.remove("tab-panel");
  form.classList.toggle("panel", !detailMode);
  form.classList.toggle("detail-submit-form", detailMode);
  form.classList.toggle("hidden", !detailMode || assignmentSubTab !== "submit");
  form.classList.toggle("active", detailMode && assignmentSubTab === "submit");
}

function renderAssignmentDetail(assignment, readOnly) {
  const panel = $("#assignmentDetailPanel");
  const lowerGrid = $(".lower-grid");
  const active = Boolean(assignment);
  panel.classList.toggle("hidden", !active);
  lowerGrid.classList.toggle("hidden", active && assignmentSubTab !== "submissions");
  if (!assignment) return;

  $("#detailAssignmentTitle").textContent = assignment.title;
  $("#detailAssignmentMeta").textContent = `${assignment.submissionCount} 篇提交 · 均分 ${scoreText(assignment.avgScore)}`;
  $("#assignmentDetailActions").innerHTML = `
    ${readOnly ? "" : `<button class="mini-btn" data-edit-assignment="${escapeHtml(assignment.id)}" type="button">编辑</button>`}
    ${assignment.reportPath ? `<button class="mini-btn" data-assignment-report="${escapeHtml(assignment.reportPath)}" type="button">审题</button>` : ""}
    ${readOnly && !assignment.summaryReportPath ? "" : `<button class="mini-btn" data-assignment-summary="${escapeHtml(assignment.id)}" data-summary-report="${escapeHtml(readOnly ? (assignment.summaryReportPath || "") : "")}" type="button">总结</button>`}
    <button class="mini-btn" data-export-assignment="${escapeHtml(assignment.id)}" type="button">导出</button>
    ${readOnly ? "" : `<button class="mini-btn" data-rejudge-assignment="${escapeHtml(assignment.id)}" data-title="${escapeHtml(assignment.title)}" data-count="${escapeHtml(assignment.submissionCount)}" type="button">重判</button>`}
    ${readOnly ? "" : `<button class="mini-danger" data-delete-assignment="${escapeHtml(assignment.id)}" data-title="${escapeHtml(assignment.title)}" data-count="${escapeHtml(assignment.submissionCount)}" type="button">删除</button>`}
  `;
  $$("#assignmentDetailPanel [data-assignment-subtab]").forEach(button => {
    const isSubmit = button.dataset.assignmentSubtab === "submit";
    button.classList.toggle("hidden", readOnly && isSubmit);
    button.classList.toggle("active", button.dataset.assignmentSubtab === assignmentSubTab);
  });
}

function renderAssignments(assignments) {
  const box = $("#assignmentList");
  if (!assignments.length) {
    box.className = "side-list empty";
    box.textContent = "暂无作业";
    return;
  }
  box.className = "side-list";
  box.innerHTML = assignments.map(item => `
    <div class="side-item assignment-item ${item.id === selectedAssignmentId ? "selected" : ""}" data-open-assignment="${escapeHtml(item.id)}">
      <div class="assignment-main">
        <strong>${escapeHtml(item.title)}</strong>
        <span>${item.submissionCount} 篇提交 · 均分 ${scoreText(item.avgScore)}</span>
      </div>
    </div>
  `).join("");
}

function renderStudents(students) {
  const box = $("#studentList");
  if (!students.length) {
    box.className = "side-list empty";
    box.textContent = "暂无学生";
    return;
  }
  box.className = "side-list";
  box.innerHTML = students.map(item => `
    <button class="side-item student-item ${item.student === selectedStudentId ? "selected" : ""}" data-open-student="${escapeHtml(item.student)}" type="button">
      <strong>${escapeHtml(item.student)}</strong>
      <span>${item.submissionCount} 篇 · 均分 ${scoreText(item.avgScore)} · 变化 ${item.trend >= 0 ? "+" : ""}${item.trend}</span>
    </button>
  `).join("");
}

function studentRows(student, submissions) {
  return (submissions || [])
    .filter(row => row.student === student)
    .slice()
    .sort((a, b) => String(a.createdAt || "").localeCompare(String(b.createdAt || "")));
}

function scoreColor(score) {
  if (typeof score !== "number") return "#eef1ed";
  const ratio = Math.max(0, Math.min(1, score / SCORE_MAX));
  const hue = 12 + ratio * 125;
  const light = 91 - ratio * 38;
  return `hsl(${hue.toFixed(0)} 48% ${light.toFixed(0)}%)`;
}

function dateKey(value) {
  if (!value) return "";
  const text = String(value);
  const direct = text.match(/^\d{4}-\d{2}-\d{2}/);
  if (direct) return direct[0];
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return "";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function localDateFromKey(key) {
  const [year, month, day] = String(key).split("-").map(Number);
  return new Date(year, month - 1, day);
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function dayKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function activityLevel(count) {
  if (!count) return 0;
  if (count === 1) return 1;
  if (count === 2) return 2;
  if (count <= 4) return 3;
  return 4;
}

function scoreBandLabel(score) {
  if (typeof score !== "number") return "未评分";
  if (score >= 50) return "一类";
  if (score >= 40) return "二类";
  if (score >= 30) return "三类";
  if (score >= 20) return "四类";
  return "五类";
}

function renderStudentScoreChart(rows) {
  const scored = rows.filter(row => typeof row.score === "number");
  if (!scored.length) return `<div class="empty-chart">暂无可绘制分数</div>`;
  const w = Math.max(720, 140 + scored.length * 92);
  const h = 280;
  const left = 52, right = 28, top = 28, bottom = 52;
  const plotW = w - left - right;
  const plotH = h - top - bottom;
  const x = index => left + (scored.length === 1 ? plotW / 2 : index / (scored.length - 1) * plotW);
  const y = score => top + (SCORE_MAX - Math.max(0, Math.min(SCORE_MAX, score))) / SCORE_MAX * plotH;
  const pts = scored.map((row, index) => ({ row, x: x(index), y: y(row.score) }));
  const poly = pts.map(point => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  return `
    <svg viewBox="0 0 ${w} ${h}" role="img" aria-label="学生分数走势">
      <rect width="100%" height="100%" rx="10" fill="#fbfcfa"></rect>
      ${[0, 20, 30, 40, 50, 60].map(score => `
        <line x1="${left}" y1="${y(score).toFixed(1)}" x2="${w - right}" y2="${y(score).toFixed(1)}" stroke="#dbe2dc"></line>
        <text x="${left - 10}" y="${(y(score) + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="#66736d">${score}</text>
      `).join("")}
      <polyline fill="none" stroke="#13735b" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="${poly}"></polyline>
      ${pts.map((point, index) => `
        <circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="5" fill="${scoreColor(point.row.score)}" stroke="#1f2b26" stroke-width="1"></circle>
        <text x="${point.x.toFixed(1)}" y="${(point.y - 10).toFixed(1)}" text-anchor="middle" font-size="12" fill="#1f2b26">${scoreText(point.row.score)}</text>
        <text x="${point.x.toFixed(1)}" y="${h - 22}" text-anchor="middle" font-size="11" fill="#66736d">第${index + 1}篇</text>
      `).join("")}
    </svg>
  `;
}

function renderStudentHeatmap(rows) {
  const byDay = new Map();
  rows.forEach(row => {
    const key = dateKey(row.createdAt);
    if (!key) return;
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key).push(row);
  });
  const todayKey = dayKey(new Date());
  let start = addDays(localDateFromKey(todayKey), -ACTIVITY_WEEKS * 7 + 1);
  const end = localDateFromKey(todayKey);
  start = addDays(start, -start.getDay());
  const days = [];
  for (let cursor = new Date(start); cursor <= end; cursor = addDays(cursor, 1)) {
    days.push(dayKey(cursor));
  }
  while (days.length % 7 !== 0) {
    days.push(dayKey(addDays(localDateFromKey(days[days.length - 1]), 1)));
  }
  const weeks = [];
  for (let index = 0; index < days.length; index += 7) weeks.push(days.slice(index, index + 7));
  const monthLabels = [];
  weeks.forEach((week, index) => {
    const firstDayOfMonth = week.find(key => localDateFromKey(key).getDate() === 1);
    if (firstDayOfMonth) {
      const first = localDateFromKey(firstDayOfMonth);
      monthLabels.push({ index, label: `${first.getMonth() + 1}月` });
    }
  });
  if (!monthLabels.length && weeks.length) {
    const first = localDateFromKey(weeks[0][0]);
    monthLabels.push({ index: 0, label: `${first.getMonth() + 1}月` });
  }
  const monthLabelMap = new Map(monthLabels.map(item => [item.index, item.label]));
  const daily = `
    <section class="activity-heatmap">
      <div class="activity-months">
        ${weeks.map((_, index) => `<span>${escapeHtml(monthLabelMap.get(index) || "")}</span>`).join("")}
      </div>
      <div class="activity-body">
        <div class="activity-days"><span>日</span><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span></div>
        <div class="activity-grid">
          ${weeks.map(week => week.map(key => {
            const dayRows = byDay.get(key) || [];
            const scored = dayRows.filter(row => typeof row.score === "number");
            const avgScore = scored.length ? scored.reduce((sum, row) => sum + row.score, 0) / scored.length : null;
            const disabled = key > todayKey ? "future" : "";
            const title = `${key} · ${dayRows.length} 篇${avgScore === null ? "" : ` · 均分 ${scoreText(avgScore)}`}`;
            return `<button class="activity-cell level-${activityLevel(dayRows.length)} ${disabled}" type="button" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}"></button>`;
          }).join("")).join("")}
        </div>
      </div>
      <div class="activity-legend"><span>少</span><i class="level-0"></i><i class="level-1"></i><i class="level-2"></i><i class="level-3"></i><i class="level-4"></i><span>多</span></div>
    </section>
  `;

  const byAssignment = new Map();
  rows.forEach(row => {
    const key = row.assignmentId || row.assignmentTitle || "unknown";
    if (!byAssignment.has(key)) byAssignment.set(key, { title: row.assignmentTitle || key, rows: [] });
    byAssignment.get(key).rows.push(row);
  });
  if (!byAssignment.size) return `${daily}<p class="muted">暂无作业记录。</p>`;
  const assignmentHeatmap = Array.from(byAssignment.values()).map(group => `
    <section class="heat-row">
      <strong title="${escapeHtml(group.title)}">${escapeHtml(group.title)}</strong>
      <div class="heat-cells">
        ${group.rows.map(row => `
          <button class="heat-cell" data-report="${escapeHtml(row.reportPath || "")}" ${row.reportPath ? "" : "disabled"} style="background:${scoreColor(row.score)}" type="button" title="v${escapeHtml(row.versionNo)} · ${scoreText(row.score)} · ${escapeHtml(row.detectedGenre || "未判断")}">
            <span>${scoreText(row.score)}</span>
          </button>
        `).join("")}
      </div>
    </section>
  `).join("");
  return `${daily}<div class="assignment-heatmap">${assignmentHeatmap}</div>`;
}
function renderMiniBars(items, { max = null } = {}) {
  const total = items.reduce((sum, item) => sum + item.value, 0);
  const peak = max || Math.max(1, total);
  return `
    <div class="mini-bars">
      ${items.map((item, index) => {
        const width = peak ? item.value / peak * 100 : 0;
        return `
        <div class="mini-bar-row">
          <span>${escapeHtml(item.label)}</span>
          <progress class="bar-meter bar-c-${index % CHART_COLORS.length}" value="${width.toFixed(1)}" max="100" aria-label="${escapeHtml(item.label)}占比"></progress>
          <strong>${item.value}</strong>
        </div>
      `;
      }).join("")}
    </div>
  `;
}

function renderStudentMix(rows) {
  const bandCounts = ["一类", "二类", "三类", "四类", "五类", "未评分"].map(label => ({
    label,
    value: rows.filter(row => scoreBandLabel(row.score) === label).length,
  })).filter(item => item.value);
  const genreMap = new Map();
  rows.forEach(row => {
    const genre = row.detectedGenre || "未判断";
    genreMap.set(genre, (genreMap.get(genre) || 0) + 1);
  });
  const genreCounts = Array.from(genreMap, ([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value).slice(0, 6);
  const revisionItems = [
    { label: "初稿", value: rows.filter(row => !row.isRevision).length },
    { label: "修改稿", value: rows.filter(row => row.isRevision).length },
  ].filter(item => item.value);
  return `
    <div class="student-mix-grid">
      <section><h4>档位</h4>${renderMiniBars(bandCounts)}</section>
      <section><h4>文体</h4>${renderMiniBars(genreCounts)}</section>
      <section><h4>版本</h4>${renderMiniBars(revisionItems, { max: rows.length || 1 })}</section>
    </div>
  `;
}

function renderStudentEssayCards(items, emptyText) {
  if (!items.length) return `<p class="muted">${escapeHtml(emptyText)}</p>`;
  return items.map(row => {
    const genre = escapeHtml(row.detectedGenre || "\u672a\u5224\u65ad");
    return `
      <article class="student-recent-card">
        <div>
          <strong>${escapeHtml(row.assignmentTitle)}</strong>
          <span>v${escapeHtml(row.versionNo)} &middot; ${genre}</span>
        </div>
        <b style="background:${scoreColor(row.score)}">${scoreText(row.score)}</b>
        <div class="row-actions">
          ${row.radar?.available ? `<button class="tiny-btn" data-radar-submission="${escapeHtml(row.id)}" type="button">\u96f7\u8fbe</button>` : ""}
          ${row.reportPath ? `<button class="tiny-btn" data-report="${escapeHtml(row.reportPath)}" type="button">\u62a5\u544a</button><button class="tiny-btn" data-report-pdf="${escapeHtml(row.reportPath)}" type="button">PDF</button>` : ""}
        </div>
      </article>
    `;
  }).join("");
}
/*
  if (!items.length) return `<p class="muted">${escapeHtml(emptyText)}</p>`;
  return items.map(row => `
    <article class="student-recent-card">
      <div>
        <strong>${escapeHtml(row.assignmentTitle)}</strong>
        <span>v${escapeHtml(row.versionNo)} · ${escapeHtml(row.detectedGenre || "未判断")}</span>
      </div>
      <b style="background:${scoreColor(row.score)}">${scoreText(row.score)}</b>
      <div class="row-actions">
        ${row.radar?.available ? `<button class="tiny-btn" data-radar-submission="${escapeHtml(row.id)}" type="button">雷达</button>` : ""}
        ${row.reportPath ? `<button class="tiny-btn" data-report="${escapeHtml(row.reportPath)}" type="button">报告</button><button class="tiny-btn" data-report-pdf="${escapeHtml(row.reportPath)}" type="button">PDF</button>` : ""}
      </div>
    </article>
  `).join("");
}

*/

function renderStudentRecentCards(rows) {
  const recent = latestSubmissionRows(rows)
    .sort((a, b) => String(b.createdAt || "").localeCompare(String(a.createdAt || "")))
    .slice(0, 6);
  return renderStudentEssayCards(recent, "\u6682\u65e0\u4f5c\u6587\u8bb0\u5f55\u3002");
}
/*
  return renderStudentEssayCards(recent, "暂无作文记录。");
  if (!recent.length) return `<p class="muted">暂无作文记录。</p>`;
  return recent.map(row => `
    <article class="student-recent-card">
      <div>
        <strong>${escapeHtml(row.assignmentTitle)}</strong>
        <span>v${escapeHtml(row.versionNo)} · ${escapeHtml(row.detectedGenre || "未判断")}</span>
      </div>
      <b style="background:${scoreColor(row.score)}">${scoreText(row.score)}</b>
      <div class="row-actions">
        ${row.radar?.available ? `<button class="tiny-btn" data-radar-submission="${escapeHtml(row.id)}" type="button">雷达</button>` : ""}
        ${row.reportPath ? `<button class="tiny-btn" data-report="${escapeHtml(row.reportPath)}" type="button">报告</button><button class="tiny-btn" data-report-pdf="${escapeHtml(row.reportPath)}" type="button">PDF</button>` : ""}
      </div>
    </article>
  `).join("");
}

*/

function renderStudentLowestCards(rows) {
  const lowest = latestSubmissionRows(rows)
    .filter(row => typeof row.score === "number")
    .sort((a, b) => (a.score - b.score) || String(b.createdAt || "").localeCompare(String(a.createdAt || "")))
    .slice(0, 5);
  return renderStudentEssayCards(lowest, "\u6682\u65e0\u5df2\u8bc4\u5206\u7ec8\u7a3f\u3002");
}
/*
  return renderStudentEssayCards(lowest, "暂无已评分终稿。");
}

*/

function renderStudentDetail(student, submissions) {
  const panel = $("#studentDetailPanel");
  const active = Boolean(student);
  panel.classList.toggle("hidden", !active);
  if (!student) return;
  const rows = studentRows(student.student, submissions);
  const scored = rows.filter(row => typeof row.score === "number");
  const scores = scored.map(row => row.score);
  const best = scored.slice().sort((a, b) => b.score - a.score)[0];
  const latest = rows[rows.length - 1];
  const radar = radarAverage(finalDraftRows(rows));
  $("#studentDetailName").textContent = student.student;
  $("#studentDetailMeta").textContent = `${rows.length} 篇作文 · ${scored.length} 篇已评分 · 最近 ${latest ? formatDateTime(latest.createdAt) : "暂无"}`;
  $("#studentKpis").innerHTML = [
    ["均分", scoreText(student.avgScore)],
    ["最高", best ? scoreText(best.score) : "—"],
    ["趋势", `${student.trend >= 0 ? "+" : ""}${student.trend}`],
    ["终稿雷达", radar.available ? `${scoreText(radar.average)}/20` : "—"],
  ].map(([label, value]) => `<div><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  $("#studentScoreSummary").textContent = scores.length ? `最高 ${scoreText(Math.max(...scores))} · 最低 ${scoreText(Math.min(...scores))}` : "暂无评分";
  $("#studentScoreChart").innerHTML = renderStudentScoreChart(rows);
  $("#studentRadar").innerHTML = radar.available
    ? renderRadarSvg(radar.dimensions, { size: 520 })
    : `<div class="empty-chart">暂无雷达数据</div>`;
  $("#studentRadarData").innerHTML = radar.available
    ? renderRadarData(radar.dimensions)
    : `<div class="empty-chart">暂无八方面数据</div>`;  $("#studentHeatmap").innerHTML = renderStudentHeatmap(rows);
  $("#studentMix").innerHTML = renderStudentMix(rows);
  $("#studentLowestCards").innerHTML = renderStudentLowestCards(rows);
  $("#studentRecentCards").innerHTML = renderStudentRecentCards(rows);
}

function formatDateTime(value) {
  if (!value) return "";
  return String(value).replace("T", " ").slice(0, 16);
}

function renderStyleReports(reports) {
  const box = $("#styleReportList");
  if (!box) return;
  const items = (reports || []).filter(item => item.type === "style_report" && item.path).slice(0, 12);
  if (!items.length) {
    box.innerHTML = `<p class="muted">暂无旧风格报告。</p>`;
    return;
  }
  box.innerHTML = `
    <div class="report-list-head">
      <strong>旧风格报告</strong>
      <span>${items.length} 份</span>
    </div>
    ${items.map(item => `
      <div class="report-list-item">
        <div>
          <strong>${escapeHtml(formatDateTime(item.createdAt) || "风格报告")}</strong>
          <span>${escapeHtml(item.model || "本地数学汇总")}</span>
        </div>
        <div class="row-actions">
          <button class="tiny-btn" data-style-report-view="${escapeHtml(item.path)}" type="button">查看</button>
          <button class="tiny-btn" data-style-report-pdf="${escapeHtml(item.pdfPath || item.path)}" type="button">PDF</button>
        </div>
      </div>
    `).join("")}
  `;
}

function renderAssignmentSelect(assignments) {
  const select = $("#assignmentSelect");
  const current = select.value;
  select.innerHTML = assignments.length
    ? assignments.map(item => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.title)}</option>`).join("")
    : `<option value="">先新建作业</option>`;
  if (selectedAssignmentId && assignments.some(item => item.id === selectedAssignmentId)) {
    select.value = selectedAssignmentId;
  } else if (assignments.some(item => item.id === current)) {
    select.value = current;
  }
}

function ensurePolling(active) {
  if (active && !pollTimer) {
    pollTimer = setInterval(() => refresh(true).catch(err => toast(err.message)), 2600);
  }
  if (!active && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function rowVersion(row) {
  if (row.versionNo !== null && row.versionNo !== undefined && row.versionNo !== "") return Number(row.versionNo) || 0;
  if (row.isJob && row.type === "rejudge") return Number(row.versionNo) || 0;
  return row.isRevision ? 1 : 0;
}

function recentSortValue(row, key) {
  switch (key) {
    case "student":
      return row.student || "";
    case "assignment":
      return row.assignmentTitle || "";
    case "version":
      return rowVersion(row);
    case "score":
      return typeof row.score === "number" ? row.score : null;
    case "genre":
      return row.isJob ? "待判断" : (row.detectedGenre || "未判断");
    case "fit":
      if (row.isJob) return row.status === "error" ? "需处理" : "等待报告";
      return row.genreFit || "未判断";
    case "createdAt":
      return row.createdAt || "";
    default:
      return "";
  }
}

function compareSortValue(a, b, key, dir = "asc") {
  const av = recentSortValue(a, key);
  const bv = recentSortValue(b, key);
  const aEmpty = av === null || av === undefined || av === "";
  const bEmpty = bv === null || bv === undefined || bv === "";
  if (aEmpty && bEmpty) return 0;
  if (aEmpty) return 1;
  if (bEmpty) return -1;
  let result;
  if (typeof av === "number" && typeof bv === "number") {
    result = av - bv;
  } else {
    result = String(av).localeCompare(String(bv), "zh-Hans-CN", { numeric: true, sensitivity: "base" });
  }
  return dir === "desc" ? -result : result;
}

function sortRecentRows(rows) {
  const secondary = [
    ["assignment", "asc"],
    ["student", "asc"],
    ["version", "asc"],
    ["createdAt", "desc"],
  ];
  return rows.slice().sort((a, b) => {
    let result = compareSortValue(a, b, recentSort.key, recentSort.dir);
    if (result) return result;
    for (const [key, dir] of secondary) {
      if (key === recentSort.key) continue;
      result = compareSortValue(a, b, key, dir);
      if (result) return result;
    }
    return String(a.id || "").localeCompare(String(b.id || ""), "zh-Hans-CN", { numeric: true });
  });
}

function renderRecentSortHeaders() {
  $$("[data-sort]").forEach(button => {
    const active = button.dataset.sort === recentSort.key;
    button.classList.toggle("active", active);
    button.setAttribute("aria-sort", active ? (recentSort.dir === "asc" ? "ascending" : "descending") : "none");
    const arrow = button.querySelector(".sort-arrow");
    if (arrow) arrow.textContent = active ? (recentSort.dir === "asc" ? "↑" : "↓") : "";
  });
}

function renderFailedJobActions(row, readOnly) {
  if (readOnly) {
    return `<span class="muted" title="${escapeHtml(row.message || "")}">失败</span>`;
  }
  return `
    <div class="row-actions">
      ${row.submissionId ? `<button class="tiny-btn" data-rejudge-submission="${escapeHtml(row.submissionId)}" data-student="${escapeHtml(row.student)}" data-assignment-title="${escapeHtml(row.assignmentTitle)}" data-version="${escapeHtml(row.versionNo || "")}" type="button" title="${escapeHtml(row.message || "")}">重判</button>` : ""}
      <button class="tiny-btn danger-text" data-delete-job="${escapeHtml(row.id)}" data-student="${escapeHtml(row.student)}" data-assignment-title="${escapeHtml(row.assignmentTitle)}" type="button" title="${escapeHtml(row.message || "")}">删除</button>
    </div>
  `;
}

function renderRecent(rows, jobs, assignmentId = null) {
  const body = $("#recentRows");
  const readOnly = isReadOnly();
  const scopedJobs = assignmentId ? jobs.filter(job => job.assignmentId === assignmentId) : jobs;
  const scopedRows = assignmentId ? rows.filter(row => row.assignmentId === assignmentId) : rows;
  const activeJobSubmissionIds = new Set(
    scopedJobs
      .filter(job => ["queued", "running"].includes(job.status) && job.submissionId)
      .map(job => job.submissionId)
  );
  const pendingRows = scopedJobs
    .filter(job => ["queued", "running", "error"].includes(job.status))
    .map(job => ({ ...job, isJob: true }));
  const allRows = sortRecentRows([...pendingRows, ...scopedRows.filter(row => !activeJobSubmissionIds.has(row.id))]);
  renderRecentSortHeaders();
  if (!allRows.length) {
    body.innerHTML = `<tr><td colspan="7" class="muted">${assignmentId ? "该作业暂无评分任务" : "暂无提交"}</td></tr>`;
    return;
  }
  body.innerHTML = allRows.map(row => {
    if (row.isJob) {
      const isError = row.status === "error";
      const isRejudge = row.type === "rejudge";
      const statusText = isError
        ? (isRejudge ? "重判失败" : "评分失败")
        : (row.status === "queued" ? (isRejudge ? "重判排队" : "排队中") : (isRejudge ? "重判中" : "评分中"));
      return `
        <tr class="job-row ${isError ? "error" : ""}">
          <td><strong>${escapeHtml(row.student)}</strong></td>
          <td>${escapeHtml(row.assignmentTitle)}</td>
          <td>${isRejudge ? `重判 v${escapeHtml(row.versionNo || "")}` : (row.isRevision ? "修改稿" : "新提交")}</td>
          <td><span class="pill ${isError ? "warn" : "live"}">${statusText}</span></td>
          <td>待判断</td>
          <td><span class="pill">${isError ? "需处理" : (isRejudge ? "等待新报告" : "等待报告")}</span></td>
          <td>
            ${isError
              ? renderFailedJobActions(row, readOnly)
              : `<button class="tiny-btn disabled" type="button" disabled title="${escapeHtml(row.message || "")}">未完成</button>`}
          </td>
        </tr>
      `;
    }
    const fit = row.genreFit || "未判断";
    const warn = /错位|四不像/.test(fit);
    return `
      <tr>
        <td><strong>${escapeHtml(row.student)}</strong></td>
        <td>${escapeHtml(row.assignmentTitle)}</td>
        <td>v${escapeHtml(row.versionNo)}${row.isRevision ? " · 修改稿" : ""}</td>
        <td class="score">${scoreText(row.score)}</td>
        <td>${escapeHtml(row.detectedGenre || "未判断")}</td>
        <td><span class="pill ${warn ? "warn" : ""}">${escapeHtml(fit)}</span></td>
        <td>
          <div class="row-actions">
            ${row.radar?.available ? `<button class="tiny-btn" data-radar-submission="${escapeHtml(row.id)}" type="button">雷达</button>` : ""}
            ${row.reportPath ? `<button class="tiny-btn" data-report="${escapeHtml(row.reportPath)}" type="button">查看</button><button class="tiny-btn" data-report-pdf="${escapeHtml(row.reportPath)}" type="button">PDF</button>` : ""}
            ${readOnly ? "" : `<button class="tiny-btn" data-rejudge-submission="${escapeHtml(row.id)}" data-student="${escapeHtml(row.student)}" data-assignment-title="${escapeHtml(row.assignmentTitle)}" data-version="${escapeHtml(row.versionNo)}" type="button">重判</button>`}
            ${readOnly ? "" : `<button class="tiny-btn danger-text" data-delete-submission="${escapeHtml(row.id)}" data-student="${escapeHtml(row.student)}" data-assignment-title="${escapeHtml(row.assignmentTitle)}" data-version="${escapeHtml(row.versionNo)}" type="button">删除</button>`}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function renderSparkline(rows) {
  const scores = rows
    .slice()
    .reverse()
    .filter(row => typeof row.score === "number")
    .slice(-12);
  const box = $("#sparkline");
  if (!scores.length) {
    box.innerHTML = `<svg viewBox="0 0 600 170" role="img"><text x="24" y="88" fill="#66736d" font-size="16">暂无可绘制的分数</text></svg>`;
    return;
  }
  const w = 600, h = 170, pad = 24;
  const step = scores.length === 1 ? 0 : (w - pad * 2) / (scores.length - 1);
  const pts = scores.map((row, i) => {
    const x = scores.length === 1 ? w / 2 : pad + i * step;
    const score = Math.max(0, Math.min(SCORE_MAX, Number(row.score)));
    const y = pad + (SCORE_MAX - score) / SCORE_MAX * (h - pad * 2);
    return { x, y, row };
  });
  const poly = pts.map(p => `${p.x},${p.y}`).join(" ");
  box.innerHTML = `
    <svg viewBox="0 0 ${w} ${h}" role="img">
      <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="#dbe2dc"/>
      <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${h - pad}" stroke="#dbe2dc"/>
      <polyline fill="none" stroke="#13735b" stroke-width="3" points="${poly}"/>
      ${pts.map(p => `<circle cx="${p.x}" cy="${p.y}" r="5" fill="#c25545"><title>${escapeHtml(p.row.student)} ${scoreText(p.row.score)}</title></circle>`).join("")}
    </svg>
  `;
}

function radarDimensions(row) {
  const dimensions = row?.radar?.dimensions || [];
  const byKey = Object.fromEntries(dimensions.map(item => [item.key, item]));
  return RADAR_DIMENSIONS.map(dim => {
    const item = byKey[dim.key] || {};
    const score = typeof item.score === "number" ? item.score : null;
    return { ...dim, score, raw: item.raw || "", source: item.source || "" };
  });
}

function hasRadar(row) {
  return Boolean(row?.radar?.available && radarDimensions(row).some(item => typeof item.score === "number"));
}

function radarAverage(rows) {
  const buckets = Object.fromEntries(RADAR_DIMENSIONS.map(dim => [dim.key, []]));
  rows.filter(hasRadar).forEach(row => {
    radarDimensions(row).forEach(item => {
      if (typeof item.score === "number") buckets[item.key].push(item.score);
    });
  });
  const dimensions = RADAR_DIMENSIONS.map(dim => {
    const values = buckets[dim.key];
    return {
      ...dim,
      score: values.length ? Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(1)) : null,
      count: values.length,
    };
  });
  const scored = dimensions.filter(item => typeof item.score === "number");
  return {
    available: scored.length >= 4,
    dimensions,
    average: scored.length ? Number((scored.reduce((sum, item) => sum + item.score, 0) / scored.length).toFixed(1)) : null,
  };
}

function finalDraftRows(rows) {
  return latestSubmissionRows(rows, { requireRadar: true });
}

function latestSubmissionRows(rows, { requireRadar = false } = {}) {
  const latestByAssignment = new Map();
  rows.forEach(row => {
    if (requireRadar && !hasRadar(row)) return;
    const key = `${row.student || ""}::${row.assignmentId || row.assignmentTitle || ""}`;
    const current = latestByAssignment.get(key);
    const rowVersion = Number(row.versionNo) || 0;
    const currentVersion = Number(current?.versionNo) || 0;
    if (
      !current ||
      rowVersion > currentVersion ||
      (rowVersion === currentVersion && String(row.createdAt || "") > String(current.createdAt || ""))
    ) {
      latestByAssignment.set(key, row);
    }
  });
  return Array.from(latestByAssignment.values());
}

function initialDraftRows(rows) {
  const earliestByAssignment = new Map();
  rows.forEach(row => {
    if (!hasRadar(row)) return;
    const key = `${row.student || ""}::${row.assignmentId || row.assignmentTitle || ""}`;
    const current = earliestByAssignment.get(key);
    const rowVersion = Number(row.versionNo) || 0;
    const currentVersion = Number(current?.versionNo) || 0;
    if (
      !current ||
      rowVersion < currentVersion ||
      (rowVersion === currentVersion && String(row.createdAt || "") < String(current.createdAt || ""))
    ) {
      earliestByAssignment.set(key, row);
    }
  });
  return Array.from(earliestByAssignment.values());
}

function radarPoint(cx, cy, radius, index, total, value = 1) {
  const angle = -Math.PI / 2 + index * Math.PI * 2 / total;
  const r = radius * value;
  return {
    x: cx + Math.cos(angle) * r,
    y: cy + Math.sin(angle) * r,
  };
}

function pointsAttr(points) {
  return points.map(point => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
}

function renderRadarSvg(dimensions, { size = 250, compact = false } = {}) {
  const count = dimensions.length || RADAR_DIMENSIONS.length;
  const cx = size / 2;
  const cy = size / 2;
  const radius = compact ? size * 0.29 : size * 0.31;
  const labelRadius = compact ? size * 0.41 : size * 0.43;
  const rings = [0.25, 0.5, 0.75, 1];
  const safeDimensions = dimensions.length ? dimensions : RADAR_DIMENSIONS.map(dim => ({ ...dim, score: 0 }));
  const scoredDimensions = safeDimensions.filter(item => typeof item.score === "number");
  const centerScore = scoredDimensions.length
    ? Math.round(scoredDimensions.reduce((sum, item) => sum + item.score, 0) / scoredDimensions.length)
    : 0;
  const polygon = safeDimensions.map((item, index) => radarPoint(cx, cy, radius, index, count, Math.max(0, Math.min(20, item.score || 0)) / 20));
  const axes = safeDimensions.map((_, index) => radarPoint(cx, cy, radius, index, count, 1));
  const labels = safeDimensions.map((item, index) => {
    const point = radarPoint(cx, cy, labelRadius, index, count, 1);
    const anchor = Math.abs(point.x - cx) < 8 ? "middle" : (point.x > cx ? "start" : "end");
    return `<text x="${point.x.toFixed(1)}" y="${point.y.toFixed(1)}" text-anchor="${anchor}" dominant-baseline="middle">${escapeHtml(item.label)}</text>`;
  }).join("");
  return `
    <svg class="radar-svg" viewBox="0 0 ${size} ${size}" role="img">
      ${rings.map(ring => `<polygon class="radar-ring" points="${pointsAttr(axes.map((_, index) => radarPoint(cx, cy, radius, index, count, ring)))}"></polygon>`).join("")}
      ${axes.map(point => `<line class="radar-axis" x1="${cx}" y1="${cy}" x2="${point.x.toFixed(1)}" y2="${point.y.toFixed(1)}"></line>`).join("")}
      <polygon class="radar-area" points="${pointsAttr(polygon)}"></polygon>
      <polyline class="radar-line" points="${pointsAttr([...polygon, polygon[0]])}"></polyline>
      ${polygon.map((point, index) => `<circle class="radar-dot" cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="${compact ? 2.4 : 3.2}"><title>${escapeHtml(safeDimensions[index].label)} ${safeDimensions[index].score ?? "—"}/20</title></circle>`).join("")}
      <text class="radar-center" x="${cx}" y="${cy + 4}" text-anchor="middle">${escapeHtml(String(centerScore))}</text>
      ${labels}
    </svg>
  `;
}

function renderRadarData(dimensions) {
  return `
    <div class="radar-data-grid">
      ${dimensions.map((item, index) => {
        const score = typeof item.score === "number" ? Math.max(0, Math.min(20, item.score)) : null;
        const width = score === null ? 0 : score / 20 * 100;
        return `
        <div class="radar-data-item">
          <span>${escapeHtml(item.label)}</span>
          <strong>${typeof item.score === "number" ? `${scoreText(item.score)} / 20` : "—"}</strong>
          <progress class="radar-score-bar bar-meter bar-c-${index % CHART_COLORS.length}" value="${width.toFixed(1)}" max="100" aria-label="${escapeHtml(item.label)}得分占比"></progress>
        </div>
      `;
      }).join("")}
    </div>
  `;
}
function radarOverviewCards(submissions, students, pickRows) {
  const studentNames = students.map(item => item.student);
  return studentNames.map(student => {
    const rows = pickRows(submissions.filter(row => row.student === student));
    const radar = radarAverage(rows);
    return { student, rows, radar };
  });
}

function renderRadarCardGrid(cards, draftLabel) {
  return cards.map(card => `
    <section class="radar-card ${card.radar.available ? "" : "empty"}">
      <div class="radar-card-head">
        <div>
          <strong>${escapeHtml(card.student)}</strong>
          <span>${card.radar.available ? `${card.rows.length} 篇${draftLabel} · 均值 ${scoreText(card.radar.average)} / 20` : "暂无雷达数据"}</span>
        </div>
      </div>
      ${card.radar.available ? renderRadarSvg(card.radar.dimensions, { size: 240, compact: true }) : `<div class="radar-empty">暂无</div>`}
      ${card.radar.available ? renderRadarData(card.radar.dimensions) : ""}
    </section>
  `).join("");
}

function renderRadarOverview(submissions, students) {
  const grid = $("#radarGrid");
  if (!grid) return;
  const finalCards = radarOverviewCards(submissions, students, finalDraftRows);
  const initialCards = radarOverviewCards(submissions, students, initialDraftRows);
  const finalAvailable = finalCards.filter(item => item.radar.available);
  const initialAvailable = initialCards.filter(item => item.radar.available);
  const currentCards = radarSubTab === "initial" ? initialCards : finalCards;
  const currentAvailable = radarSubTab === "initial" ? initialAvailable : finalAvailable;
  const currentLabel = radarSubTab === "initial" ? "初稿" : "终稿";
  const totalCards = finalCards.length;
  $$("#radarPanel [data-radar-subtab]").forEach(button => {
    button.classList.toggle("active", button.dataset.radarSubtab === radarSubTab);
  });
  $("#radarSummary").textContent = totalCards
    ? `终稿 ${finalAvailable.length}/${totalCards} 名 · ${finalAvailable.reduce((sum, item) => sum + item.rows.length, 0)} 篇；初稿 ${initialAvailable.length}/${totalCards} 名 · ${initialAvailable.reduce((sum, item) => sum + item.rows.length, 0)} 篇`
    : "暂无可用雷达数据";
  if (!currentCards.length) {
    grid.innerHTML = `<p class="muted">暂无学生数据。新评分完成后会自动出现。</p>`;
    return;
  }
  grid.innerHTML = `
    <section class="radar-section">
      <div class="radar-section-head">
        <h4>${currentLabel}雷达图</h4>
        <span>${currentAvailable.length} 名学生可用</span>
      </div>
      <div class="radar-grid">${renderRadarCardGrid(currentCards, currentLabel)}</div>
    </section>
  `;
}

function openSubmissionRadar(submissionId) {
  currentReportPath = null;
  const row = (appState?.submissions || appState?.recentSubmissions || []).find(item => item.id === submissionId);
  if (!row || !hasRadar(row)) {
    toast("这篇作文暂无可用雷达数据。");
    return;
  }
  const dimensions = radarDimensions(row);
  $("#reportModalEyebrow").textContent = "Essay Radar";
  $("#reportModalTitle").textContent = `${row.student}《${row.assignmentTitle}》v${row.versionNo} 雷达图`;
  $("#reportModalBody").className = "report-modal-body radar-mode";
  $("#reportModalBody").innerHTML = `
    <section class="radar-detail">
      <div class="radar-detail-chart">
        ${renderRadarSvg(dimensions, { size: 430 })}
      </div>
      <div class="radar-detail-data">
        <h2 class="report-heading">八方面数据</h2>
        ${renderRadarData(dimensions)}
        <div class="report-table-wrap">
          <table class="report-table">
            <thead><tr><th>维度</th><th>分值</th><th>来源/原始说明</th></tr></thead>
            <tbody>
              ${dimensions.map(item => `
                <tr>
                  <td>${escapeHtml(item.label)}</td>
                  <td>${typeof item.score === "number" ? `${scoreText(item.score)} / 20` : "—"}</td>
                  <td>${escapeHtml(item.raw || item.source || "—")}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  `;
  $("#reportModal").classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function markdownToHtml(markdown, options = {}) {
  const mode = options.mode || "review";
  const lines = String(markdown || "").split(/\r?\n/);
  const out = [];
  let inList = false;
  let fieldBlock = [];
  let tableBlock = [];

  const closeFieldBlock = () => {
    if (!fieldBlock.length) return;
    out.push(renderFieldBlock(fieldBlock, mode));
    fieldBlock = [];
  };

  const closeTableBlock = () => {
    if (!tableBlock.length) return;
    out.push(renderMarkdownTable(tableBlock));
    tableBlock = [];
  };

  const closeList = () => {
    if (inList) {
      out.push("</ul>");
      inList = false;
    }
  };

  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index];
    if (rawLine.trim() === "<!-- raw-html:start -->") {
      closeList();
      closeFieldBlock();
      closeTableBlock();
      const rawHtml = [];
      index += 1;
      while (index < lines.length && lines[index].trim() !== "<!-- raw-html:end -->") {
        rawHtml.push(lines[index]);
        index += 1;
      }
      out.push(rawHtml.join("\n"));
      continue;
    }
    let line = escapeHtml(rawLine);
    if (isTableLine(line)) {
      closeList();
      closeFieldBlock();
      tableBlock.push(line);
      continue;
    }
    closeTableBlock();
    const field = parseFieldLine(line);
    if (field && mode !== "summary") {
      closeList();
      if (fieldBlock.some(item => item.key === field.key)) {
        closeFieldBlock();
      }
      fieldBlock.push(field);
      continue;
    }
    closeFieldBlock();
    if (/^### /.test(line)) {
      closeList();
      out.push(`<h3 class="report-subtitle ${mode === "assignment" ? "assignment-subtitle" : ""}">${line.slice(4)}</h3>`);
    } else if (/^## /.test(line)) {
      if (mode === "review" && isGenreSummaryHeading(line.slice(3))) {
        closeList();
        const compact = collectGenreSummarySections(lines, index);
        out.push(renderGenreSummaryTable(compact.items));
        index = compact.nextIndex - 1;
        continue;
      }
      closeList();
      out.push(`<h2 class="report-heading ${mode === "assignment" ? "assignment-heading" : ""}">${line.slice(3)}</h2>`);
    } else if (/^# /.test(line)) {
      closeList();
      out.push(`<h1 class="report-title">${line.slice(2)}</h1>`);
    } else if (/^- /.test(line)) {
      if (!inList) { out.push("<ul>"); inList = true; }
      out.push(`<li>${line.slice(2)}</li>`);
    } else if (line.trim() === "") {
      closeList();
    } else {
      closeList();
      out.push(`<p>${line}</p>`);
    }
  }
  closeTableBlock();
  closeFieldBlock();
  closeList();
  return out.join("").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>").replace(/`(.*?)`/g, "<code>$1</code>");
}

const GENRE_SUMMARY_HEADINGS = new Set([
  "任务类型判断",
  "题目期待文体",
  "实际文体",
  "文体判断依据",
  "文体匹配",
  "文体专项评价",
  "文体分数上限提示",
  "档次判断",
]);

function isGenreSummaryHeading(value) {
  return GENRE_SUMMARY_HEADINGS.has(String(value || "").trim());
}

function collectGenreSummarySections(lines, startIndex) {
  const items = [];
  let index = startIndex;
  while (index < lines.length && /^## /.test(lines[index])) {
    const label = lines[index].slice(3).trim();
    if (!isGenreSummaryHeading(label)) break;
    index += 1;
    const content = [];
    while (index < lines.length && !/^#{1,3} /.test(lines[index])) {
      if (lines[index].trim()) content.push(lines[index].trim());
      index += 1;
    }
    items.push({ label, value: content.join("<br>") || "—" });
  }
  return { items, nextIndex: index };
}

function renderGenreSummaryTable(items) {
  if (!items.length) return "";
  const rows = items.map(item => `
    <tr>
      <th scope="row">${item.label}</th>
      <td>${renderCellContent(item.value)}</td>
    </tr>
  `).join("");
  return `
    <div class="report-table-wrap genre-summary-wrap">
      <table class="report-table genre-summary-table">
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function normalizeScoreScaleMarkdown(markdown) {
  let text = String(markdown || "");
  const score60Match = text.match(/-\s*\*\*(?:final_total_60|total_60|最终 60 分|60 分参考)\*\*[:：]\s*(\d+(?:\.\d+)?)/);
  if (score60Match) {
    return text.replace(/\*\*总分：[^*\n]+\/\s*100\*\*/g, `**总分：${score60Match[1]} / 60**`);
  }
  return text.replace(/\*\*总分：\s*(\d+(?:\.\d+)?)\s*\/\s*100\*\*/g, (_, score) => {
    const converted = Math.round(Number(score) / 100 * SCORE_MAX);
    return `**总分：${converted} / 60**`;
  });
}

function isTableLine(line) {
  return /^\s*\|.*\|\s*$/.test(line);
}

function splitTableRow(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(cell => cell.trim());
}

function isSeparatorRow(cells) {
  return cells.length > 0 && cells.every(cell => /^:?-{3,}:?$/.test(cell.replace(/\s+/g, "")));
}

function renderCellContent(value) {
  return (value || "").replace(/&lt;br\s*\/?&gt;/gi, "<br>");
}

function renderMarkdownTable(lines) {
  const rows = lines.map(splitTableRow).filter(row => row.length);
  if (!rows.length) return "";
  const hasHeader = rows.length > 1 && isSeparatorRow(rows[1]);
  const header = hasHeader ? rows[0] : null;
  const bodyRows = hasHeader ? rows.slice(2) : rows;
  const headerHtml = header
    ? `<thead><tr>${header.map(cell => `<th scope="col">${renderCellContent(cell)}</th>`).join("")}</tr></thead>`
    : "";
  const bodyHtml = `<tbody>${bodyRows.map(row => `<tr>${row.map(cell => `<td>${renderCellContent(cell)}</td>`).join("")}</tr>`).join("")}</tbody>`;
  return `<div class="report-table-wrap"><table class="report-table">${headerHtml}${bodyHtml}</table></div>`;
}

function parseFieldLine(line) {
  const match = line.match(/^(?:-\s*)+\*\*([^*]+)\*\*[:：Ŗē]\s*(.*)$/);
  if (!match) return null;
  return { key: match[1].trim(), value: match[2].trim() };
}

function parseFieldLine(line) {
  const match = line.match(/^(?:-\s*)+\*\*([^*]+)\*\*[:：]\s*(.*)$/);
  if (!match) return null;
  return { key: match[1].trim(), value: match[2].trim() };
}

function priorityClass(value) {
  const text = String(value || "").toLowerCase();
  const num = Number((text.match(/\d+/) || [])[0]);
  if (num >= 3 || /高|严重|urgent|high/.test(text)) return "high";
  if (num === 2 || /中|medium/.test(text)) return "medium";
  return "low";
}

function labelForKey(key, mode = "review") {
  const reviewLabels = {
    quote: "原文",
    problem: "问题",
    reason: "原因",
    suggestion: "修改建议",
    priority: "优先级",
    score: "分数",
    total_60: "60 分参考",
    content_20: "内容",
    expression_20: "表达",
    development_20: "发展",
    band_reason: "定档理由",
    content_band: "内容档次",
    expression_band: "表达档次",
    development_band: "发展档次",
    initial_total_band: "初定档位/分数",
    hard_caps: "硬性上限",
    penalties: "扣分项",
    final_total_60: "最终 60 分",
    final_band_reason: "最终定档理由",
    overall: "整体评价",
    score_change_reason: "分数变化",
    previous_review_response: "回应上次批阅",
    changes: "修改明细",
    change_type: "修改类型",
    review_basis: "对应上次批阅",
    before: "上一稿",
    after: "本稿",
    what_changed: "改动内容",
    effect: "修改效果",
    evidence: "证据",
    remaining_issue: "遗留问题",
    new_problems: "新增问题",
    keep_next_time: "下次保留",
  };
  const assignmentLabels = {
    assignment_type: "任务类型",
    assignment_type_reason: "判断依据",
    genre: "文体",
    suitable_genre: "适合文体",
    suitability: "适配度",
    reason: "理由",
    keyword: "关键词",
    angle: "角度",
    main_idea: "主旨",
    risk: "风险",
    explicit: "显性限制",
    implicit: "隐性限制",
    core_task: "核心任务",
    scoring_focus: "评分关注",
    pitfalls: "常见风险",
    teaching_notes: "教学提醒",
    student_brief: "学生提示",
  };
  const labels = mode === "assignment" ? { ...reviewLabels, ...assignmentLabels } : reviewLabels;
  return labels[key] || key;
}

function fitClass(value) {
  const text = String(value || "").toLowerCase();
  if (/高|high/.test(text)) return "high";
  if (/低|low/.test(text)) return "low";
  return "medium";
}

function renderAssignmentFieldBlock(fields) {
  const keys = fields.map(item => item.key);
  const map = Object.fromEntries(fields.map(item => [item.key, item.value]));
  const isGenre = keys.some(key => ["genre", "suitability"].includes(key));
  const isThesis = keys.some(key => ["keyword", "angle", "main_idea", "risk", "suitable_genre"].includes(key));
  const isConstraint = keys.some(key => ["explicit", "implicit", "assignment_type_reason"].includes(key));
  if (isGenre || isThesis || isConstraint) {
    const title = map.genre || map.angle || map.keyword || map.assignment_type || (isConstraint ? "题目边界" : "审题要点");
    const hidden = new Set(["genre", "suitability", "keyword", "angle", "assignment_type"]);
    return `
      <section class="planning-card ${map.risk ? "risk-card" : ""}">
        <div class="planning-head">
          <strong>${title}</strong>
          ${map.suitability ? `<span class="fit-pill ${fitClass(map.suitability)}">适配度 ${map.suitability}</span>` : ""}
        </div>
        ${fields.filter(item => !hidden.has(item.key)).map(item => `
          <p class="${item.key === "risk" ? "plan-risk" : ""}">
            <span>${labelForKey(item.key, "assignment")}</span>${item.value || "—"}
          </p>
        `).join("")}
      </section>
    `;
  }
  return `
    <div class="field-grid planning-grid">
      ${fields.map(item => `
        <div class="field-item">
          <span>${labelForKey(item.key, "assignment")}</span>
          <strong>${item.value || "—"}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function renderFieldBlock(fields, mode = "review") {
  if (mode === "assignment") return renderAssignmentFieldBlock(fields);
  const visibleFields = fields.filter(item => !["consistency_check", "converted_score_100"].includes(item.key));
  if (!visibleFields.length) return "";
  const keys = visibleFields.map(item => item.key);
  const map = Object.fromEntries(visibleFields.map(item => [item.key, item.value]));
  const strictReasonKeys = new Set(["final_band_reason", "最终定档理由"]);
  const strictFieldKeys = new Set([
    "content_band",
    "expression_band",
    "development_band",
    "final_total_60",
    "内容档次",
    "表达档次",
    "发展档次",
    "最终 60 分",
  ]);
  const isStrictReason = item => strictReasonKeys.has(item.key);
  const isIssue = keys.some(key => ["quote", "problem", "reason", "suggestion", "priority"].includes(key));
  if (isIssue) {
    const priority = map.priority;
    return `
      <section class="diagnosis-card">
        <div class="diagnosis-head">
          <strong>${map.problem || "问题诊断"}</strong>
          ${priority ? `<span class="priority ${priorityClass(priority)}">${labelForKey("priority", mode)} ${priority}</span>` : ""}
        </div>
        ${map.quote ? `<blockquote>${map.quote}</blockquote>` : ""}
        ${map.reason ? `<p><span>原因</span>${map.reason}</p>` : ""}
        ${map.suggestion ? `<p><span>建议</span>${map.suggestion}</p>` : ""}
        ${visibleFields.filter(item => !["quote", "problem", "reason", "suggestion", "priority"].includes(item.key)).map(item => `<p><span>${labelForKey(item.key, mode)}</span>${item.value}</p>`).join("")}
      </section>
    `;
  }
  const isRevisionChange = keys.some(key => ["change_type", "review_basis", "before", "after", "what_changed", "effect", "evidence", "remaining_issue"].includes(key));
  if (isRevisionChange) {
    return `
      <section class="diagnosis-card revision-card">
        <div class="diagnosis-head">
          <strong>${map.change_type ? `${labelForKey("change_type", mode)}：${map.change_type}` : "修改明细"}</strong>
        </div>
        ${map.review_basis ? `<p><span>${labelForKey("review_basis", mode)}</span>${map.review_basis}</p>` : ""}
        ${map.before ? `<blockquote class="before-after"><span>${labelForKey("before", mode)}</span>${map.before}</blockquote>` : ""}
        ${map.after ? `<blockquote class="before-after after"><span>${labelForKey("after", mode)}</span>${map.after}</blockquote>` : ""}
        ${map.what_changed ? `<p><span>${labelForKey("what_changed", mode)}</span>${map.what_changed}</p>` : ""}
        ${map.effect ? `<p><span>${labelForKey("effect", mode)}</span>${map.effect}</p>` : ""}
        ${map.evidence ? `<p><span>${labelForKey("evidence", mode)}</span>${map.evidence}</p>` : ""}
        ${map.remaining_issue ? `<p><span>${labelForKey("remaining_issue", mode)}</span>${map.remaining_issue}</p>` : ""}
        ${visibleFields.filter(item => !["change_type", "review_basis", "before", "after", "what_changed", "effect", "evidence", "remaining_issue"].includes(item.key)).map(item => `<p><span>${labelForKey(item.key, mode)}</span>${item.value}</p>`).join("")}
      </section>
    `;
  }
  const scoreReference = keys.includes("band_reason") && keys.some(key => ["total_60", "content_20", "expression_20", "development_20"].includes(key));
  const strictBanding = keys.some(key => strictReasonKeys.has(key)) && keys.some(key => strictFieldKeys.has(key));
  const orderedFields = scoreReference
    ? [...visibleFields.filter(item => item.key !== "band_reason"), ...visibleFields.filter(item => item.key === "band_reason")]
    : strictBanding
      ? [...visibleFields.filter(item => !isStrictReason(item)), ...visibleFields.filter(item => isStrictReason(item))]
      : visibleFields;
  const strictColumnCount = strictBanding
    ? Math.min(7, Math.max(1, orderedFields.filter(item => !isStrictReason(item)).length))
    : 0;
  return `
    <div class="field-grid ${scoreReference ? "score-reference-grid" : ""} ${strictBanding ? "strict-banding-grid" : ""}" ${strictBanding ? `style="--strict-columns: ${strictColumnCount};"` : ""}>
      ${orderedFields.map(item => `
        <div class="field-item ${item.key === "priority" ? `priority-field ${priorityClass(item.value)}` : ""} ${(scoreReference && item.key === "band_reason") || (strictBanding && isStrictReason(item)) ? "wide-field reason-field" : ""}">
          <span>${labelForKey(item.key, mode)}</span>
          <strong>${item.value || "—"}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function extractMarkdownTitle(markdown) {
  const match = String(markdown || "").match(/^#\s+(.+)$/m);
  return match ? match[1].trim() : "";
}

function reportMode(data) {
  const name = data.name || "";
  const path = data.path || "";
  const content = data.content || "";
  if (data.kind === "svg") return "visual";
  if (/assignment_summary_.*\.md$/i.test(name) || /assignment_summary_.*\.md$/i.test(path) || /作业总结/.test(content)) {
    return "summary";
  }
  if (
    name === "assignment_analysis.md" ||
    /assignment_analysis\.md$/i.test(path) ||
    /^#\s+《.+》审题分析/m.test(content) ||
    content.includes("## AI 审题")
  ) {
    return "assignment";
  }
  return "review";
}

function reportEyebrow(mode) {
  return {
    assignment: "Assignment Planner",
    summary: "Assignment Summary",
    visual: "Visual Report",
    review: "Essay Review",
  }[mode] || "Report Reader";
}

async function loadReport(path) {
  if (!path) return;
  currentReportPath = path;
  const data = await api(`/api/report?path=${encodeURIComponent(path)}`, { method: "GET", headers: {} });
  const mode = reportMode(data);
  const content = data.kind === "svg" ? data.content : normalizeScoreScaleMarkdown(data.content);
  const title = extractMarkdownTitle(content) || data.name || "报告预览";
  const html = data.kind === "svg" ? data.content : markdownToHtml(content, { mode });
  $("#reportModalEyebrow").textContent = reportEyebrow(mode);
  $("#reportModalTitle").textContent = title;
  $("#reportModalBody").className = `report-modal-body ${mode}-mode`;
  $("#reportModalBody").innerHTML = html;
  openReportModal();
}

function openReportModal() {
  $("#reportModal").classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeReportModal() {
  $("#reportModal").classList.add("hidden");
  document.body.classList.remove("modal-open");
}

function splitStudents(value) {
  return value.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean);
}

function findAssignment(id) {
  return (appState?.assignments || []).find(item => item.id === id);
}

function closeAssignmentEdit() {
  $("#assignmentEditModal").classList.add("hidden");
}

function openAssignmentEdit(id) {
  const assignment = findAssignment(id);
  if (!assignment) {
    toast("找不到这次作业。");
    return;
  }
  const form = $("#assignmentEditForm");
  form.elements.id.value = assignment.id;
  form.elements.title.value = assignment.title || "";
  form.elements.topic.value = assignment.topic || "";
  form.elements.writingType.value = assignment.writingType || "auto";
  if (form.elements.writingType.value !== (assignment.writingType || "auto")) {
    form.elements.writingType.value = "auto";
  }
  $("#assignmentEditModal").classList.remove("hidden");
  form.elements.title.focus();
}

async function updateAssignmentFromForm(formEl) {
  const submitButton = formEl.querySelector("button[type='submit']");
  const originalButtonHtml = submitButton ? submitButton.innerHTML : "";
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.innerHTML = "正在重新审题";
  }
  const form = new FormData(formEl);
  try {
    const data = await api("/api/assignment-update", {
      method: "POST",
      body: JSON.stringify({
        id: form.get("id"),
        title: form.get("title"),
        topic: form.get("topic"),
        writingType: form.get("writingType"),
      }),
    });
    closeAssignmentEdit();
    selectedAssignmentId = data.assignmentId || form.get("id");
    const count = Number(data.submissionCount || 0);
    if (data.reanalyzed && count > 0) {
      const ok = await confirmAction({
        title: "是否重判这次作业？",
        body: `审题报告已经更新。是否把这次作业下的 ${count} 篇提交全部重新评分？`,
        okText: "重判这次作业",
        danger: false,
      });
      if (ok) await rejudgeAssignment(selectedAssignmentId);
    }
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.innerHTML = originalButtonHtml;
    }
  }
}

function confirmAction({ title, body, okText = "确认删除", danger = true }) {
  return new Promise(resolve => {
    confirmResolver = resolve;
    $("#confirmTitle").textContent = title;
    $("#confirmBody").textContent = body;
    $("#confirmOk").textContent = okText;
    $("#confirmOk").classList.toggle("danger", danger);
    $("#confirmModal").classList.remove("hidden");
  });
}

function closeConfirm(result) {
  $("#confirmModal").classList.add("hidden");
  if (confirmResolver) {
    confirmResolver(result);
    confirmResolver = null;
  }
}

async function deleteTarget(kind, id) {
  await api("/api/delete", {
    method: "POST",
    body: JSON.stringify({ kind, id }),
  });
}

async function rejudgeSubmission(id) {
  await api("/api/rejudge", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
}

async function rejudgeAssignment(id) {
  await api("/api/rejudge-assignment", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
}

async function openAssignmentSummary(id, cachedPath = "") {
  if (cachedPath) {
    await loadReport(cachedPath);
    return;
  }
  const data = await api("/api/assignment-summary", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
  if (data.path) await loadReport(data.path);
}

async function exportAssignmentPdf(id) {
  if (!isReadOnly()) {
    await api("/api/assignment-summary", {
      method: "POST",
      body: JSON.stringify({ id }),
    });
  }
  window.open(`/api/export/assignment-pdf?id=${encodeURIComponent(id)}`, "_blank");
}

function exportRadarPdf() {
  window.open(`/api/export/radar-pdf?draft=${encodeURIComponent(radarSubTab)}`, "_blank");
}

function exportReportPdf(path) {
  if (!path) {
    toast("没有可导出的报告路径。");
    return;
  }
  const link = document.createElement("a");
  link.href = `/api/export/report-pdf?path=${encodeURIComponent(path)}`;
  link.download = "";
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function handleAssignmentActionClick(event) {
  const edit = event.target.closest("[data-edit-assignment]");
  if (edit) {
    openAssignmentEdit(edit.dataset.editAssignment);
    return true;
  }
  const summary = event.target.closest("[data-assignment-summary]");
  if (summary) {
    openAssignmentSummary(summary.dataset.assignmentSummary, summary.dataset.summaryReport).catch(err => toast(err.message));
    return true;
  }
  const exportBtn = event.target.closest("[data-export-assignment]");
  if (exportBtn) {
    exportAssignmentPdf(exportBtn.dataset.exportAssignment).catch(err => toast(err.message));
    return true;
  }
  const report = event.target.closest("[data-assignment-report]");
  if (report) {
    loadReport(report.dataset.assignmentReport).catch(err => toast(err.message));
    return true;
  }
  const rejudge = event.target.closest("[data-rejudge-assignment]");
  if (rejudge) {
    const count = Number(rejudge.dataset.count || 0);
    const ok = confirmAction({
      title: "重判整次作业？",
      body: `将重新调用 AI 重判《${rejudge.dataset.title}》下的 ${count} 篇提交，并覆盖这些提交当前评分和报告。操作完成后可逐次用“恢复上一步”撤销。`,
      okText: "重判整次作业",
      danger: false,
    });
    ok.then(confirmed => {
      if (confirmed) rejudgeAssignment(rejudge.dataset.rejudgeAssignment).catch(err => toast(err.message));
    });
    return true;
  }
  const del = event.target.closest("[data-delete-assignment]");
  if (del) {
    confirmAction({
      title: "删除这次作业？",
      body: `将从界面中删除《${del.dataset.title}》，并移除它下面的 ${del.dataset.count} 篇提交记录。原始文件会保留，必要时可用“恢复上一步”找回记录。`,
      okText: "删除这次作业",
    }).then(confirmed => {
      if (confirmed) deleteTarget("assignment", del.dataset.deleteAssignment).catch(err => toast(err.message));
    });
    return true;
  }
  return false;
}

function bindEvents() {
  $$(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
      activateTab(tab.dataset.tab);
    });
  });

  $("#refreshBtn").addEventListener("click", refresh);

  $("#exportRadarPdf")?.addEventListener("click", () => {
    exportRadarPdf();
  });

  $("#radarPanel").addEventListener("click", event => {
    const subtab = event.target.closest("[data-radar-subtab]");
    if (!subtab) return;
    radarSubTab = subtab.dataset.radarSubtab === "initial" ? "initial" : "final";
    render();
  });

  $("#assignmentDetailPanel").addEventListener("click", event => {
    const subtab = event.target.closest("[data-assignment-subtab]");
    if (subtab) {
      assignmentSubTab = subtab.dataset.assignmentSubtab;
      render();
      return;
    }
    handleAssignmentActionClick(event);
  });

  $("#assignmentList").addEventListener("click", event => {
    const item = event.target.closest("[data-open-assignment]");
    if (item) {
      if (selectedAssignmentId !== item.dataset.openAssignment) assignmentSubTab = "submissions";
      selectedAssignmentId = item.dataset.openAssignment;
      selectedStudentId = null;
      render();
    }
  });

  $("#studentList").addEventListener("click", event => {
    const item = event.target.closest("[data-open-student]");
    if (item) {
      selectedStudentId = item.dataset.openStudent;
      selectedAssignmentId = null;
      assignmentSubTab = "submissions";
      render();
    }
  });

  $("#studentDetailPanel").addEventListener("click", event => {
    const radarBtn = event.target.closest("[data-radar-submission]");
    if (radarBtn) {
      openSubmissionRadar(radarBtn.dataset.radarSubmission);
      return;
    }
    const pdfBtn = event.target.closest("[data-report-pdf]");
    if (pdfBtn && pdfBtn.dataset.reportPdf) {
      exportReportPdf(pdfBtn.dataset.reportPdf);
      return;
    }
    const reportBtn = event.target.closest("[data-report]");
    if (reportBtn && reportBtn.dataset.report) {
      loadReport(reportBtn.dataset.report).catch(err => toast(err.message));
    }
  });

  $("#backToWorkspace").addEventListener("click", () => {
    selectedAssignmentId = null;
    selectedStudentId = null;
    assignmentSubTab = "submissions";
    render();
  });

  $("#saveConfig").addEventListener("click", async () => {
    await api("/api/config", {
      method: "POST",
      body: JSON.stringify({
        apiKey: $("#apiKey").value.trim(),
        model: $("#model").value.trim(),
        apiBase: $("#apiBase").value.trim(),
      }),
    });
    $("#apiKey").value = "";
  });

  $("#assignmentEditForm").addEventListener("submit", async event => {
    event.preventDefault();
    updateAssignmentFromForm(event.currentTarget).catch(err => toast(err.message));
  });

  $("#assignmentForm").addEventListener("submit", async event => {
    event.preventDefault();
    const submitButton = event.currentTarget.querySelector("button[type='submit']");
    const originalButtonHtml = submitButton ? submitButton.innerHTML : "";
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.innerHTML = "<span>…</span>正在生成审题分析";
    }
    const form = new FormData(event.currentTarget);
    try {
      await api("/api/assignments", {
        method: "POST",
        body: JSON.stringify({
          title: form.get("title"),
          topic: form.get("topic"),
          writingType: form.get("writingType"),
          noAi: form.get("noAi") === "on",
        }),
      });
      event.currentTarget.reset();
    } finally {
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.innerHTML = originalButtonHtml;
      }
    }
  });

  $("#submissionForm").addEventListener("submit", async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await api("/api/submissions", {
      method: "POST",
      body: JSON.stringify({
        assignment: selectedAssignmentId || form.get("assignment"),
        student: form.get("student"),
        content: form.get("content"),
        manualScore: form.get("manualScore"),
        revision: form.get("revision") === "on",
        initial: form.get("initial") === "on",
        noAi: form.get("noAi") === "on",
      }),
    });
    toast("已转入后台评分，可以继续查看作业。报告完成后会自动出现。");
    event.currentTarget.querySelector("textarea").value = "";
  });

  $("#curveBtn").addEventListener("click", async () => {
    await api("/api/curves", {
      method: "POST",
      body: JSON.stringify({ students: splitStudents($("#curveStudents").value) }),
    });
  });

  $("#styleBtn").addEventListener("click", async () => {
    const data = await api("/api/style-report", {
      method: "POST",
      body: JSON.stringify({
        students: splitStudents($("#styleStudents").value),
        noAi: true,
      }),
    });
    if (data.pdfPath || data.path) exportReportPdf(data.pdfPath || data.path);
  });

  $("#styleReportList")?.addEventListener("click", event => {
    const view = event.target.closest("[data-style-report-view]");
    if (view) {
      loadReport(view.dataset.styleReportView).catch(err => toast(err.message));
      return;
    }
    const pdf = event.target.closest("[data-style-report-pdf]");
    if (pdf) {
      exportReportPdf(pdf.dataset.styleReportPdf);
    }
  });

  $("#recentTable").addEventListener("click", event => {
    const sortButton = event.target.closest("[data-sort]");
    if (!sortButton) return;
    const key = sortButton.dataset.sort;
    if (recentSort.key === key) {
      recentSort = { key, dir: recentSort.dir === "asc" ? "desc" : "asc" };
    } else {
      recentSort = { key, dir: key === "score" ? "desc" : "asc" };
    }
    if (appState) render();
  });

  $("#recentRows").addEventListener("click", event => {
    const radarBtn = event.target.closest("[data-radar-submission]");
    if (radarBtn) {
      openSubmissionRadar(radarBtn.dataset.radarSubmission);
      return;
    }
    const pdfBtn = event.target.closest("[data-report-pdf]");
    if (pdfBtn && pdfBtn.dataset.reportPdf) {
      exportReportPdf(pdfBtn.dataset.reportPdf);
      return;
    }
    const btn = event.target.closest("[data-report]");
    if (btn) {
      loadReport(btn.dataset.report);
      return;
    }
    const rejudge = event.target.closest("[data-rejudge-submission]");
    if (rejudge) {
      const ok = confirmAction({
        title: "完全重判这次提交？",
        body: `将重新调用 AI 覆盖 ${rejudge.dataset.student} 的《${rejudge.dataset.assignmentTitle}》v${rejudge.dataset.version} 当前评分和报告。操作完成后可用“恢复上一步”撤销。`,
        okText: "确认重判",
        danger: false,
      });
      ok.then(confirmed => {
        if (confirmed) rejudgeSubmission(rejudge.dataset.rejudgeSubmission).catch(err => toast(err.message));
      });
      return;
    }
    const jobDel = event.target.closest("[data-delete-job]");
    if (jobDel) {
      const ok = confirmAction({
        title: "删除失败任务？",
        body: `只删除 ${jobDel.dataset.student} 的《${jobDel.dataset.assignmentTitle}》后台失败记录，不会删除作文提交或报告文件。`,
        okText: "删除失败任务",
      });
      ok.then(confirmed => {
        if (confirmed) deleteTarget("job", jobDel.dataset.deleteJob).catch(err => toast(err.message));
      });
      return;
    }
    const del = event.target.closest("[data-delete-submission]");
    if (del) {
      const ok = confirmAction({
        title: "删除这次提交？",
        body: `将从界面中删除 ${del.dataset.student} 的《${del.dataset.assignmentTitle}》v${del.dataset.version}。原始文件会保留，必要时可用“恢复上一步”找回记录。`,
        okText: "删除这次提交",
      });
      ok.then(confirmed => {
        if (confirmed) deleteTarget("submission", del.dataset.deleteSubmission).catch(err => toast(err.message));
      });
    }
  });

  $("#undoBtn").addEventListener("click", async () => {
    const ok = await confirmAction({
      title: "恢复上一步操作？",
      body: appState?.undo?.last ? `将恢复：${appState.undo.last}` : "没有可恢复的操作。",
      okText: "恢复上一步",
      danger: false,
    });
    if (!ok) return;
    await api("/api/undo", { method: "POST", body: "{}" });
  });

  $("#confirmCancel").addEventListener("click", () => closeConfirm(false));
  $("#confirmOk").addEventListener("click", () => closeConfirm(true));
  $("#confirmModal").addEventListener("click", event => {
    if (event.target.id === "confirmModal") closeConfirm(false);
  });
  $("#assignmentEditCancel").addEventListener("click", closeAssignmentEdit);
  $("#assignmentEditModal").addEventListener("click", event => {
    if (event.target.id === "assignmentEditModal") closeAssignmentEdit();
  });
  $("#reportModalClose").addEventListener("click", closeReportModal);
  $("#reportModalExport")?.addEventListener("click", () => {
    exportReportPdf(currentReportPath);
  });
  $("#reportModal").addEventListener("click", event => {
    if (event.target.id === "reportModal") closeReportModal();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !$("#assignmentEditModal").classList.contains("hidden")) closeAssignmentEdit();
    if (event.key === "Escape" && !$("#reportModal").classList.contains("hidden")) closeReportModal();
  });
}

bindEvents();
refresh().catch(err => toast(err.message));
