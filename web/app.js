const state = {
  digests: [],
  pipelineRuns: [],
  selectedDate: null,
};

const statusEl = document.getElementById("status");
const digestEl = document.getElementById("digest");
const digestListEl = document.getElementById("digestList");
const refreshButton = document.getElementById("refreshButton");
const digestMetaEl = document.getElementById("digestMeta");
const pipelineRunListEl = document.getElementById("pipelineRunList");

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

    const [digests, runs] = await Promise.all([
      fetchDigests(config),
      fetchPipelineRuns(config),
    ]);
    state.digests = digests;
    state.pipelineRuns = runs;
    state.selectedDate = state.selectedDate || state.digests[0]?.digest_date || null;
    renderDigestList();
    renderPipelineRuns();
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
      renderDigestList();
      renderSelectedDigest();
    });
    digestListEl.appendChild(link);
  }
}

function renderSelectedDigest() {
  const digest = state.digests.find((item) => item.digest_date === state.selectedDate);
  if (!digest) {
    setStatus("暂无日报");
    return;
  }

  setStatus(`生成时间：${formatDateTime(digest.generated_at)}`);
  digestEl.innerHTML = markdownToHtml(digest.markdown || "");
  renderDigestMeta(digest);
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
  for (const run of state.pipelineRuns) {
    const item = document.createElement("div");
    item.className = "run-item";
    const status = String(run.status || "").toLowerCase() === "success" ? "success" : "failed";
    const elapsedMs = extractElapsedMs(run);
    item.innerHTML = `
      <div class="run-item-head">
        <span class="run-item-title">${escapeHtml(String(run.job_type || "unknown"))}</span>
        <span class="run-badge ${status}">${status === "success" ? "OK" : "FAIL"}</span>
      </div>
      <div class="run-item-meta">
        ${escapeHtml(formatDateTime(run.started_at))} · ${escapeHtml(formatDurationMs(elapsedMs))}
      </div>
      ${run.error ? `<div class="run-item-error">${escapeHtml(String(run.error).slice(0, 120))}</div>` : ""}
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
  url.searchParams.set("select", "job_type,status,started_at,finished_at,stats,error");
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
