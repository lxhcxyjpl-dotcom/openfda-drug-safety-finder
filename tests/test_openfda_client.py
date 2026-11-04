"""HTTP behaviour is covered with a mock transport."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from my_actor.constants import RATE_SAFETY_FACTOR, REQUESTS_PER_MINUTE
from my_actor.openfda_client import (
    OpenFdaClient,
    OpenFdaPage,
    OpenFdaRequestError,
    RateLimiter,
    polite_interval,
    redact_secrets,
)

FIXTURES = Path(__file__).parent / 'fixtures'


class ListLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def info(self, msg: str, *args: object, **kwargs: object) -> None:
        self.infos.append(msg)

    def warning(self, msg: str, *args: object, **kwargs: object) -> None:
        self.warnings.append(msg)

    def debug(self, msg: str, *args: object, **kwargs: object) -> None:
        return None


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _params(request: httpx.Request) -> dict[str, str]:
    return dict(request.url.params)


async def test_rate_limiter_spaces_request_starts() -> None:
    clock = FakeClock()
    limiter = RateLimiter(0.5, sleep=clock.sleep, monotonic=clock.monotonic)
    await limiter.wait()
    await limiter.wait()
    assert clock.slept == [0.5]


def test_polite_interval_stays_under_the_published_ceiling() -> None:
    assert polite_interval() == pytest.approx(RATE_SAFETY_FACTOR * (60.0 / REQUESTS_PER_MINUTE))
    assert polite_interval() > 60.0 / REQUESTS_PER_MINUTE


async def test_default_interval_does_not_depend_on_the_api_key() -> None:
    async with OpenFdaClient() as without_key, OpenFdaClient(api_key='test-key.1234') as with_key:
        assert without_key.min_interval == pytest.approx(polite_interval())
        assert with_key.min_interval == pytest.approx(without_key.min_interval)


def test_redact_secrets_removes_key_from_urls_and_text() -> None:
    raw = 'https://api.fda.gov/drug/event.json?api_key=test-key.1234&search=aspirin'
    assert 'test-key.1234' not in redact_secrets(raw, 'test-key.1234')
    assert 'api_key=***' in redact_secrets(raw)


async def test_fetch_page_sends_get_with_key_only_as_a_query_param() -> None:
    seen: list[httpx.Request] = []
    payload = json.loads((FIXTURES / 'event_page.json').read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with OpenFdaClient(api_key='test-key.1234', http_client=http, min_interval=0) as client:
            page = await client.fetch_page(
                mode='event',
                search='patient.drug.medicinalproduct:"aspirin"',
                limit=1,
                skip=0,
            )
    assert page == OpenFdaPage(results=payload['results'], total=3)
    request = seen[0]
    assert request.method == 'GET'
    assert request.url.host == 'api.fda.gov'
    assert request.url.path == '/drug/event.json'
    params = _params(request)
    assert params['search'] == 'patient.drug.medicinalproduct:"aspirin"'
    assert params['limit'] == '1'
    assert params['skip'] == '0'
    assert params['sort'] == 'receivedate:desc'
    assert params['api_key'] == 'test-key.1234'
    assert 'test-key.1234' not in (request.headers.get('authorization') or '')


async def test_fetch_page_omits_key_when_absent() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(_params(request))
        return httpx.Response(200, json={'meta': {'results': {'total': 0}}, 'results': []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with OpenFdaClient(http_client=http, min_interval=0) as client:
            page = await client.fetch_page(mode='label', search='openfda.brand_name:"aspirin"', limit=5, skip=2)
    assert page.results == []
    assert page.total == 0
    assert 'api_key' not in seen[0]
    assert seen[0]['sort'] == 'effective_time:desc'
    assert seen[0]['skip'] == '2'


async def test_not_found_is_an_empty_page() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={'error': {'code': 'NOT_FOUND', 'message': 'No matches found!'}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with OpenFdaClient(http_client=http, min_interval=0) as client:
            page = await client.fetch_page(mode='recall', search='openfda.brand_name:"no-such-drug"', limit=1, skip=0)
    assert page.results == []
    assert page.total == 0


async def test_retries_429_then_succeeds_without_logging_the_key() -> None:
    calls = {'n': 0}
    logger = ListLogger()
    clock = FakeClock()

    def handler(_request: httpx.Request) -> httpx.Response:
        calls['n'] += 1
        if calls['n'] < 3:
            return httpx.Response(429, headers={'Retry-After': '0'}, text='rate limit for api_key=test-key.1234')
        return httpx.Response(200, json={'meta': {'results': {'total': 1}}, 'results': [{'safetyreportid': '1'}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with OpenFdaClient(
            api_key='test-key.1234',
            http_client=http,
            min_interval=0,
            sleep=clock.sleep,
            logger=logger,
        ) as client:
            page = await client.fetch_page(mode='event', search='safetyreportid:1', limit=1, skip=0)
    assert [row['safetyreportid'] for row in page.results] == ['1']
    assert calls['n'] == 3
    assert clock.slept == [1.0, 2.0]
    logged = ' '.join(logger.warnings + logger.infos)
    assert 'test-key.1234' not in logged
    assert 'HTTP 429' in logged


async def test_server_error_gives_up_with_a_safe_message() -> None:
    calls = {'n': 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls['n'] += 1
        return httpx.Response(503, text='upstream failed test-key.1234')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with OpenFdaClient(
            api_key='test-key.1234',
            http_client=http,
            min_interval=0,
            sleep=_no_sleep,
            max_attempts=2,
        ) as client:
            with pytest.raises(OpenFdaRequestError, match='HTTP 503') as caught:
                await client.fetch_page(mode='event', search='aspirin', limit=1, skip=0)
    assert calls['n'] == 2
    assert 'test-key.1234' not in str(caught.value)


async def test_parse_exception_is_not_retried() -> None:
    calls = {'n': 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls['n'] += 1
        return httpx.Response(
            500,
            json={'error': {'code': 'SERVER_ERROR', 'message': 'Check your request', 'details': 'parse_exception'}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with OpenFdaClient(http_client=http, min_interval=0, max_attempts=5) as client:
            with pytest.raises(OpenFdaRequestError, match='could not parse') as caught:
                await client.fetch_page(mode='event', search=':', limit=1, skip=0)
    assert calls['n'] == 1
    assert 'api_key' not in str(caught.value)


async def test_rejected_request_redacts_the_key_in_the_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='bad key test-key.1234 rejected')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with OpenFdaClient(api_key='test-key.1234', http_client=http, min_interval=0) as client:
            with pytest.raises(OpenFdaRequestError, match='HTTP 400') as caught:
                await client.fetch_page(mode='event', search='aspirin', limit=1, skip=0)
    assert 'test-key.1234' not in str(caught.value)
    assert 'bad key' in str(caught.value)


async def _no_sleep(_seconds: float) -> None:
    return None
