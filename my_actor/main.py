"""Apify Actor entry point for OpenFDA Drug Safety Finder."""

from __future__ import annotations

from typing import Any

from apify import Actor, Event

from .constants import ENDPOINTS, FAERS_DISCLAIMER, SOURCE
from .openfda_client import OpenFdaClient, OpenFdaRequestError, redact_secrets
from .query_builder import parse_actor_input
from .search import collect_records

_MODE_LABEL = {
    'event': 'adverse event report',
    'label': 'drug label',
    'recall': 'recall report',
}


async def _on_abort(_event_data: Any) -> None:
    Actor.log.warning('Aborting. Records already written to the dataset are kept.')
    await Actor.exit()


async def main() -> None:
    """Query openFDA and push one flat dataset row per adverse event, label, or recall."""
    async with Actor:
        Actor.on(Event.ABORTING, _on_abort)
        raw_input = await Actor.get_input()
        try:
            actor_input = parse_actor_input(raw_input)
        except ValueError as exc:
            message = str(exc)
            Actor.log.error(message)
            await Actor.fail(status_message=message, exception=exc)
            return

        safe_search = redact_secrets(actor_input.search, actor_input.api_key)
        Actor.log.info(
            'Starting openFDA search.',
            extra={
                'mode': actor_input.mode,
                'endpoint': ENDPOINTS[actor_input.mode],
                'maxResults': actor_input.max_results,
                'skip': actor_input.skip,
                'apiKey': bool(actor_input.api_key),
                'search': safe_search,
            },
        )
        await Actor.set_status_message(f'Searching openFDA {actor_input.mode} records.')

        async def push_batch(rows: list[dict[str, Any]]) -> None:
            if rows:
                await Actor.push_data(rows)

        try:
            async with OpenFdaClient(api_key=actor_input.api_key, logger=Actor.log) as client:
                result = await collect_records(
                    client,
                    mode=actor_input.mode,
                    search=actor_input.search,
                    max_results=actor_input.max_results,
                    skip=actor_input.skip,
                    logger=Actor.log,
                    on_batch=push_batch,
                )
        except (OpenFdaRequestError, ValueError) as exc:
            message = redact_secrets(str(exc), actor_input.api_key)
            Actor.log.error(message)
            await Actor.fail(status_message=message, exception=exc)
            return

        overview: dict[str, Any] = {
            'resultCount': len(result.rows),
            'totalMatches': result.total,
            'pages': result.pages,
            'source': SOURCE,
            'mode': actor_input.mode,
            'endpoint': ENDPOINTS[actor_input.mode],
            'search': safe_search,
            'skip': actor_input.skip,
            'maxResults': actor_input.max_results,
        }
        if actor_input.mode == 'event':
            overview['disclaimer'] = FAERS_DISCLAIMER
        overview = {key: value for key, value in overview.items() if value is not None}
        await Actor.set_value('OUTPUT', overview)

        noun = _MODE_LABEL[actor_input.mode]
        if result.rows:
            final_message = f'Saved {len(result.rows)} openFDA {noun}{"s" if len(result.rows) != 1 else ""}.'
        else:
            final_message = 'No openFDA records matched this search.'
        Actor.status_message = final_message
        Actor.log.info(final_message)
