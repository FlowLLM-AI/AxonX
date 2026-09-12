"""Execution modes supported by jobs."""

from enum import StrEnum


class JobMode(StrEnum):
    """Describe how an application manages a job."""

    ON_DEMAND = "on_demand"
    BACKGROUND = "background"
    HTTP_ROUTE = "http_route"
