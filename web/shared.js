const DigestShared = (() => {
  const CHAIN_JOBS = [
    "collect",
    "audit_source_health",
    "build_clusters",
    "select_candidates",
    "translate",
    "validate_digest_inputs",
    "generate_digest",
  ];

  function getConfig() {
    const config = window.FINANCE_DIGEST_CONFIG || {};
    if (!config.supabaseUrl || !config.supabaseAnonKey) {
      throw new Error("Missing Supabase config. Create web/config.js from config.example.js.");
    }
    return config;
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

  function findLatestRunByJob(runs, jobType) {
    return runs.find((run) => String(run.job_type || "") === jobType) || null;
  }

  function findLatestRunForJobAndDate(runs, jobType, digestDate) {
    if (!digestDate) {
      return null;
    }
    return (
      runs.find((run) => {
        if (String(run.job_type || "") !== jobType) {
          return false;
        }
        const stats = normalizeStats(run.stats);
        const runDate = String(run.digest_date || stats.digest_date || "");
        return runDate === digestDate;
      }) || null
    );
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

  return {
    CHAIN_JOBS,
    escapeHtml,
    extractElapsedMs,
    fetchDigests,
    fetchPipelineRuns,
    findLastChainSuccess,
    findLatestRunByJob,
    findLatestRunForJobAndDate,
    firstNumeric,
    formatDateTime,
    formatDurationMs,
    formatMaybeNumber,
    formatPercent,
    formatSourceHealthCounts,
    getConfig,
    markdownToHtml,
    normalizeStats,
  };
})();
