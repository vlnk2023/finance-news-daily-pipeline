const state = {
  digests: [],
  pipelineRuns: [],
  digestRuns: [],
  selectedDate: null,
  selectedDigestRunId: null,
};
const CHAIN_JOBS = ["collect", "build_clusters", "select_candidates", "translate", "generate_digest"];

const statusEl = document.getElementById("status");
const digestEl = document.getElementById("digest");
const digestListEl = document.getElementById("digestList");
const refreshButton = document.getElementById("refreshButton");
const digestMetaEl = document.getElementById("digestMeta");
const pipelineRunListEl = document.getElementById("pipelineRunList");
const digestRunListEl = document.getElementById("digestRunList");

refreshButton.addEventListener("click", () => loadDigests());

loadDigests();

async function loadDigests() {
  setStatus("加载中...");
  digestEl.innerHTML = "";

  try {
    const config = window.FINANCE_DIGEST_CONFIG || {};
    if (!config.supabaseUrl || !config.supabaseAnonKey) {
      throw new Error("Missing Supabase config. Create web/config.js from config.example.js.");
    }

    const [digests, runs, digestRuns] = await Promise.all([
      fetchDigests(config),
      fetchPipelineRuns(config),
      fetchDigestRuns(config),
    ]);
    state.digests = digests;
    state.pipelineRuns = runs;
    state.digestRuns = digestRuns;
    state.selectedDate = state.selectedDate || state.digests[0]?.digest_date || null;
    syncSelectedDigestRun();
    renderDigestList();
    renderPipelineRuns();
    renderDigestRuns();
    renderSelectedDigest();
  } catch (error) {
    setStatus(error.message, true);
  }
}

function renderDigestList() {
  digestListEl.innerHTML = "";
  if (!state.digests.length) {
    digestListEl.textContent = "暂无日报";
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
      state.selectedDigestRunId = null;
      syncSelectedDigestRun();
      renderDigestList();
      renderDigestRuns();
      renderSelectedDigest();
    });
    digestListEl.appendChild(link);
  }
}

function renderSelectedDigest() {
  const digest = state.digests.find((item) => item.digest_date === state.selectedDate);
  const digestRun = getSelectedDigestRun();
  const view = digestRun || digest;
  if (!view) {
    setStatus("暂无日报");
    return;
  }

  setStatus(`生成时间：${formatDateTime(view.generated_at)}`);
  digestEl.innerHTML = markdownToHtml(view.markdown || "");
  renderDigestMeta(view);
}

function renderDigestRuns() {
  if (!digestRunListEl) {
    return;
  }
  digestRunListEl.innerHTML = "";
  const selectedDate = state.selectedDate;
  const runs = state.digestRuns.filter((item) => item.digest_date === selectedDate);
  if (!runs.length) {
    digestRunListEl.textContent = "当日暂无版本记录";
    return;
  }

  for (const run of runs) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `digest-run-item${run.id === state.selectedDigestRunId ? " active" : ""}`;
    const model = run.model || "-";
    const hash = String(run.markdown_hash || "").slice(0, 8) || "-";
    button.innerHTML = `
      <div class="digest-run-time">${escapeHtml(formatDateTime(run.generated_at))}</div>
      <div class="digest-run-meta">model=${escapeHtml(model)} · hash=${escapeHtml(hash)}</div>
    `;
    button.addEventListener("click", () => {
      state.selectedDigestRunId = run.id;
      renderDigestRuns();
      renderSelectedDigest();
    });
    digestRunListEl.appendChild(button);
  }
}

function renderPipelineRuns() {
  if (!pipelineRunListEl) {
    return;
  }
  pipelineRunListEl.innerHTML = "";
  if (!state.pipelineRuns.length) {
    pipelineRunListEl.textContent = "暂无运行记录";
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
    const extra = [
      `date=${digestDate}`,
      `耗时=${formatDurationMs(elapsedMs)}`,
      `候选=${formatMaybeNumber(candidateCount)}`,
      `覆盖=${formatPercent(coverage)}`,
    ].join(" · ");
    const rerunHint = status === "failed" ? buildRerunHint(run, stats) : "";
    item.innerHTML = `
      <div class="run-item-head">
        <span class="run-item-title">${escapeHtml(String(run.job_type || "unknown"))}</span>
        <span class="run-badge ${status}">${status === "success" ? "OK" : "FAIL"}</span>
      </div>
      <div class="run-item-meta">
        ${escapeHtml(formatDateTime(run.started_at))}
      </div>
      <div class="run-item-extra">
        ${escapeHtml(extra)}
      </div>
      ${run.error ? `<div class="run-item-error">${escapeHtml(String(run.error).slice(0, 120))}</div>` : ""}
      ${rerunHint ? `<div class="run-item-hint">${escapeHtml(rerunHint)}</div>` : ""}
    `;
    pipelineRunListEl.appendChild(item);
  }
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function markdownToHtml(markdown) {
  const lines = markdown.split("\n");
  const html = [];
  let inList = false;

  for (const line of lines) {
    if (line.startsWith("# ")) {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
      html.push(`<h1>${inlineMarkdown(line.slice(2))}</h1>`);
    } else if (line.startsWith("## ")) {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
      html.push(`<h2>${inlineMarkdown(line.slice(3))}</h2>`);
    } else if (line.startsWith("- ")) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${inlineMarkdown(line.slice(2))}</li>`);
    } else if (line.trim()) {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
      html.push(`<p>${inlineMarkdown(line)}</p>`);
    }
  }

  if (inList) {
    html.push("</ul>");
  }
  return html.join("\n");
}

function inlineMarkdown(text) {
  return escapeHtml(text).replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
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
  const url = new URL(`${config.supabaseUrl}/rest/v1/daily_digests`);
  url.searchParams.set("select", "digest_date,title,markdown,generated_at,model,json_summary");
  url.searchParams.set("order", "digest_date.desc");
  url.searchParams.set("limit", "30");
  const response = await fetch(url, {
    headers: {
      apikey: config.supabaseAnonKey,
      authorization: `Bearer ${config.supabaseAnonKey}`,
    },
  });
  if (!response.ok) {
    throw new Error(`Supabase digest request failed: ${response.status}`);
  }
  return response.json();
}

async function fetchPipelineRuns(config) {
  const url = new URL(`${config.supabaseUrl}/rest/v1/pipeline_runs`);
  url.searchParams.set(
    "select",
    "job_type,status,started_at,finished_at,stats,error,digest_date:stats->>digest_date"
  );
  url.searchParams.set("order", "started_at.desc");
  url.searchParams.set("limit", "20");
  const response = await fetch(url, {
    headers: {
      apikey: config.supabaseAnonKey,
      authorization: `Bearer ${config.supabaseAnonKey}`,
    },
  });
  if (!response.ok) {
    return [];
  }
  return response.json();
}

async function fetchDigestRuns(config) {
  const url = new URL(`${config.supabaseUrl}/rest/v1/daily_digest_runs`);
  url.searchParams.set(
    "select",
    "id,digest_date,title,markdown,json_summary,model,generated_at,markdown_hash,pipeline_run_id"
  );
  url.searchParams.set("order", "generated_at.desc");
  url.searchParams.set("limit", "120");
  const response = await fetch(url, {
    headers: {
      apikey: config.supabaseAnonKey,
      authorization: `Bearer ${config.supabaseAnonKey}`,
    },
  });
  if (!response.ok) {
    return [];
  }
  return response.json();
}

function syncSelectedDigestRun() {
  const selectedDate = state.selectedDate;
  if (!selectedDate) {
    state.selectedDigestRunId = null;
    return;
  }
  const runs = state.digestRuns.filter((item) => item.digest_date === selectedDate);
  if (!runs.length) {
    state.selectedDigestRunId = null;
    return;
  }
  const hasCurrent = runs.some((item) => item.id === state.selectedDigestRunId);
  if (!hasCurrent) {
    state.selectedDigestRunId = runs[0].id;
  }
}

function getSelectedDigestRun() {
  if (!state.selectedDigestRunId) {
    return null;
  }
  return state.digestRuns.find((item) => item.id === state.selectedDigestRunId) || null;
}

function renderDigestMeta(digest) {
  if (!digestMetaEl) {
    return;
  }
  const summary = digest?.json_summary || {};
  const candidateMode = summary.candidate_mode === true;
  const coverage = summary.candidate_translated_coverage;
  const fallbackReason = summary.candidate_fallback_reason || "";
  const topClusters = Array.isArray(summary.top_clusters) ? summary.top_clusters : [];
  const model = digest?.model || "-";

  const rows = [
    ["模型", model, ""],
    ["候选模式", candidateMode ? "已启用" : "未启用", candidateMode ? "ok" : ""],
    ["候选数", summary.candidate_count ?? "-", ""],
    ["候选覆盖率", formatPercent(coverage), coverage >= 0.7 ? "ok" : "warn"],
    ["新闻总量", summary.item_count ?? "-", ""],
    ["回退原因", fallbackReason || "无", fallbackReason ? "warn" : ""],
  ];

  digestMetaEl.innerHTML = rows
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

  if (topClusters.length) {
    const items = topClusters
      .slice(0, 8)
      .map((item) => {
        const rank = item.rank ?? "-";
        const score = item.importance_score ?? "-";
        const sourceCount = item.source_count ?? "-";
        return `<li>#${escapeHtml(String(rank))} score=${escapeHtml(String(score))} src=${escapeHtml(String(sourceCount))}</li>`;
      })
      .join("");
    digestMetaEl.innerHTML += `
      <div class="cluster-list">
        <h3>Top Clusters</h3>
        <ul>${items}</ul>
      </div>
    `;
  }
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
  const stats = run?.stats || {};
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

function buildRunSummaryHtml(runs) {
  const failedCount = runs.filter((run) => String(run.status || "").toLowerCase() !== "success").length;
  const lastChainSuccess = findLastChainSuccess(runs);
  const chainValue = lastChainSuccess ? `${lastChainSuccess}（全链路）` : "暂无";
  const healthClass = failedCount === 0 ? "ok" : "warn";
  return `
    <div class="run-summary-row">
      <span class="run-summary-label">最近全链路成功</span>
      <span class="run-summary-value">${escapeHtml(chainValue)}</span>
    </div>
    <div class="run-summary-row">
      <span class="run-summary-label">最近20次失败数</span>
      <span class="run-summary-value ${healthClass}">${escapeHtml(String(failedCount))}</span>
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

function buildRerunHint(run, stats) {
  const digestDate = stats.digest_date ? `date=${stats.digest_date}` : "date=<YYYY-MM-DD>";
  const candidateLimit = typeof stats.candidate_count === "number" && stats.candidate_count > 0
    ? `candidate_limit=${stats.candidate_count}`
    : "candidate_limit=40";
  const base = `workflow_dispatch: ${digestDate}`;
  const job = String(run.job_type || "");
  if (job === "translate" || job === "generate_digest" || job === "select_candidates") {
    return `${base} ${candidateLimit}`;
  }
  return base;
}
