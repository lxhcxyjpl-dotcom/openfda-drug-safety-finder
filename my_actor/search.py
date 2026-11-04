"""Page an openFDA search into flat dataset rows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .constants import MAX_SKIP
from .openfda_client import Logger, OpenFdaClient
from .parsing import dedupe_key, parse_record


@dataclass(frozen=True)
class CollectResult:
    """Flat rows plus the totals openFDA reported for this search."""

    rows: list[dict[str, Any]]
    total: int | None
    pages: int


async def collect_records(
    client: OpenFdaClient,
    *,
    mode: str,
    search: str,
    max_results: int,
    skip: int,
    logger: Logger,
    on_batch: Callable[[list[dict[str, Any]]], Awaitable[None]] | None = None,
) -> CollectResult:
    """Fetch pages until ``max_results`` rows are saved or openFDA runs out."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    offset = skip
    total: int | None = None
    pages = 0

    while len(rows) < max_results:
        if offset > MAX_SKIP:
            logger.warning(f'Stopping at openFDA skip limit ({MAX_SKIP}).')
            break
        page_limit = min(client.page_size, max_results - len(rows))
        page = await client.fetch_page(mode=mode, search=search, limit=page_limit, skip=offset)
        pages += 1
        if page.total is not None:
            total = page.total
        if not page.results:
            break

        batch: list[dict[str, Any]] = []
        for document in page.results:
            if len(rows) >= max_results:
                break
            row = parse_record(mode, document)
            if row is None:
                logger.warning('openFDA returned a record that could not be flattened.')
                continue
            key = dedupe_key(mode, row)
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)
            rows.append(row)
            batch.append(row)
        if on_batch is not None and batch:
            await on_batch(batch)

        offset += len(page.results)
        if len(page.results) < page_limit:
            break
        if total is not None and offset >= total:
            break

    return CollectResult(rows=rows, total=total, pages=pages)
