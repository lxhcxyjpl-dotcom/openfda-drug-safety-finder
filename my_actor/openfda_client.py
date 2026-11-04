"""Rate-limited client for the official openFDA JSON API.

Requests go to ``https://api.fda.gov`` only. The optional API key is sent as
the ``api_key`` query parameter and is never written into log messages.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .constants import (
    ENDPOINTS,
    MAX_ATTEMPTS,
    OPENFDA_BASE,
    PAGE_SIZE,
    RATE_SAFETY_FACTOR,
    REQUESTS_PER_MINUTE,
    SORT,
    USER_AGENT,
)

_API_KEY_PARAM = re.compile(r'(api_key=)[^&\s]+', re.IGNORECASE)
_PARSE_ERROR = re.compile(r'parse_exception', re.IGNORECASE)


class Logger(Protocol):
    """Subset of ``Actor.log`` used by the client."""

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None: ...

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None: ...

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None: ...


class _NullLogger:
    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        return None

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        return None

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        return None


class OpenFdaRequestError(RuntimeError):
    """openFDA failed or rejected the request."""


@dataclass(frozen=True)
class OpenFdaPage:
    """One page of openFDA results."""

    results: list[dict[str, Any]]
    total: int | None


class RateLimiter:
    """Space request starts so the long-run average stays under ``min_interval``."""

    def __init__(
        self,
        min_interval: float,
        *,
        sleep: Any = asyncio.sleep,
        monotonic: Any = time.monotonic,
    ) -> None:
        self._min_interval = min_interval
        self._sleep = sleep
        self._monotonic = monotonic
        self._next = 0.0
        self._lock = asyncio.Lock()

    @property
    def min_interval(self) -> float:
        return self._min_interval

    async def wait(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = self._monotonic()
            delay = self._next - now
            if delay > 0:
                await self._sleep(delay)
                now = self._monotonic()
            self._next = now + self._min_interval


def redact_secrets(text: str, api_key: str | None = None) -> str:
    """Remove an openFDA API key from text that might be logged or raised."""
    cleaned = _API_KEY_PARAM.sub(r'\1***', text)
    if api_key:
        cleaned = cleaned.replace(api_key, '***')
    return cleaned


def polite_interval() -> float:
    """Seconds between requests, just under the published 240/minute cap."""
    return RATE_SAFETY_FACTOR * (60.0 / REQUESTS_PER_MINUTE)


class OpenFdaClient:
    """GET JSON from the drug event, label, and enforcement endpoints."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        logger: Logger | None = None,
        http_client: httpx.AsyncClient | None = None,
        min_interval: float | None = None,
        sleep: Any = asyncio.sleep,
        monotonic: Any = time.monotonic,
        max_attempts: int = MAX_ATTEMPTS,
        page_size: int = PAGE_SIZE,
    ) -> None:
        self._api_key = api_key or None
        self._logger = logger or _NullLogger()
        self._sleep = sleep
        self._max_attempts = max_attempts
        self.page_size = page_size
        interval = polite_interval() if min_interval is None else min_interval
        self._limiter = RateLimiter(interval, sleep=sleep, monotonic=monotonic)
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'},
            follow_redirects=False,
        )

    @property
    def min_interval(self) -> float:
        return self._limiter.min_interval

    async def __aenter__(self) -> OpenFdaClient:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def fetch_page(self, *, mode: str, search: str, limit: int, skip: int) -> OpenFdaPage:
        """Return one page. An openFDA 404 (no matches) is an empty page."""
        cleaned = search.strip()
        if not cleaned:
            raise ValueError('openFDA search expression is empty.')
        if limit < 1:
            raise ValueError('limit must be at least 1.')
        if skip < 0:
            raise ValueError('skip must be 0 or greater.')
        endpoint = ENDPOINTS.get(mode)
        if endpoint is None:
            raise ValueError(f'Unknown openFDA mode {mode!r}.')
        params: dict[str, str] = {
            'search': cleaned,
            'limit': str(limit),
            'skip': str(skip),
        }
        sort = SORT.get(mode)
        if sort:
            params['sort'] = sort
        if self._api_key:
            params['api_key'] = self._api_key
        url = f'{OPENFDA_BASE}{endpoint}'
        payload = await self._get(url, params)
        if payload is None:
            self._logger.info(f'openFDA returned no matches for {_short(cleaned)}.')
            return OpenFdaPage(results=[], total=0)
        results = payload.get('results')
        if not isinstance(results, list):
            raise OpenFdaRequestError('openFDA returned an unexpected payload.')
        documents = [item for item in results if isinstance(item, dict)]
        total = _total(payload)
        self._logger.info(
            f'openFDA {mode} returned {len(documents)} records'
            + (f' of {total}' if total is not None else '')
            + f' for {_short(cleaned)}.'
        )
        return OpenFdaPage(results=documents, total=total)

    async def _get(self, url: str, params: dict[str, str]) -> Any | None:
        """Return parsed JSON, or None when openFDA reports no matches."""
        last_error = 'openFDA request failed.'
        for attempt in range(self._max_attempts):
            await self._limiter.wait()
            try:
                response = await self._http.get(url, params=params)
            except httpx.TransportError as exc:
                last_error = redact_secrets(
                    f'Network error talking to openFDA ({exc.__class__.__name__}).',
                    self._api_key,
                )
                if not await self._pause_for_retry(attempt, last_error, None):
                    break
                continue
            status = response.status_code
            body = response.text
            if status == 404 and _is_no_match(body):
                return None
            if status >= 400 and _PARSE_ERROR.search(body):
                raise OpenFdaRequestError(
                    'openFDA could not parse the search expression. '
                    'Check field names and quotes, or pass a plain drug name such as aspirin.'
                )
            if status == 429 or status >= 500:
                last_error = f'openFDA returned HTTP {status}.'
                if not await self._pause_for_retry(attempt, last_error, _retry_after(response)):
                    break
                continue
            if status >= 400:
                snippet = redact_secrets(_error_summary(body), self._api_key)
                raise OpenFdaRequestError(f'openFDA rejected the request (HTTP {status}): {snippet}')
            try:
                parsed = response.json()
            except json.JSONDecodeError:
                last_error = f'openFDA returned a non-JSON response (HTTP {status}).'
                if not await self._pause_for_retry(attempt, last_error, None):
                    break
                continue
            if not isinstance(parsed, dict):
                raise OpenFdaRequestError('openFDA returned an unexpected payload.')
            return parsed
        raise OpenFdaRequestError(f'{last_error} Gave up after {self._max_attempts} attempts.')

    async def _pause_for_retry(self, attempt: int, message: str, retry_after: float | None) -> bool:
        """Return False when this was the last attempt."""
        if attempt + 1 >= self._max_attempts:
            self._logger.warning(message)
            return False
        delay = _backoff(attempt, retry_after)
        self._logger.warning(f'{message} Retrying in {delay:.1f}s ({attempt + 1}/{self._max_attempts}).')
        await self._sleep(delay)
        return True


def _backoff(attempt: int, retry_after: float | None) -> float:
    delay = min(30.0, float(2**attempt))
    if retry_after is not None:
        delay = max(delay, retry_after)
    return min(60.0, delay)


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get('retry-after')
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def _is_no_match(body: str) -> bool:
    summary = _error_summary(body).lower()
    return 'not_found' in summary or 'no matches' in summary


def _error_summary(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return _snippet(body)
    error = payload.get('error') if isinstance(payload, dict) else None
    if isinstance(error, dict):
        code = error.get('code') if isinstance(error.get('code'), str) else ''
        message = error.get('message') if isinstance(error.get('message'), str) else ''
        text = f'{code}: {message}'.strip(': ')
        return _snippet(text or body)
    return _snippet(body)


def _total(payload: dict[str, Any]) -> int | None:
    meta = payload.get('meta')
    if not isinstance(meta, dict):
        return None
    results = meta.get('results')
    if not isinstance(results, dict):
        return None
    raw = results.get('total')
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def _snippet(text: str) -> str:
    compact = ' '.join(text.split())
    return compact[:180]


def _short(term: str) -> str:
    if len(term) <= 180:
        return term
    return term[:177] + '...'
