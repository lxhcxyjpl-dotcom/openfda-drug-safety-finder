"""Paging stops at maxResults and drops duplicate openFDA records."""

from __future__ import annotations

from my_actor.openfda_client import OpenFdaPage
from my_actor.search import collect_records


class FakeClient:
    def __init__(self, pages: list[OpenFdaPage]) -> None:
        self.pages = list(pages)
        self.calls: list[dict[str, object]] = []
        self.page_size = 2

    async def fetch_page(self, *, mode: str, search: str, limit: int, skip: int) -> OpenFdaPage:
        self.calls.append({'mode': mode, 'search': search, 'limit': limit, 'skip': skip})
        if not self.pages:
            return OpenFdaPage(results=[], total=0)
        return self.pages.pop(0)


class ListLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def info(self, msg: str, *args: object, **kwargs: object) -> None:
        return None

    def warning(self, msg: str, *args: object, **kwargs: object) -> None:
        self.warnings.append(msg)

    def debug(self, msg: str, *args: object, **kwargs: object) -> None:
        return None


def _event(report_id: str) -> dict:
    return {
        'safetyreportid': report_id,
        'receivedate': '20140312',
        'serious': '2',
        'patient': {'drug': [{'medicinalproduct': 'ASPIRIN', 'drugcharacterization': '1'}]},
    }


async def test_pages_until_max_results_and_dedupes_report_ids() -> None:
    client = FakeClient(
        [
            OpenFdaPage(results=[_event('1'), _event('1'), _event('2')], total=25),
            OpenFdaPage(results=[_event('2'), _event('3')], total=25),
        ]
    )
    pushed: list[list[dict]] = []

    async def on_batch(rows: list[dict]) -> None:
        pushed.append(rows)

    result = await collect_records(
        client,  # type: ignore[arg-type]
        mode='event',
        search='patient.drug.medicinalproduct:"aspirin"',
        max_results=10,
        skip=20,
        logger=ListLogger(),
        on_batch=on_batch,
    )
    assert [row['safetyreportid'] for row in result.rows] == ['1', '2', '3']
    assert [row['safetyreportid'] for batch in pushed for row in batch] == ['1', '2', '3']
    assert result.total == 25
    assert result.pages == 2
    assert client.calls[0]['skip'] == 20
    assert client.calls[0]['limit'] == 2
    assert client.calls[1]['skip'] == 23


async def test_max_results_stops_inside_the_first_page() -> None:
    client = FakeClient([OpenFdaPage(results=[_event('1'), _event('2'), _event('3')], total=3)])
    result = await collect_records(
        client,  # type: ignore[arg-type]
        mode='event',
        search='aspirin',
        max_results=1,
        skip=0,
        logger=ListLogger(),
    )
    assert [row['safetyreportid'] for row in result.rows] == ['1']
    assert client.calls == [{'mode': 'event', 'search': 'aspirin', 'limit': 1, 'skip': 0}]


async def test_not_found_page_finishes_with_zero_rows() -> None:
    client = FakeClient([OpenFdaPage(results=[], total=0)])
    result = await collect_records(
        client,  # type: ignore[arg-type]
        mode='label',
        search='openfda.brand_name:"missing"',
        max_results=5,
        skip=0,
        logger=ListLogger(),
    )
    assert result.rows == []
    assert result.total == 0
    assert result.pages == 1


async def test_unflattenable_record_is_skipped_with_a_warning() -> None:
    logger = ListLogger()
    client = FakeClient([OpenFdaPage(results=[{'serious': '1'}, _event('4')], total=2)])
    result = await collect_records(
        client,  # type: ignore[arg-type]
        mode='event',
        search='aspirin',
        max_results=5,
        skip=0,
        logger=logger,
    )
    assert [row['safetyreportid'] for row in result.rows] == ['4']
    assert logger.warnings
