"""Trying providers of one kind in order, shared by the routing and geocoding chains."""

import logging
from collections.abc import Callable, Sequence
from typing import Protocol

from planner.infra.errors import UpstreamContractError, UpstreamTimeout, UpstreamUnavailable

logger = logging.getLogger(__name__)

# A provider that is down, too slow or answering nonsense is replaced by the next one.
# "Nothing found" is an answer, not a failure, and other rejections would be rejected again.
FALL_THROUGH = (UpstreamUnavailable, UpstreamTimeout, UpstreamContractError)


class Named(Protocol):
    @property
    def name(self) -> str: ...


def first_success[P: Named, R](providers: Sequence[P], ask: Callable[[P], R]) -> R:
    """Ask each provider in turn and return the first answer.

    Only the failures in ``FALL_THROUGH`` move on to the next provider; anything else is
    raised at once. If every provider fails, the last failure is raised.
    """
    failures: list[Exception] = []
    for provider in providers:
        try:
            return ask(provider)
        except FALL_THROUGH as error:
            logger.warning("provider %s failed (%s)", provider.name, type(error).__name__)
            failures.append(error)
    if not failures:
        msg = "no providers to ask"
        raise ValueError(msg)
    raise failures[-1]
