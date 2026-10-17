import pytest

from planner.infra.errors import (
    HostNotAllowed,
    UpstreamContractError,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnavailable,
    UpstreamWaitTimeout,
)


def test_upstream_error_names_the_provider_and_keeps_the_message() -> None:
    error = UpstreamError("osrm", "bad request")

    assert str(error) == "osrm: bad request"
    assert error.provider == "osrm"
    assert error.message == "bad request"


@pytest.mark.parametrize(
    "error_type", [UpstreamTimeout, UpstreamUnavailable, UpstreamContractError]
)
def test_specific_failures_are_upstream_errors(error_type: type[UpstreamError]) -> None:
    error = error_type("open-meteo", "details")

    assert isinstance(error, UpstreamError)
    assert error.provider == "open-meteo"


def test_the_specific_failures_are_distinct() -> None:
    assert not issubclass(UpstreamTimeout, UpstreamUnavailable)
    assert not issubclass(UpstreamUnavailable, UpstreamTimeout)
    assert not issubclass(UpstreamContractError, UpstreamUnavailable)


def test_a_disallowed_host_is_not_an_upstream_failure() -> None:
    assert issubclass(HostNotAllowed, ValueError)
    assert not issubclass(HostNotAllowed, UpstreamError)


def test_status_and_body_are_optional_and_kept_out_of_the_message() -> None:
    plain = UpstreamError("osrm", "HTTP 400")
    detailed = UpstreamError("osrm", "HTTP 400", status=400, body='{"code":"NoRoute"}')

    assert (plain.status, plain.body) == (None, None)
    assert (detailed.status, detailed.body) == (400, '{"code":"NoRoute"}')
    assert "NoRoute" not in str(detailed)


def test_waiting_too_long_locally_is_a_timeout() -> None:
    error = UpstreamWaitTimeout("osrm", "no slot")

    assert isinstance(error, UpstreamTimeout)
    assert not isinstance(UpstreamTimeout("osrm", "x"), UpstreamWaitTimeout)
