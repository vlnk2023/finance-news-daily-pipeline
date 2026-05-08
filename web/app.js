const state = {
  digests: [],
  pipelineRuns: [],
  pipelineRunsError: "",
  selectedDate: null,
  readSurface: {
    digests: "",
    pipelineRuns: "",
  },
};

const statusEl = document.getElementById("status");
const digestEl = document.getElementById("digest");
const digestListEl = document.getElementById("digestList");
const refreshButton = document.getElementById("refreshButton");
const digestTitleEl = document.getElementById("digestTitle");
const generatedAtEl = document.getElementById("generatedAt");
const validationModeBadgeEl = document.getElementById("validationModeBadge");

refreshButton.addEventListener("click", () => loadDigests());
loadDigests();

async function loadDigests() {
  setStatus("Loading...");
  digestEl.innerHTML = "";
  try {
    const config = DigestShared.getConfig();
    const digestRead = await DigestShared.fetchDigests(config);
    state.digests = digestRead.rows;
    state.readSurface.digests = digestRead.relation;
    state.selectedDate = state.selectedDate || state.digests[0]?.digest_date || null;

    try {
      const runsRead = await DigestShared.fetchPipelineRuns(config);
      state.pipelineRuns = runsRead.rows;
      state.readSurface.pipelineRuns = runsRead.relation;
      state.pipelineRunsError = "";
    } catch (error) {
      state.pipelineRuns = [];
      state.readSurface.pipelineRuns = "";
      state.pipelineRunsError = String(error?.message || error || "Failed to load pipeline runs.");
    }

    renderDigestList();
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
    link.innerHTML = `${DigestShared.escapeHtml(digest.title)}<span>${DigestShared.escapeHtml(digest.digest_date)}</span>`;
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
    setStatus("No digest available.");
    setDigestHeader("Daily Digest", "");
    setValidationModeBadge("-");
    digestEl.innerHTML = "";
    return;
  }
  setStatus(state.pipelineRunsError ? "Digest loaded. Run metadata unavailable." : "Ready.");
  setDigestHeader(digest.title || "Daily Digest", digest.generated_at || "");
  digestEl.innerHTML = DigestShared.markdownToHtml(digest.markdown || "");
  renderDigestMeta(digest);
}

function renderDigestMeta(digest) {
  const digestRun = DigestShared.findLatestRunForJobAndDate(
    state.pipelineRuns,
    "generate_digest",
    digest?.digest_date || ""
  );
  const digestRunStats = DigestShared.normalizeStats(digestRun?.stats);
  const validationMode = String(digestRunStats.validation_mode || digestRunStats.digest_mode || "-");
  setValidationModeBadge(validationMode || "-");
}

function setDigestHeader(title, generatedAt) {
  if (digestTitleEl) {
    digestTitleEl.textContent = title || "Daily Digest";
  }
  if (generatedAtEl) {
    const display = generatedAt ? DigestShared.formatDateTime(generatedAt) : "-";
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

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}
