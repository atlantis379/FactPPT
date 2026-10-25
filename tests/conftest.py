"""Shared test setup: tests never write the real job-stats index (data/job_stats.sqlite), which is the baseline for
generation time and token use."""
import pytest


@pytest.fixture(autouse=True)
def _job_stats_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTDECK_JOB_STATS_DB", str(tmp_path / "job_stats.sqlite"))
