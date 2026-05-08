const adminState = {
  digests: [],
  pipelineRuns: [],
  pipelineRunsError: "",
  sourceHealthFilter: "all",
  sourceHealthSort: "age_desc",
  selectedHealthDate: "",
  selectedDigestDate: "",
  readSurface: {
    digests: "",
    pipelineRuns: "",
  },
};

const statusEl = document.getElementById("status");
const refreshButton = document.getElementById("refreshButton");
const adminSummaryEl = document.getElementById("adminSummary");
const digestDiagnosticDateEl = document.getElementById("digestDiagnosticDate");
const digestMetaQualityEl = document.getElementById("digestMetaQuality");
const digestMetaDeliveryEl = document.getElementById("digestMetaDelivery");
const clusterPanelEl = document.getElementById("clusterPanel");
const clusterListEl = document.getElementById("clusterList");
const pipelineRunListEl = document.getElementById("pipelineRunList");
const sourceHealthListEl = document.getElementById("sourceHealthList");
const sourceHealthFilterEl = document.getElementById("sourceHealthFilter");
const sourceHealthSortEl = document.getElementById("sourceHealthSort");
const sourceHealthDateEl = document.getElementById("sourceHealthDate");

refreshButton.addEventListener("click", () => loadAdmin());
sourceHealthFilterEl.addEventListener("change", () => {
  adminState.sourceHealthFilter = String(sourceHealthFilterEl.value || "all");
  renderSourceHealth();
});
sourceHealthSortEl.addEventListener("change", () => {
  adminState.sourceHealthSort = String(sourceHealthSortEl.value || "age_desc");
  renderSourceHealth();
});
sourceHealthDateEl.addEventListener("change", () => {
  adminState.selectedHealthDate = String(sourceHealthDateEl.value || "");
  renderSourceHealth();
});
digestDiagnosticDateEl.addEventListener("change", () => {
  adminState.selectedDigestDate = String(digestDiagnosticDateEl.value || "");
  renderDigestDiagnostics();
});

loadAdmin();

async function loadAdmin() {
  setStatus("Loading...");
  try {
    const config = DigestShared.getConfig();
    const digestRead = await DigestShared.fetchDigests(config);
    adminState.digests = digestRead.rows;
    adminState.readSurface.digests = digestRead.relation;

    const runsRead = await DigestShared.fetchPipelineRuns(config);
    adminState.pipelineRuns = runsRead.rows;
    adminState.readSurface.pipelineRuns = runsRead.relation;
    adminState.pipelineRunsError = "";
    adminState.selectedHealthDate = adminState.selectedHealthDate || inferLatestDigestDate();
    adminState.selectedDigestDate = adminState.selectedDigestDate || adminState.digests[0]?.digest_date || "";

    renderAdminSummary();
    renderDigestDiagnosticDateOptions();
    renderDigestDiagnostics();
    renderPipelineRuns();
    renderSourceHealthDateOptions();
    renderSourceHealth();
    setStatus("Ready.");
  } catch (error) {
    adminState.pipelineRunsError = String(error?.message || error || "Failed to load admin data.");
    renderAdminSummary();
    renderDigestDiagnosticDateOptions();
    renderDigestDiagnostics();
    renderPipelineRuns();
    renderSourceHealth();
    setStatus(adminState.pipelineRunsError, true);
  }
}

function renderDigestDiagnosticDateOptions() {
  if (!digestDiagnosticDateEl) {
    return;
  }
  const dates = adminState.digests.map((digest) => String(digest.digest_date || "")).filter(Boolean);
  if (!dates.includes(adminState.selectedDigestDate) && dates.length) {
    adminState.selectedDigestDate = dates[0];
  }
  digestDiagnosticDateEl.innerHTML = dates
    .map((date) => {
      const selected = date === adminState.selectedDigestDate ? " selected" : "";
      return `<option value="${DigestShared.escapeHtml(date)}"${selected}>${DigestShared.escapeHtml(date)}</option>`;
    })
    .join("");
}

function renderDigestDiagnostics() {
  const digest = adminState.digests.find((item) => item.digest_date === adminState.selectedDigestDate);
  if (!digest) {
    setMetricRows(digestMetaQualityEl, []);
    setMetricRows(digestMetaDeliveryEl, []);
    renderClusters([]);
    return;
  }

  const summary = digest?.json_summary || {};
  const candidateMode = summary.candidate_mode === true;
  const coverage = summary.candidate_translated_coverage;
  const fallbackReason = summary.candidate_fallback_reason || "";
  const topClusters = Array.isArray(summary.top_clusters) ? summary.top_clusters : [];
  const model = digest?.model || "-";
  const digestRun = DigestShared.findLatestRunForJobAndDate(
    adminState.pipelineRuns,
    "generate_digest",
    digest?.digest_date || ""
  );
  const digestRunStats = DigestShared.normalizeStats(digestRun?.stats);
  const validationMode = String(digestRunStats.validation_mode || digestRunStats.digest_mode || "-");
  const validationReason = String(digestRunStats.validation_reason || fallbackReason || "");
  const qualityRows = [
    ["Candidate mode", candidateMode ? "enabled" : "disabled", candidateMode ? "ok" : ""],
    ["Candidate count", summary.candidate_count ?? "-", ""],
    ["Candidate coverage", DigestShared.formatPercent(coverage), coverage >= 0.7 ? "ok" : "warn"],
    ["Raw item count", summary.item_count ?? "-", ""],
  ];
  const deliveryRows = [
    ["Model", model, ""],
    ["Validation mode", validationMode, validationMode === "normal" ? "ok" : "warn"],
    ["API surface", buildReadSurfaceLabel(), ""],
    ["Fallback reason", validationReason || "-", validationReason ? "warn" : ""],
  ];
  setMetricRows(digestMetaQualityEl, qualityRows);
  setMetricRows(digestMetaDeliveryEl, deliveryRows);
  renderClusters(topClusters);
}

function setMetricRows(container, rows) {
  if (!container) {
    return;
  }
  container.innerHTML = rows
    .map(([label, value, cls]) => {
      const clsName = cls ? `meta-value ${cls}` : "meta-value";
      return `
        <div class="meta-row">
          <span class="meta-label">${DigestShared.escapeHtml(String(label))}</span>
          <span class="${clsName}">${DigestShared.escapeHtml(String(value))}</span>
        </div>
      `;
    })
    .join("");
}

function renderClusters(topClusters) {
  if (!clusterPanelEl || !clusterListEl) {
    return;
  }
  const rows = Array.isArray(topClusters) ? topClusters.slice(0, 8) : [];
  if (!rows.length) {
    clusterListEl.innerHTML = '<li class="cluster-empty">No cluster detail available.</li>';
    clusterPanelEl.open = false;
    return;
  }
  clusterPanelEl.open = true;
  clusterListEl.innerHTML = rows
    .map((item) => {
      const rank = item.rank ?? "-";
      const score = item.importance_score ?? "-";
      const sourceCount = item.source_count ?? "-";
      return `<li>#${DigestShared.escapeHtml(String(rank))} score=${DigestShared.escapeHtml(String(score))} src=${DigestShared.escapeHtml(String(sourceCount))}</li>`;
    })
    .join("");
}

function renderAdminSummary() {
  if (!adminSummaryEl) {
    return;
  }
  const failedCount = adminState.pipelineRuns.filter(
    (run) => String(run.status || "").toLowerCase() !== "success"
  ).length;
  const lastChainSuccess = DigestShared.findLastChainSuccess(adminState.pipelineRuns) || "none";
  const latestValidateRun = DigestShared.findLatestRunByJob(adminState.pipelineRuns, "validate_digest_inputs");
  const latestValidateStats = DigestShared.normalizeStats(latestValidateRun?.stats);
  const digestMode = String(latestValidateStats.digest_mode || "-");
  const latestAuditRun = DigestShared.findLatestRunByJob(adminState.pipelineRuns, "audit_source_health");
  const latestAuditStats = DigestShared.normalizeStats(latestAuditRun?.stats);
  const sourceHealth = DigestShared.formatSourceHealthCounts(latestAuditStats.source_health_counts) || "-";
  const rows = [
    ["Last full-chain success", lastChainSuccess, lastChainSuccess === "none" ? "warn" : "ok"],
    ["Failed runs in latest 40", failedCount, failedCount === 0 ? "ok" : "warn"],
    ["Latest gate mode", digestMode, digestMode === "normal" ? "ok" : "warn"],
    ["Latest source health", sourceHealth, ""],
    ["Digest read surface", adminState.readSurface.digests || "-", ""],
    ["Runs read surface", adminState.readSurface.pipelineRuns || "-", ""],
  ];
  adminSummaryEl.innerHTML = rows
    .map(([label, value, cls]) => {
      const clsName = cls ? `meta-value ${cls}` : "meta-value";
      return `
        <div class="meta-row">
          <span class="meta-label">${DigestShared.escapeHtml(String(label))}</span>
          <span class="${clsName}">${DigestShared.escapeHtml(String(value))}</span>
        </div>
      `;
    })
    .join("");
}

function renderPipelineRuns() {
  pipelineRunListEl.innerHTML = "";
  if (adminState.pipelineRunsError) {
    const error = document.createElement("div");
    error.className = "run-item-error";
    error.textContent = `Failed to load run history: ${adminState.pipelineRunsError}`;
    pipelineRunListEl.appendChild(error);
    return;
  }
  if (!adminState.pipelineRuns.length) {
    pipelineRunListEl.textContent = "No pipeline runs yet.";
    return;
  }

  for (const run of adminState.pipelineRuns) {
    const item = document.createElement("div");
    item.className = "run-item";
    const status = String(run.status || "").toLowerCase() === "success" ? "success" : "failed";
    const elapsedMs = DigestShared.extractElapsedMs(run);
    const stats = DigestShared.normalizeStats(run.stats);
    const digestDate = stats.digest_date || run.digest_date || "-";
    const coverage = DigestShared.firstNumeric(stats.candidate_coverage, stats.candidate_translated_coverage);
    const candidateCount = DigestShared.firstNumeric(stats.candidate_count, stats.fetched);
    const digestMode = String(stats.digest_mode || stats.validation_mode || "").trim();
    const healthCounts = DigestShared.formatSourceHealthCounts(stats.source_health_counts);
    const extraParts = [
      `date=${digestDate}`,
      `duration=${DigestShared.formatDurationMs(elapsedMs)}`,
      `candidates=${DigestShared.formatMaybeNumber(candidateCount)}`,
      `coverage=${DigestShared.formatPercent(coverage)}`,
    ];
    if (digestMode) {
      extraParts.push(`mode=${digestMode}`);
    }
    if (healthCounts) {
      extraParts.push(`health=${healthCounts}`);
    }
    const rerunHint = status === "failed" ? buildRerunHint(run, stats) : "";
    item.innerHTML = `
      <div class="run-item-head">
        <span class="run-item-title">${DigestShared.escapeHtml(String(run.job_type || "unknown"))}</span>
        <span class="run-badge ${status}">${status === "success" ? "OK" : "FAIL"}</span>
      </div>
      <div class="run-item-meta">${DigestShared.escapeHtml(DigestShared.formatDateTime(run.started_at))}</div>
      <div class="run-item-extra">${DigestShared.escapeHtml(extraParts.join(" | "))}</div>
      ${run.error ? `<div class="run-item-error">${DigestShared.escapeHtml(String(run.error).slice(0, 180))}</div>` : ""}
      ${rerunHint ? `<div class="run-item-hint">${DigestShared.escapeHtml(rerunHint)}</div>` : ""}
    `;
    pipelineRunListEl.appendChild(item);
  }
}

function renderSourceHealthDateOptions() {
  const dates = [...new Set(adminState.pipelineRuns.map((run) => extractRunDate(run)).filter(Boolean))];
  if (!dates.includes(adminState.selectedHealthDate) && dates.length) {
    adminState.selectedHealthDate = dates[0];
  }
  sourceHealthDateEl.innerHTML = dates
    .map((date) => {
      const selected = date === adminState.selectedHealthDate ? " selected" : "";
      return `<option value="${DigestShared.escapeHtml(date)}"${selected}>${DigestShared.escapeHtml(date)}</option>`;
    })
    .join("");
}

function renderSourceHealth() {
  sourceHealthListEl.innerHTML = "";
  if (adminState.pipelineRunsError) {
    sourceHealthListEl.textContent = "Cannot load source health while run history failed.";
    return;
  }
  const auditRun = DigestShared.findLatestRunForJobAndDate(
    adminState.pipelineRuns,
    "audit_source_health",
    adminState.selectedHealthDate
  );
  const auditStats = DigestShared.normalizeStats(auditRun?.stats);
  const rows = Array.isArray(auditStats.source_health) ? auditStats.source_health : [];
  if (!rows.length) {
    sourceHealthListEl.textContent = "No source health data for this date.";
    return;
  }
  const filtered = rows.filter((row) => {
    const status = String(row.status || "unknown");
    return adminState.sourceHealthFilter === "all" || adminState.sourceHealthFilter === status;
  });
  if (!filtered.length) {
    sourceHealthListEl.textContent = "No matching rows under current filter.";
    return;
  }
  const sorted = [...filtered].sort(compareSourceHealthRows);
  for (const row of sorted) {
    const feed = String(row.feed_id || row.source_id || "unknown");
    const status = String(row.status || "unknown");
    const cadence = String(row.cadence || "-");
    const ageHours = typeof row.age_hours === "number" ? `${row.age_hours.toFixed(1)}h` : "-";
    const itemCount = typeof row.item_count === "number" ? row.item_count : "-";
    const latest = row.latest_published_at ? DigestShared.formatDateTime(row.latest_published_at) : "-";
    const card = document.createElement("div");
    card.className = "source-health-item";
    card.innerHTML = `
      <div class="source-health-head">
        <span class="source-health-feed">${DigestShared.escapeHtml(feed)}</span>
        <span class="source-health-status ${DigestShared.escapeHtml(status)}">${DigestShared.escapeHtml(status)}</span>
      </div>
      <div class="source-health-meta">cadence=${DigestShared.escapeHtml(cadence)} | age=${DigestShared.escapeHtml(ageHours)}</div>
      <div class="source-health-meta">items=${DigestShared.escapeHtml(String(itemCount))} | latest=${DigestShared.escapeHtml(latest)}</div>
    `;
    sourceHealthListEl.appendChild(card);
  }
}

function compareSourceHealthRows(a, b) {
  const feedA = String(a.feed_id || a.source_id || "");
  const feedB = String(b.feed_id || b.source_id || "");
  const ageA = typeof a.age_hours === "number" ? a.age_hours : Number.POSITIVE_INFINITY;
  const ageB = typeof b.age_hours === "number" ? b.age_hours : Number.POSITIVE_INFINITY;
  if (adminState.sourceHealthSort === "age_asc") {
    return ageA - ageB || feedA.localeCompare(feedB);
  }
  if (adminState.sourceHealthSort === "feed_asc") {
    return feedA.localeCompare(feedB);
  }
  if (adminState.sourceHealthSort === "status") {
    return sourceStatusRank(String(a.status || "unknown")) - sourceStatusRank(String(b.status || "unknown")) || feedA.localeCompare(feedB);
  }
  return ageB - ageA || feedA.localeCompare(feedB);
}

function sourceStatusRank(status) {
  const ranks = {
    healthy_active: 1,
    healthy_quiet: 2,
    stale: 3,
    no_data: 4,
    unknown: 5,
    disabled: 6,
  };
  return ranks[status] || 9;
}

function buildRerunHint(run, stats) {
  const digestDate = stats.digest_date ? `date=${stats.digest_date}` : "date=<YYYY-MM-DD>";
  const candidateLimit =
    typeof stats.candidate_count === "number" && stats.candidate_count > 0
      ? `candidate_limit=${stats.candidate_count}`
      : "candidate_limit=40";
  const base = `workflow_dispatch: ${digestDate}`;
  const job = String(run.job_type || "");
  if (
    job === "translate" ||
    job === "generate_digest" ||
    job === "select_candidates" ||
    job === "validate_digest_inputs"
  ) {
    return `${base} ${candidateLimit}`;
  }
  return base;
}

function buildReadSurfaceLabel() {
  const digestsSurface = adminState.readSurface.digests || "-";
  const runsSurface = adminState.readSurface.pipelineRuns || "-";
  return `digests=${digestsSurface} runs=${runsSurface}`;
}

function inferLatestDigestDate() {
  return extractRunDate(adminState.pipelineRuns[0] || {}) || adminState.digests[0]?.digest_date || "";
}

function extractRunDate(run) {
  const stats = DigestShared.normalizeStats(run?.stats);
  return String(run?.digest_date || stats.digest_date || "").trim();
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}
