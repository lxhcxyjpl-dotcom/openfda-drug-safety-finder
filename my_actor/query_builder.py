"""Validate Actor input and build an openFDA search expression.

A value in ``search`` is sent to openFDA unchanged when it already looks like
an openFDA expression (a ``field:term`` clause). Otherwise it is treated as a
drug, brand, or ingredient phrase: the Actor quotes it and ORs it across the
name fields for the selected mode.

``brandName``, ``genericName``, and ``substanceName`` are used only when
``search`` is empty. They are OR-ed together. At least one of those four
inputs must produce a non-empty expression.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .constants import (
    DEFAULT_MAX_RESULTS,
    MAX_MAX_RESULTS,
    MAX_NAME_LENGTH,
    MAX_QUERY_LENGTH,
    MAX_SKIP,
    MIN_MAX_RESULTS,
    MODES,
    NAME_FIELDS,
    SIMPLE_SEARCH_FIELDS,
)

_API_KEY_RE = re.compile(r'^[A-Za-z0-9._-]{8,128}$')
_FIELD_TERM_RE = re.compile(r'(^|[\s(])[A-Za-z_][\w.]*:')
_API_KEY_MENTION_RE = re.compile(r'api[_-]?key', re.IGNORECASE)


@dataclass(frozen=True)
class ActorInput:
    """Validated search plan. ``api_key`` is omitted from ``repr``."""

    mode: str
    search: str
    max_results: int
    skip: int
    api_key: str | None

    def __repr__(self) -> str:
        key_state = 'set' if self.api_key else 'absent'
        return (
            f'ActorInput(mode={self.mode!r}, search={self.search!r}, '
            f'max_results={self.max_results}, skip={self.skip}, api_key={key_state})'
        )


def parse_actor_input(raw: Any) -> ActorInput:
    """Validate raw Actor input and return the openFDA search to run."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError('Actor input must be a JSON object.')

    mode = _mode(raw.get('mode'))
    search_text = _optional_text(raw.get('search'), 'search', MAX_QUERY_LENGTH)
    brand = _optional_text(raw.get('brandName'), 'brandName', MAX_NAME_LENGTH)
    generic = _optional_text(raw.get('genericName'), 'genericName', MAX_NAME_LENGTH)
    substance = _optional_text(raw.get('substanceName'), 'substanceName', MAX_NAME_LENGTH)
    max_results = _bounded_int(
        raw.get('maxResults'),
        'maxResults',
        default=DEFAULT_MAX_RESULTS,
        minimum=MIN_MAX_RESULTS,
        maximum=MAX_MAX_RESULTS,
    )
    skip = _bounded_int(raw.get('skip'), 'skip', default=0, minimum=0, maximum=MAX_SKIP)
    api_key = _api_key(raw.get('apiKey'))

    if search_text:
        expression = _expression_from_search(search_text, mode)
    else:
        expression = _expression_from_names(mode, brand, generic, substance)

    if not expression:
        raise ValueError(
            'Provide a search expression or a drug name, or set brandName, genericName, or substanceName. '
            'A plain name such as aspirin is converted into an openFDA field search. '
            'A value that already contains field:term syntax, such as '
            'patient.drug.medicinalproduct:aspirin, is sent to openFDA as written.'
        )

    return ActorInput(
        mode=mode,
        search=expression,
        max_results=max_results,
        skip=skip,
        api_key=api_key,
    )


def _mode(raw: Any) -> str:
    if raw is None or raw == '':
        return 'event'
    if not isinstance(raw, str):
        raise ValueError('mode must be a string: event, label, or recall.')
    mode = raw.strip().lower()
    if mode not in MODES:
        allowed = ', '.join(MODES)
        raise ValueError(f'mode must be one of: {allowed}.')
    return mode


def _optional_text(raw: Any, field: str, limit: int) -> str:
    if raw is None:
        return ''
    if not isinstance(raw, str):
        raise ValueError(f'{field} must be a string.')
    if any(ord(char) < 32 and char not in '\t\n\r' for char in raw):
        raise ValueError(f'{field} contains unsupported control characters.')
    text = re.sub(r'\s+', ' ', raw).strip()
    if not text:
        return ''
    if _API_KEY_MENTION_RE.search(text):
        raise ValueError(f'{field} must not contain an API key. Put the openFDA key in the apiKey input.')
    if len(text) > limit:
        raise ValueError(f'{field} is too long (maximum {limit} characters).')
    return text


def _expression_from_search(text: str, mode: str) -> str:
    if _is_expression(text):
        if text.count('(') != text.count(')'):
            raise ValueError('search has unbalanced parentheses.')
        return text
    return _or_fields(SIMPLE_SEARCH_FIELDS[mode], text)


def _expression_from_names(mode: str, brand: str, generic: str, substance: str) -> str:
    fields = NAME_FIELDS[mode]
    clauses: list[str] = []
    for key, value in (('brand', brand), ('generic', generic), ('substance', substance)):
        if value:
            clauses.append(_field_clause(fields[key], value))
    return _join_or(clauses)


def _is_expression(text: str) -> bool:
    """True when the user already wrote openFDA ``field:term`` syntax."""
    return _FIELD_TERM_RE.search(text) is not None


def _or_fields(fields: tuple[str, ...], text: str) -> str:
    return _join_or([_field_clause(field, text) for field in fields])


def _field_clause(field: str, text: str) -> str:
    return f'{field}:{_quote(text)}'


def _join_or(clauses: list[str]) -> str:
    if not clauses:
        return ''
    if len(clauses) == 1:
        return clauses[0]
    return '(' + ' OR '.join(clauses) + ')'


def _quote(text: str) -> str:
    escaped = text.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def _bounded_int(raw: Any, field: str, *, default: int, minimum: int, maximum: int) -> int:
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f'{field} must be an integer.')
    if raw < minimum or raw > maximum:
        raise ValueError(f'{field} must be between {minimum} and {maximum}.')
    return raw


def _api_key(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError('apiKey must be a string.')
    text = raw.strip()
    if not text:
        return None
    if not _API_KEY_RE.fullmatch(text):
        raise ValueError('apiKey must be 8 to 128 letters, digits, dots, underscores, or hyphens, with no spaces.')
    return text
