from tests.test_eval import _result

from email_classifier.api.stats_build import build_stats, latency_histogram


def test_latency_histogram_edges() -> None:
    bins = latency_histogram([50, 150, 5000])
    by_lo = {b["lo"]: b["n"] for b in bins}
    assert by_lo[0] == 1
    assert by_lo[100] == 1
    assert by_lo[5000] == 1


def test_build_stats_projections() -> None:
    result = _result("m", cost_usd=0.0001)
    row = {
        "result_json": result.model_dump_json(),
        "classified_at": "2026-09-21T01:00:00+00:00",
        "label_ids": '["SPAM"]',
    }
    stats = build_stats([row], "hour")
    assert stats["n"] == 1
    assert stats["projected_cost_usd"]["emails_10000"] == 1.0
    assert stats["series"][0]["bucket"].startswith("2026-09-21T01")
