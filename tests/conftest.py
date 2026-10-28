"""Shared test setup: tests never write the real job-stats index (data/job_stats.sqlite), which is the baseline for
generation time and token use."""
import pytest


@pytest.fixture(autouse=True)
def _job_stats_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTDECK_JOB_STATS_DB", str(tmp_path / "job_stats.sqlite"))


@pytest.fixture(autouse=True)
def _strict_siblings(monkeypatch):
    """Accepting a task must never change the input of a parallel sibling (app.deckflow Store.check_siblings)."""
    monkeypatch.setenv("FACTDECK_STRICT_SIBLINGS", "1")
