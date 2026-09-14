from pathlib import Path

from eventflow.platform import MobilityPlatform
from eventflow.universal import UniversalPlanner


ROOT = Path(__file__).resolve().parents[1]


def planner() -> UniversalPlanner:
    return UniversalPlanner(ROOT, MobilityPlatform(ROOT))


def test_exact_shakira_london_brief_is_understood() -> None:
    parsed = planner().parse_brief("Give me projections for a Shakira concert in London June 8th 2027")
    assert parsed["title"] == "Shakira concert"
    assert parsed["city_query"] == "London"
    assert parsed["date"] == "2027-06-08"
    assert parsed["event_type"] == "stadium_concert"


def test_london_brief_generates_complete_offline_plan() -> None:
    payload = planner().plan_from_brief("Give me projections for a Shakira concert in London June 8th 2027", online=False)
    assert payload["schema_version"] == "3.0"
    assert payload["venue"]["name"] == "Wembley Stadium"
    assert payload["event"]["attendance"] == 74500
    assert payload["currency"]["code"] == "GBP"
    assert len(payload["plans"]) == 3
    assert len(payload["plans"][1]["routes"]) == len(payload["zones"]) == 8
    assert payload["brief"]["assumptions"]
    assert payload["plans"][1]["metrics"]["max_pressure"] < payload["baseline"]["max_pressure"]


def test_explicit_venue_attendance_and_time_override_defaults() -> None:
    payload = planner().plan_from_brief(
        "Concert at Wembley Stadium in London June 8th 2027 attendance 50000 8pm", online=False
    )
    assert payload["event"]["attendance"] == 50000
    assert payload["event"]["start_time"] == "20:00"
    assert payload["brief"]["assumptions"][1]["confidence"] == "high"


def test_global_seed_city_uses_local_currency() -> None:
    payload = planner().plan_from_brief("Football final in Paris July 18th 2028", online=False)
    assert payload["venue"]["city"] == "Paris"
    assert payload["currency"]["code"] == "EUR"
    assert all(plan["cost"]["mid"] > 0 for plan in payload["plans"])
