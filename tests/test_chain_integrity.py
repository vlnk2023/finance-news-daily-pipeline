from scripts.assert_chain_integrity import evaluate_chain_integrity


CHAIN = [
    "collect",
    "audit_source_health",
    "build_clusters",
    "select_candidates",
    "translate",
    "validate_digest_inputs",
    "generate_digest",
]


def run_row(
    job_type: str,
    *,
    status: str = "success",
    digest_date: str = "2026-05-08",
    mode: str = "",
) -> dict[str, object]:
    stats: dict[str, object] = {"digest_date": digest_date}
    if mode:
        stats["digest_mode"] = mode
        stats["validation_mode"] = mode
    return {
        "job_type": job_type,
        "status": status,
        "started_at": "2026-05-08T12:00:00+00:00",
        "finished_at": "2026-05-08T12:01:00+00:00",
        "error": None,
        "stats": stats,
        "digest_date": digest_date,
    }


def test_evaluate_chain_integrity_success() -> None:
    rows = [run_row(job, mode="normal") for job in CHAIN]
    report = evaluate_chain_integrity(
        rows,
        digest_date="2026-05-08",
        chain_jobs=CHAIN,
        required_validation_mode="normal",
    )
    assert report.ok is True
    assert report.missing_jobs == []
    assert report.failed_jobs == []
    assert report.mode_mismatches == []


def test_evaluate_chain_integrity_missing_job() -> None:
    rows = [run_row(job, mode="normal") for job in CHAIN if job != "translate"]
    report = evaluate_chain_integrity(
        rows,
        digest_date="2026-05-08",
        chain_jobs=CHAIN,
        required_validation_mode="normal",
    )
    assert report.ok is False
    assert "translate" in report.missing_jobs


def test_evaluate_chain_integrity_failed_job() -> None:
    rows = [run_row(job, mode="normal") for job in CHAIN]
    rows = [dict(row) for row in rows]
    rows[0]["status"] = "failed"
    report = evaluate_chain_integrity(
        rows,
        digest_date="2026-05-08",
        chain_jobs=CHAIN,
        required_validation_mode="normal",
    )
    assert report.ok is False
    assert "collect" in report.failed_jobs


def test_evaluate_chain_integrity_mode_mismatch() -> None:
    rows = [
        run_row("validate_digest_inputs", mode="degraded"),
        run_row("generate_digest", mode="degraded"),
    ]
    rows += [run_row(job, mode="normal") for job in CHAIN]
    report = evaluate_chain_integrity(
        rows,
        digest_date="2026-05-08",
        chain_jobs=CHAIN,
        required_validation_mode="normal",
    )
    assert report.ok is False
    assert any("mode mismatch" in message for message in report.mode_mismatches)
