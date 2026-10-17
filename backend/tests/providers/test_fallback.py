import logging
from collections.abc import Callable

import pytest

from planner.infra.errors import (
    UpstreamContractError,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from planner.providers.fallback import first_success


class Named:
    def __init__(self, name: str) -> None:
        self.name = name


def ask_with(outcomes: dict[str, object]) -> tuple[Callable[[Named], str], list[str]]:
    calls: list[str] = []

    def ask(provider: Named) -> str:
        calls.append(provider.name)
        outcome = outcomes[provider.name]
        if isinstance(outcome, Exception):
            raise outcome
        return str(outcome)

    return ask, calls


def test_the_first_answer_wins_and_later_providers_are_not_asked() -> None:
    ask, calls = ask_with({"a": "from a", "b": "from b"})

    assert first_success([Named("a"), Named("b")], ask) == "from a"
    assert calls == ["a"]


@pytest.mark.parametrize(
    "failure",
    [
        UpstreamUnavailable("a", "down"),
        UpstreamTimeout("a", "slow"),
        UpstreamContractError("a", "garbage"),
    ],
)
def test_outages_and_garbage_move_on_to_the_next_provider(failure: Exception) -> None:
    ask, calls = ask_with({"a": failure, "b": "from b"})

    assert first_success([Named("a"), Named("b")], ask) == "from b"
    assert calls == ["a", "b"]


@pytest.mark.parametrize("error", [UpstreamError("a", "HTTP 400", status=400), KeyError("bug")])
def test_other_failures_are_raised_at_once(error: Exception) -> None:
    ask, calls = ask_with({"a": error, "b": "from b"})

    with pytest.raises(type(error)):
        first_success([Named("a"), Named("b")], ask)

    assert calls == ["a"]


def test_when_all_fail_the_last_failure_is_raised() -> None:
    ask, _ = ask_with({"a": UpstreamUnavailable("a", "down"), "b": UpstreamTimeout("b", "slow")})

    with pytest.raises(UpstreamTimeout, match="b: slow"):
        first_success([Named("a"), Named("b")], ask)


def test_no_providers_is_an_error() -> None:
    with pytest.raises(ValueError, match="no providers"):
        first_success([], lambda provider: "x")


def test_a_failure_is_logged_with_the_provider_name_and_type(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ask, _ = ask_with({"photon": UpstreamUnavailable("photon", "down"), "nominatim": "ok"})

    with caplog.at_level(logging.WARNING):
        first_success([Named("photon"), Named("nominatim")], ask)

    assert "photon failed (UpstreamUnavailable)" in caplog.text
