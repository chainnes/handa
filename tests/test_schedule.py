from datetime import date

from handa.engine.ops import backward_schedule


def test_prep_is_walked_backward_from_service():
    rows = backward_schedule(date(2026, 12, 4), "18:00", guests=40, has_lechon=False, max_lead_days=1)
    by_task = {row["task"]: row for row in rows}
    assert by_task["Prep starts"]["hours_before_service"] == 6
    assert by_task["Service"]["at"] == "2026-12-04T18:00"
    assert by_task["On site"]["at"] == "2026-12-04T17:00"
    assert by_task["Load the van"]["at"] == "2026-12-04T15:00"
    assert [row["at"] for row in rows] == sorted(row["at"] for row in rows)


def test_a_large_event_starts_prep_earlier():
    rows = backward_schedule(date(2026, 12, 4), "12:00", guests=120, has_lechon=True, max_lead_days=2)
    by_task = {row["task"]: row for row in rows}
    assert by_task["Prep starts"]["hours_before_service"] == 8
    assert "Confirm lechon delivery" in by_task
    assert by_task["Market order deadline"]["at"].startswith("2026-12-02")
