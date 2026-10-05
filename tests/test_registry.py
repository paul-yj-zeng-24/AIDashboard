"""The tool registry: schemas the model sees, argument checks, the tier gate."""
from app.tools import registry
from app.tools.registry import Tier, tool


def test_schemas_describe_each_tool():
    by_name = {s["function"]["name"]: s["function"] for s in registry.schemas()}
    assert {"get_current_time", "get_weather"} <= by_name.keys()

    weather = by_name["get_weather"]
    assert weather["description"].startswith("Current weather")
    props = weather["parameters"]["properties"]
    # Optional `str | None` is simplified to a plain string, no anyOf/title noise.
    assert props["place"] == {"type": "string", "description": props["place"]["description"]}
    assert props["days"]["minimum"] == 1 and props["days"]["maximum"] == 7
    assert "required" not in weather["parameters"]  # every argument is optional


def test_bad_arguments_come_back_as_text():
    result = registry.run("get_weather", '{"days": 30}')
    assert not result.ok
    assert "invalid arguments" in result.text and "days" in result.text


def test_misspelled_argument_is_rejected_not_ignored():
    result = registry.run("get_weather", '{"city": "Shanghai"}')
    assert not result.ok and "city" in result.text


def test_tier_is_required():
    import pytest
    with pytest.raises(TypeError):
        @tool  # forgot the parentheses and the tier
        def oops() -> str:
            return ""


def test_handoff_tier_is_never_run():
    @tool(tier=Tier.HANDOFF)
    def book_ride(destination: str) -> str:
        """Book a ride."""
        raise AssertionError("must not run")

    try:
        result = registry.run("book_ride", '{"destination": "SFO"}')
        assert not result.ok and "never runs it" in result.text
    finally:
        registry.TOOLS.pop("book_ride")


def test_unknown_tool():
    result = registry.run("launch_rocket", "{}")
    assert not result.ok and "no tool called" in result.text


def test_tool_runs_and_returns_text():
    result = registry.run("get_current_time", '{"timezone": "Asia/Shanghai"}')
    assert result.ok and "CST" in result.text


def test_tool_crash_is_caught():
    result = registry.run("get_current_time", '{"timezone": "Not/AZone"}')
    assert not result.ok and "Error while running" in result.text


def test_propose_tier_is_refused():
    calls = []

    @tool(tier=Tier.PROPOSE)
    def create_event(title: str) -> str:
        """Create a calendar event."""
        calls.append(title)
        return "created"

    try:
        result = registry.run("create_event", '{"title": "Gym"}')
        assert not result.ok and "approval" in result.text
        assert calls == []  # the function never ran
    finally:
        registry.TOOLS.pop("create_event")
