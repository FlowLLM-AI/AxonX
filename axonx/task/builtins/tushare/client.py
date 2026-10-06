"""Tushare Pro client owned by the built-in download Task."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import requests

from ....constants import TUSHARE_TIMEOUT_SECONDS
from ...contracts.windows import DeadlineBudget

if TYPE_CHECKING:
    import pandas as pd

DEFAULT_BASE_URL = "http://api.waditu.com/dataapi"
IP_LIMIT_ERROR = "IP数量超限"
RATE_LIMIT_ERROR = "频率超限"
TRANSIENT_ERROR = "查询数据失败，请确认参数"


class TushareClient:
    """Query Tushare Pro endpoints with bounded retries and pagination."""

    def __init__(
        self,
        timeout: float = TUSHARE_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
        transient_error_retries: int = 5,
        transient_error_retry_initial_seconds: float = 5.0,
        transient_error_retry_max_seconds: float = 300.0,
        limit_error_retries: int = 12,
        sleep: Callable[[float], None] = time.sleep,
        retry_rate_limit_forever: bool = False,
        rate_limit_retry_seconds: float = 60.0,
        logger: Any = None,
    ) -> None:
        if transient_error_retries < 0:
            raise ValueError("transient_error_retries must not be negative")
        if transient_error_retry_initial_seconds < 0:
            raise ValueError("transient_error_retry_initial_seconds must not be negative")
        if transient_error_retry_max_seconds <= 0:
            raise ValueError("transient_error_retry_max_seconds must be greater than 0")
        if limit_error_retries < 0:
            raise ValueError("limit_error_retries must not be negative")
        if timeout <= 0:
            raise ValueError("timeout must be greater than 0")

        if rate_limit_retry_seconds < 0:
            raise ValueError("rate_limit_retry_seconds must not be negative")

        self.base_url = os.getenv("AXONX_TUSHARE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.token = os.getenv("AXONX_TUSHARE_TOKEN", "")
        self.timeout = timeout
        self.session = session if session is not None else requests.Session()
        self._owns_session = session is None
        self.retry_rate_limit_forever = retry_rate_limit_forever
        self.rate_limit_retry_seconds = rate_limit_retry_seconds
        self.retries = transient_error_retries
        self.initial_delay = transient_error_retry_initial_seconds
        self.max_delay = transient_error_retry_max_seconds
        self.limit_retries = limit_error_retries
        self.sleep = sleep
        self.logger = logger

    def _wait(
        self,
        api_name: str,
        attempt: int,
        delay: float,
        error: object,
        limit: int | None = None,
        budget: DeadlineBudget | None = None,
    ) -> float:
        if self.logger is not None:
            retry = f"{attempt}/{limit}" if limit is not None else str(attempt)
            self.logger.warning(f"API retry api={api_name} retry={retry} wait_seconds={delay} error={error}")
        if budget is None:
            self.sleep(delay)
        else:
            budget.sleep(delay)
            self._check_budget(budget)
        return min(delay * 2, self.max_delay)

    @staticmethod
    def _check_budget(budget: DeadlineBudget | None) -> None:
        if budget is not None and budget.remaining_seconds <= 0:
            raise TimeoutError("Tushare request deadline exceeded")

    def close(self) -> None:
        """Release the session created by this client."""
        if self._owns_session:
            self.session.close()

    def _request(
        self,
        api_name: str,
        fields: str,
        params: dict,
        budget: DeadlineBudget | None = None,
    ) -> tuple[pd.DataFrame, bool]:
        import pandas as pd

        params = {**params, "ts_type_name": self.base_url}
        retry = limit_retry = 0
        delay = limit_delay = min(self.initial_delay, self.max_delay)

        while True:
            self._check_budget(budget)
            try:
                response = self.session.post(
                    f"{self.base_url}/{api_name}",
                    json={
                        "api_name": api_name,
                        "token": self.token,
                        "params": params,
                        "fields": fields,
                    },
                    timeout=(min(self.timeout, budget.remaining_seconds) if budget is not None else self.timeout),
                )
                self._check_budget(budget)
                response.raise_for_status()
                result = response.json()
                self._check_budget(budget)
            except requests.RequestException as exc:
                if retry >= self.retries:
                    raise
                retry += 1
                delay = self._wait(api_name, retry, delay, exc, self.retries, budget)
                continue
            except ValueError as exc:
                raise RuntimeError("Tushare returned invalid JSON") from exc

            if not isinstance(result, dict) or "code" not in result:
                raise RuntimeError("Tushare returned an invalid response object")
            if result["code"] == 0:
                data = result.get("data")
                if not isinstance(data, dict):
                    raise RuntimeError("Tushare response did not contain data")
                response_fields = data.get("fields")
                items = data.get("items")
                if not isinstance(response_fields, list) or not isinstance(items, list):
                    raise RuntimeError("Tushare response contained invalid tabular data")
                frame = pd.DataFrame(items, columns=response_fields)
                self._check_budget(budget)
                return frame, bool(data.get("has_more"))

            message = str(result.get("msg", ""))
            if RATE_LIMIT_ERROR in message and self.retry_rate_limit_forever:
                limit_retry += 1
                self._wait(
                    api_name,
                    limit_retry,
                    self.rate_limit_retry_seconds,
                    message,
                    budget=budget,
                )
                continue
            if IP_LIMIT_ERROR in message or RATE_LIMIT_ERROR in message:
                if limit_retry >= self.limit_retries:
                    raise RuntimeError(f"Tushare limit retry budget exhausted after {limit_retry} attempts: {message}")
                limit_retry += 1
                wait = self.max_delay if RATE_LIMIT_ERROR in message else limit_delay
                limit_delay = self._wait(
                    api_name,
                    limit_retry,
                    wait,
                    message,
                    self.limit_retries,
                    budget,
                )
                continue
            if TRANSIENT_ERROR in message and retry < self.retries:
                retry += 1
                delay = self._wait(api_name, retry, delay, message, self.retries, budget)
                continue
            raise RuntimeError(message or f"Tushare request failed with code {result['code']}")

    def query(
        self,
        api_name: str,
        fields: str = "",
        *,
        budget: DeadlineBudget | None = None,
        **params,
    ) -> pd.DataFrame:
        """Query an endpoint that must return a complete response."""
        frame, has_more = self._request(api_name, fields, params, budget)
        if has_more:
            raise RuntimeError("Tushare API returned has_more=True; query result is incomplete")
        return frame

    def query_has_more(
        self,
        api_name: str,
        fields: str = "",
        limit: int = 20_000,
        overlap: float = 0.2,
        max_pages: int = 10_000,
        budget: DeadlineBudget | None = None,
        **params,
    ) -> pd.DataFrame:
        """Fetch all pages and remove rows repeated by page overlap."""
        import pandas as pd

        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        if not 0 <= overlap < 1:
            raise ValueError("overlap must be in [0, 1)")
        if max_pages <= 0:
            raise ValueError("max_pages must be greater than 0")

        frames: list[pd.DataFrame] = []
        previous = None
        offset = 0
        for _page in range(max_pages):
            frame, has_more = self._request(api_name, fields, {**params, "offset": offset, "limit": limit}, budget)
            if frame.empty:
                break
            if previous is not None and frame.equals(previous):
                raise RuntimeError("Tushare pagination made no progress")
            frames.append(frame)
            if not has_more:
                break
            previous = frame
            offset += max(1, int(len(frame) * (1 - overlap)))
        else:
            raise RuntimeError(f"Tushare pagination exceeded {max_pages} pages")

        if not frames:
            return pd.DataFrame()
        columns = list(dict.fromkeys(column for frame in frames for column in frame.columns))
        frames = [frame.dropna(axis="columns", how="all") for frame in frames]
        frame = pd.concat(frames, ignore_index=True).reindex(columns=columns).drop_duplicates(ignore_index=True)
        self._check_budget(budget)
        return frame
