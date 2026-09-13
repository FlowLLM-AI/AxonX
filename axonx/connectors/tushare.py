"""Minimal Tushare Pro connector with retry and pagination support."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:
    import pandas as pd

DEFAULT_BASE_URL = "http://api.waditu.com/dataapi"
IP_LIMIT_ERROR = "IP数量超限"
TRANSIENT_ERROR = "查询数据失败，请确认参数"


class TushareClient:
    """Query Tushare Pro endpoints with bounded transient-error retries."""

    def __init__(
        self,
        timeout: int | float = 600,
        session: requests.Session | None = None,
        transient_error_retries: int = 5,
        transient_error_retry_initial_seconds: float = 5.0,
        transient_error_retry_max_seconds: float = 300.0,
        logger: Any = None,
    ) -> None:
        if transient_error_retries < 0:
            raise ValueError("transient_error_retries must not be negative")
        if transient_error_retry_initial_seconds < 0:
            raise ValueError(
                "transient_error_retry_initial_seconds must not be negative"
            )
        if transient_error_retry_max_seconds <= 0:
            raise ValueError("transient_error_retry_max_seconds must be greater than 0")

        self.base_url = os.getenv("AXONX_TUSHARE_BASE_URL", DEFAULT_BASE_URL).rstrip(
            "/"
        )
        self.token = os.getenv("AXONX_TUSHARE_TOKEN", "")
        self.timeout = timeout
        self.session = session if session is not None else requests.Session()
        self.retries = transient_error_retries
        self.initial_delay = transient_error_retry_initial_seconds
        self.max_delay = transient_error_retry_max_seconds
        self.logger = logger

    def _wait(
        self,
        api_name: str,
        attempt: int,
        delay: float,
        error: object,
        limit: int | None = None,
    ) -> float:
        if self.logger is not None:
            retry = f"{attempt}/{limit}" if limit is not None else str(attempt)
            self.logger.warning(
                f"API retry api={api_name} retry={retry} wait_seconds={delay} error={error}"
            )
        time.sleep(delay)
        return min(delay * 2, self.max_delay)

    def _request(
        self, api_name: str, fields: str, params: dict[str, Any]
    ) -> tuple[pd.DataFrame, bool]:
        import pandas as pd

        params = {"ts_type_name": self.base_url, **params}
        retry = ip_retry = 0
        delay = ip_delay = min(self.initial_delay, self.max_delay)

        while True:
            try:
                response = self.session.post(
                    f"{self.base_url}/{api_name}",
                    json={
                        "api_name": api_name,
                        "token": self.token,
                        "params": params,
                        "fields": fields,
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()
            except (requests.Timeout, requests.ConnectionError) as exc:
                if retry >= self.retries:
                    raise
                retry += 1
                delay = self._wait(api_name, retry, delay, exc, self.retries)
                continue

            if result["code"] == 0:
                data = result["data"]
                return pd.DataFrame(data["items"], columns=data["fields"]), bool(
                    data.get("has_more")
                )

            message = str(result.get("msg", ""))
            if IP_LIMIT_ERROR in message:
                ip_retry += 1
                ip_delay = self._wait(api_name, ip_retry, ip_delay, message)
            elif TRANSIENT_ERROR in message and retry < self.retries:
                retry += 1
                delay = self._wait(api_name, retry, delay, message, self.retries)
            else:
                raise RuntimeError(message)

    def query(self, api_name: str, fields: str = "", **params: Any) -> pd.DataFrame:
        """Query an endpoint that must return a complete response."""
        frame, has_more = self._request(api_name, fields, params)
        if has_more:
            raise RuntimeError(
                "Tushare API returned has_more=True; query result is incomplete"
            )
        return frame

    def query_has_more(
        self,
        api_name: str,
        fields: str = "",
        limit: int = 20_000,
        overlap: float = 0.2,
        **params: Any,
    ) -> pd.DataFrame:
        """Fetch all pages and remove rows repeated by page overlap."""
        import pandas as pd

        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        if not 0 <= overlap < 1:
            raise ValueError("overlap must be in [0, 1)")

        frames: list[pd.DataFrame] = []
        offset = 0
        while True:
            frame, has_more = self._request(
                api_name, fields, {**params, "offset": offset, "limit": limit}
            )
            if frame.empty:
                break
            frames.append(frame)
            if not has_more:
                break
            offset += max(1, int(len(frame) * (1 - overlap)))

        if not frames:
            return pd.DataFrame()
        columns = list(
            dict.fromkeys(column for frame in frames for column in frame.columns)
        )
        frames = [frame.dropna(axis="columns", how="all") for frame in frames]
        return (
            pd.concat(frames, ignore_index=True)
            .reindex(columns=columns)
            .drop_duplicates(ignore_index=True)
        )
