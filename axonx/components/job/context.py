"""State owned by one Pipeline Job invocation."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .base import JobResponse


class RuntimeContext(dict[str, Any]):
    """Combine defaults, caller arguments, and system data for Job Steps."""

    def __init__(
        self,
        defaults: Mapping[str, Any],
        arguments: Mapping[str, Any],
        system: Mapping[str, Any],
    ) -> None:
        super().__init__(deepcopy(dict(defaults)))
        self.update(arguments)
        self.update(system)
        self.response = JobResponse()
