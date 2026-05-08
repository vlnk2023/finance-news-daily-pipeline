const state = {
  digests: [],
  pipelineRuns: [],
  pipelineRunsError: "",
  selectedDate: null,
  sourceHealthFilter: "all",
  sourceHealthSort: "age_desc",
  readSurface: {
    digests: "",
    pipelineRuns: "",
  },
};

const CHAIN_JOBS = [
  "collect",
  "audit_source_health",
  "build_clusters",
  "select_candidates",
  "translate",
  "validate_digest_inputs",
  "generate_digest",
];

const statusEl = document.getElementById("status");
const digestEl = document.getElementById("digest");
const digestListEl = document.getElementById("digestList");
const refreshButton = document.getElementById("refreshButton");
const digestMetaQualityEl = document.getElementById("digestMetaQuality");
const digestMetaDeliveryEl = document.getElementById("digestMetaDelivery");
const digestTitleEl = document.getElementById("digestTitle");
const generatedAtEl = document.getElementById("generatedAt");
const validationModeBadgeEl = document.getElementById("validationModeBadge");
const clusterPanelEl = document.getElementById("clusterPanel");
const clusterListEl = document.getElementById("clusterList");
const pipelineRunListEl = document.getElementById("pipelineRunList");
const sourceHealthListEl = document.getElementById("sourceHealthList");
const sourceHealthFilterEl = document.getElementById("sourceHealthFilter");
const sourceHealthSortEl = document.getElementById("sourceHealthSort");

refreshButton.addEventListener("click", () => loadDigests());
if (sourceHealthFilterEl) {
  sourceHealthFilterEl.addEventListener("change", () => {
    state.sourceHealthFilter = String(sourceHealthFilterEl.value || "all");
    renderSourceHealth();
  });
}
if (sourceHealthSortEl) {
  sourceHealthSortEl.addEventListener("change", () => {
    state.sourceHealthSort = String(sourceHealthSortEl.value || "age_desc");
    renderSourceHealth();
  });
}
loadDigests();

async function loadDigests() {
  setStatus("Loading...");
  digestEl.innerHTML = "";
  try {
    const config = window.FINANCE_DIGEST_CONFIG || {};
    if (!config.supabaseUrl || !config.supabaseAnonKey) {
      throw new Error("Missing Supabase config. Create web/config.js from config.example.js.");
    }

    const digestRead = await fetchDigests(config);
    state.digests = digestRead.rows;
    state.readSurface.digests = digestRead.relation;
    state.selectedDate = state.selectedDate || state.digests[0]?.digest_date || null;

    try {
      const runsRead = await fetchPipelineRuns(config);
      state.pipelineRuns = runsRead.rows;
      state.readSurface.pipelineRuns = runsRead.relation;
      state.pipelineRunsError = "";
    } catch (error) {
      state.pipelineRuns = [];
      state.readSurface.pipelineRuns = "";
      state.pipelineRunsError = String(error?.message || error || "Failed to load pipeline runs.");
    }

    renderDigestList();
    renderPipelineRuns();
    renderSourceHealth();
    renderSelectedDigest();
  } catch (error) {
    setStatus(error.message, true);
  }
}

function renderDigestList() {
  digestListEl.innerHTML = "";
  if (!state.digests.length) {
    digestListEl.textContent = "No digests yet.";
    return;
  }
  for (const digest of state.digests) {
    const link = document.createElement("a");
    link.href = "#";
    link.className = `digest-link${digest.digest_date === state.selectedDate ? " active" : ""}`;
    link.innerHTML = `${escapeHtml(digest.title)}<span>${escapeHtml(digest.digest_date)}</span>`;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      state.selectedDate = digest.digest_date;
      renderDigestList();
      renderSourceHealth();
      renderSelectedDigest();
    });
    digestListEl.appendChild(link);
  }
}

function renderSelectedDigest() {
  const digest = state.digests.find((item) => item.digest_date === state.selectedDate);
  if (!digest) {
    setStatus("No digest available.");
    setDigestHeader("Daily Digest", "");
    setValidationModeBadge("-");
    renderClusters([]);
    setMetricRows(digestMetaQualityEl, []);
    setMetricRows(digestMetaDeliveryEl, []);
    digestEl.innerHTML = "";
    return;
  }
  setStatus("Ready.");
  setDigestHeader(digest.title || "Daily Digest", digest.generated_at || "");
  digestEl.innerHTML = markdownToHtml(digest.markdown || "");
  renderDigestMeta(digest);
}

function renderPipelineRuns() {
  if (!pipelineRunListEl) {
    return;
  }
  pipelineRunListEl.innerHTML = "";
  if (state.pipelineRunsError) {
    const error = document.createElement("div");
    error.className = "run-item-error";
    error.textContent = `Failed to load run history: ${state.pipelineRunsError}`;
    pipelineRunListEl.appendChild(error);
    return;
  }
  if (!state.pipelineRuns.length) {
    pipelineRunListEl.textContent = "No pipeline runs yet.";
    return;
  }

  const summaryEl = document.createElement("div");
  summaryEl.className = "run-summary";
  summaryEl.innerHTML = buildRunSummaryHtml(state.pipelineRuns);
  pipelineRunListEl.appendChild(summaryEl);

  for (const run of state.pipelineRuns) {
    const item = document.createElement("div");
    item.className = "run-item";
    const status = String(run.status || "").toLowerCase() === "success" ? "success" : "failed";
    const elapsedMs = extractElapsedMs(run);
    const stats = normalizeStats(run.stats);
    const digestDate = stats.digest_date || "-";
    const coverage = firstNumeric(stats.candidate_coverage, stats.candidate_translated_coverage);
    const candidateCount = firstNumeric(stats.candidate_count, stats.fetched);
    const digestMode = String(stats.digest_mode || stats.validation_mode || "").trim();
    const healthCounts = formatSourceHealthCounts(stats.source_health_counts);
    const extraParts = [
      `date=${digestDate}`,
      `duration=${formatDurationMs(elapsedMs)}`,
      `candidates=${formatMaybeNumber(candidateCount)}`,
      `coverage=${formatPercent(coverage)}`,
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
        <span class="run-item-title">${escapeHtml(String(run.job_type || "unknown"))}</span>
        <span class="run-badge ${status}">${status === "success" ? "OK" : "FAIL"}</span>
      </div>
      <div class="run-item-meta">${escapeHtml(formatDateTime(run.started_at))}</div>
      <div class="run-item-extra">${escapeHtml(extraParts.join(" | "))}</div>
      ${run.error ? `<div class="run-item-error">${escapeHtml(String(run.error).slice(0, 180))}</div>` : ""}
      ${rerunHint ? `<div class="run-item-hint">${escapeHtml(rerunHint)}</div>` : ""}
    `;
    pipelineRunListEl.appendChild(item);
  }
}

function renderSourceHealth() {
  if (!sourceHealthListEl) {
    return;
  }
  sourceHealthListEl.innerHTML = "";
  if (state.pipelineRunsError) {
    sourceHealthListEl.textContent = "Cannot load source health while run history failed.";
    return;
  }
  const auditRun = findLatestRunForJobAndDate("audit_source_health", state.selectedDate);
  const auditStats = normalizeStats(auditRun?.stats);
  const rows = Array.isArray(auditStats.source_health) ? auditStats.source_health : [];
  if (!rows.length) {
    sourceHealthListEl.textContent = "No source health data for this date.";
    return;
  }
  const filtered = rows.filter((row) => {
    const status = String(row.status || "unknown");
    return state.sourceHealthFilter === "all" || state.sourceHealthFilter === status;
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
    const latest = row.latest_published_at ? formatDateTime(row.latest_published_at) : "-";
    const card = document.createElement("div");
    card.className = "source-health-item";
    card.innerHTML = `
      <div class="source-health-head">
        <span class="source-health-feed">${escapeHtml(feed)}</span>
        <span class="source-health-status ${escapeHtml(status)}">${escapeHtml(status)}</span>
      </div>
      <div class="source-health-meta">cadence=${escapeHtml(cadence)} | age=${escapeHtml(ageHours)}</div>
      <div class="source-health-meta">items=${escapeHtml(String(itemCount))} | latest=${escapeHtml(latest)}</div>
    `;
    sourceHealthListEl.appendChild(card);
  }
}

function compareSourceHealthRows(a, b) {
  const feedA = String(a.feed_id || a.source_id || "");
  const feedB = String(b.feed_id || b.source_id || "");
  const ageA = typeof a.age_hours === "number" ? a.age_hours : Number.POSITIVE_INFINITY;
  const ageB = typeof b.age_hours === "number" ? b.age_hours : Number.POSITIVE_INFINITY;
  if (state.sourceHealthSort === "age_asc") {
    return ageA - ageB || feedA.localeCompare(feedB);
  }
  if (state.sourceHealthSort === "feed_asc") {
    return feedA.localeCompare(feedB);
  }
  if (state.sourceHealthSort === "status") {
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

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function markdownToHtml(markdown) {
  const lines = String(markdown || "").split("\n");
  const html = [];
  let listType = "";
  let inCodeBlock = false;
  const codeLines = [];

  const closeList = () => {
    if (listType === "ul") {
      html.push("</ul>");
    } else if (listType === "ol") {
      html.push("</ol>");
    }
    listType = "";
  };

  const closeCodeBlock = () => {
    if (!inCodeBlock) {
      return;
    }
    html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
    codeLines.length = 0;
    inCodeBlock = false;
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) {
      if (inCodeBlock) {
        closeCodeBlock();
      } else {
        closeList();
        inCodeBlock = true;
      }
      continue;
    }
    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      closeList();
      const level = headingMatch[1].length;
      html.push(`<h${level}>${inlineMarkdown(headingMatch[2])}</h${level}>`);
      continue;
    }

    const quoteMatch = trimmed.match(/^>\s+(.+)$/);
    if (quoteMatch) {
      closeList();
      html.push(`<blockquote>${inlineMarkdown(quoteMatch[1])}</blockquote>`);
      continue;
    }

    const ulMatch = trimmed.match(/^[-*+]\s+(.+)$/);
    if (ulMatch) {
      if (listType !== "ul") {
        closeList();
        html.push("<ul>");
        listType = "ul";
      }
      html.push(`<li>${inlineMarkdown(ulMatch[1])}</li>`);
      continue;
    }

    const olMatch = trimmed.match(/^\d+\.\s+(.+)$/);
    if (olMatch) {
      if (listType !== "ol") {
        closeList();
        html.push("<ol>");
        listType = "ol";
      }
      html.push(`<li>${inlineMarkdown(olMatch[1])}</li>`);
      continue;
    }

    if (!trimmed) {
      closeList();
      continue;
    }

    closeList();
    html.push(`<p>${inlineMarkdown(trimmed)}</p>`);
  }
  closeCodeBlock();
  closeList();
  return html.join("\n");
}

function inlineMarkdown(text) {
  let result = escapeHtml(text);
  result = result.replace(/`([^`]+)`/g, "<code>$1</code>");
  result = result.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  result = result.replace(/(^|[^\*])\*([^*]+)\*(?=[^\*]|$)/g, "$1<em>$2</em>");
  result = result.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  return result;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

async function fetchDigests(config) {
  const strictPublicViews = Boolean(config.strictPublicViews);
  return fetchSupabaseRowsWithFallback(
    config,
    strictPublicViews ? ["public_daily_digests"] : ["public_daily_digests", "daily_digests"],
    {
      select: "digest_date,title,markdown,generated_at,model,json_summary",
      order: "digest_date.desc",
      limit: "30",
    },
    "digest request"
  );
}

async function fetchPipelineRuns(config) {
  const strictPublicViews = Boolean(config.strictPublicViews);
  return fetchSupabaseRowsWithFallback(
    config,
    strictPublicViews ? ["public_pipeline_runs"] : ["public_pipeline_runs", "pipeline_runs"],
    {
      select: "job_type,status,started_at,finished_at,stats,error,digest_date:stats->>digest_date",
      order: "started_at.desc",
      limit: "40",
    },
    "pipeline runs request"
  );
}

async function fetchSupabaseRowsWithFallback(config, relationCandidates, params, requestLabel) {
  let lastStatus = 0;
  for (const relation of relationCandidates) {
    const url = new URL(`${config.supabaseUrl}/rest/v1/${relation}`);
    for (const [key, value] of Object.entries(params)) {
      url.searchParams.set(key, value);
    }
    const response = await fetch(url, {
      headers: {
        apikey: config.supabaseAnonKey,
        authorization: `Bearer ${config.supabaseAnonKey}`,
      },
    });
    if (response.ok) {
      return { relation, rows: await response.json() };
    }
    lastStatus = response.status;
    if (response.status !== 404) {
      const text = await response.text();
      throw new Error(`Supabase ${requestLabel} failed on ${relation}: ${response.status} ${text.slice(0, 120)}`);
    }
  }
  throw new Error(`Supabase ${requestLabel} failed: no readable relation (${lastStatus || "unknown"})`);
}

function renderDigestMeta(digest) {
  if (!digestMetaQualityEl || !digestMetaDeliveryEl) {
    return;
  }
  const summary = digest?.json_summary || {};
  const candidateMode = summary.candidate_mode === true;
  const coverage = summary.candidate_translated_coverage;
  const fallbackReason = summary.candidate_fallback_reason || "";
  const topClusters = Array.isArray(summary.top_clusters) ? summary.top_clusters : [];
  const model = digest?.model || "-";
  const digestRun = findLatestRunForJobAndDate("generate_digest", digest?.digest_date || "");
  const digestRunStats = normalizeStats(digestRun?.stats);
  const validationMode = String(digestRunStats.validation_mode || digestRunStats.digest_mode || "-");
  const validationReason = String(digestRunStats.validation_reason || fallbackReason || "");
  const qualityRows = [
    ["Candidate mode", candidateMode ? "enabled" : "disabled", candidateMode ? "ok" : ""],
    ["Candidate count", summary.candidate_count ?? "-", ""],
    ["Candidate coverage", formatPercent(coverage), coverage >= 0.7 ? "ok" : "warn"],
    ["Raw item count", summary.item_count ?? "-", ""],
  ];
  const deliveryRows = [
    ["Model", model, ""],
    ["Validation mode", validationMode, validationMode === "normal" ? "ok" : "warn"],
    ["API surface", buildReadSurfaceLabel(), ""],
    ["Fallback reason", validationReason || "-", validationReason ? "warn" : ""],
  ];
  setValidationModeBadge(validationMode || "-");
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
          <span class="meta-label">${escapeHtml(String(label))}</span>
          <span class="${clsName}">${escapeHtml(String(value))}</span>
        </div>
      `;
    })
    .join("");
}

function setDigestHeader(title, generatedAt) {
  if (digestTitleEl) {
    digestTitleEl.textContent = title || "Daily Digest";
  }
  if (generatedAtEl) {
    const display = generatedAt ? formatDateTime(generatedAt) : "-";
    generatedAtEl.textContent = `Generated at: ${display}`;
  }
}

function setValidationModeBadge(mode) {
  if (!validationModeBadgeEl) {
    return;
  }
  const normalized = String(mode || "").trim().toLowerCase() || "unknown";
  validationModeBadgeEl.textContent = `mode: ${normalized}`;
  validationModeBadgeEl.classList.remove("mode-normal", "mode-degraded", "mode-blocked");
  if (normalized === "normal") {
    validationModeBadgeEl.classList.add("mode-normal");
  } else if (normalized === "degraded") {
    validationModeBadgeEl.classList.add("mode-degraded");
  } else if (normalized === "blocked") {
    validationModeBadgeEl.classList.add("mode-blocked");
  }
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
      return `<li>#${escapeHtml(String(rank))} score=${escapeHtml(String(score))} src=${escapeHtml(String(sourceCount))}</li>`;
    })
    .join("");
}

function buildReadSurfaceLabel() {
  const digestsSurface = state.readSurface.digests || "-";
  const runsSurface = state.readSurface.pipelineRuns || "-";
  return `digests=${digestsSurface} runs=${runsSurface}`;
}

function formatPercent(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatMaybeNumber(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return String(value);
}

function extractElapsedMs(run) {
  const stats = normalizeStats(run?.stats);
  if (typeof stats.elapsed_ms === "number" && Number.isFinite(stats.elapsed_ms)) {
    return stats.elapsed_ms;
  }
  const start = Date.parse(run?.started_at || "");
  const end = Date.parse(run?.finished_at || "");
  if (!Number.isNaN(start) && !Number.isNaN(end) && end >= start) {
    return end - start;
  }
  return null;
}

function formatDurationMs(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return "-";
  }
  if (value < 1000) {
    return `${Math.round(value)}ms`;
  }
  const seconds = value / 1000;
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainSeconds = Math.round(seconds % 60);
  return `${minutes}m${remainSeconds}s`;
}

function normalizeStats(value) {
  if (!value) {
    return {};
  }
  if (typeof value === "object") {
    return value;
  }
  try {
    return JSON.parse(String(value));
  } catch {
    return {};
  }
}

function firstNumeric(...values) {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}

function formatSourceHealthCounts(value) {
  if (!value || typeof value !== "object") {
    return "";
  }
  const pairs = [
    ["healthy_active", "active"],
    ["healthy_quiet", "quiet"],
    ["stale", "stale"],
    ["no_data", "no_data"],
    ["unknown", "unknown"],
  ];
  const parts = [];
  for (const [key, label] of pairs) {
    const count = value[key];
    if (typeof count === "number" && count > 0) {
      parts.push(`${label}:${count}`);
    }
  }
  return parts.join(",");
}

function buildRunSummaryHtml(runs) {
  const failedCount = runs.filter((run) => String(run.status || "").toLowerCase() !== "success").length;
  const lastChainSuccess = findLastChainSuccess(runs);
  const chainValue = lastChainSuccess ? `${lastChainSuccess} (full chain)` : "none";
  const healthClass = failedCount === 0 ? "ok" : "warn";
  const latestValidateRun = findLatestRunByJob("validate_digest_inputs");
  const latestValidateStats = normalizeStats(latestValidateRun?.stats);
  const digestMode = String(latestValidateStats.digest_mode || "-");
  const latestAuditRun = findLatestRunByJob("audit_source_health");
  const latestAuditStats = normalizeStats(latestAuditRun?.stats);
  const sourceHealth = formatSourceHealthCounts(latestAuditStats.source_health_counts) || "-";
  return `
    <div class="run-summary-row">
      <span class="run-summary-label">Last full-chain success</span>
      <span class="run-summary-value">${escapeHtml(chainValue)}</span>
    </div>
    <div class="run-summary-row">
      <span class="run-summary-label">Failed runs in latest 40</span>
      <span class="run-summary-value ${healthClass}">${escapeHtml(String(failedCount))}</span>
    </div>
    <div class="run-summary-row">
      <span class="run-summary-label">Latest gate mode</span>
      <span class="run-summary-value ${digestMode === "normal" ? "ok" : "warn"}">${escapeHtml(digestMode)}</span>
    </div>
    <div class="run-summary-row">
      <span class="run-summary-label">Latest source health</span>
      <span class="run-summary-value">${escapeHtml(sourceHealth)}</span>
    </div>
  `;
}

function findLastChainSuccess(runs) {
  const bucket = new Map();
  for (const run of runs) {
    if (String(run.status || "").toLowerCase() !== "success") {
      continue;
    }
    const stats = normalizeStats(run.stats);
    const digestDate = String(run.digest_date || stats.digest_date || "").trim();
    const job = String(run.job_type || "").trim();
    if (!digestDate || !CHAIN_JOBS.includes(job)) {
      continue;
    }
    if (!bucket.has(digestDate)) {
      bucket.set(digestDate, new Set());
    }
    bucket.get(digestDate).add(job);
  }
  const chainDates = [...bucket.entries()]
    .filter(([, jobs]) => CHAIN_JOBS.every((job) => jobs.has(job)))
    .map(([digestDate]) => digestDate)
    .sort((a, b) => Date.parse(b) - Date.parse(a));
  return chainDates[0] || "";
}

function findLatestRunByJob(jobType) {
  return state.pipelineRuns.find((run) => String(run.job_type || "") === jobType) || null;
}

function findLatestRunForJobAndDate(jobType, digestDate) {
  if (!digestDate) {
    return null;
  }
  return (
    state.pipelineRuns.find((run) => {
      if (String(run.job_type || "") !== jobType) {
        return false;
      }
      const stats = normalizeStats(run.stats);
      const runDate = String(run.digest_date || stats.digest_date || "");
      return runDate === digestDate;
    }) || null
  );
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
