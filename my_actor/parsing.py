"""Flatten openFDA result objects into dataset rows.

Rows are flat: strings, booleans, numbers, and lists of strings. Nested
openFDA objects are not stored. Empty values are omitted. Long label and
recall text is cut at ``TEXT_MAX_LENGTH`` and marked ``… [truncated]``.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

from .constants import (
    AGE_UNITS,
    DAILYMED_SPL_URL,
    DRUG_CHARACTERIZATION_RANK,
    EVENT_REPORT_URL,
    MAX_LIST_ITEMS,
    PATIENT_SEX,
    SOURCE,
    TEXT_MAX_LENGTH,
    TRUNCATION_SUFFIX,
)

_DATE_RE = re.compile(r'^(\d{4})(\d{2})(\d{2})$')
_UUID_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
_PUBLIC_SENDER = 'fda-public use'

_SERIOUSNESS_FLAGS = (
    'seriousnessdeath',
    'seriousnesshospitalization',
    'seriousnesslifethreatening',
    'seriousnessdisabling',
    'seriousnesscongenitalanomali',
    'seriousnessother',
)

_LABEL_TEXT_FIELDS = (
    'indications_and_usage',
    'warnings',
    'dosage_and_administration',
    'adverse_reactions',
)

_LABEL_LIST_FIELDS = (
    'brand_name',
    'generic_name',
    'manufacturer_name',
    'substance_name',
    'product_ndc',
    'package_ndc',
    'rxcui',
    'spl_id',
    'unii',
    'application_number',
)

_RECALL_TEXT_FIELDS = (
    'product_description',
    'reason_for_recall',
    'distribution_pattern',
    'code_info',
)


def parse_record(mode: str, document: Any) -> dict[str, Any] | None:
    """Flatten one openFDA result for ``mode``. Returns None when nothing usable remains."""
    if mode == 'event':
        return parse_event(document)
    if mode == 'label':
        return parse_label(document)
    if mode == 'recall':
        return parse_recall(document)
    raise ValueError(f'Unknown openFDA mode {mode!r}.')


def parse_event(document: Any) -> dict[str, Any] | None:
    """Flatten one FAERS adverse event report."""
    if not isinstance(document, dict):
        return None
    patient = document.get('patient') if isinstance(document.get('patient'), dict) else {}
    drugs = _ordered_drugs(patient.get('drug'))
    safetyreportid = _text(document.get('safetyreportid'))
    reactions = _unique(_texts(reaction.get('reactionmeddrapt') for reaction in _dicts(patient.get('reaction'))))
    drug_names = _unique(_text(drug.get('medicinalproduct')) for drug in drugs)
    indications = _unique(_text(drug.get('drugindication')) for drug in drugs)
    openfda = _merge_openfda(drug.get('openfda') for drug in drugs)

    row: dict[str, Any] = {
        'mode': 'event',
        'source': SOURCE,
        'safetyreportid': safetyreportid,
        'receivedate': _normalize_date(document.get('receivedate')),
        'serious': _serious_flag(document.get('serious')),
        'patientSex': _patient_sex(patient.get('patientsex')),
        'patientAge': _patient_age(patient.get('patientonsetage'), patient.get('patientonsetageunit')),
        'reactions': reactions or None,
        'drugs': drug_names or None,
        'indications': indications or None,
        'manufacturer': _manufacturers(openfda, document.get('sender')),
        'brand_name': openfda.get('brand_name'),
        'generic_name': openfda.get('generic_name'),
        'substance_name': openfda.get('substance_name'),
        'rxcui': openfda.get('rxcui'),
        'reportUrl': _report_url(safetyreportid),
    }
    for flag in _SERIOUSNESS_FLAGS:
        if document.get(flag) == '1' or document.get(flag) == 1:
            row[flag] = True
    compact = _compact(row)
    if not any(key in compact for key in ('safetyreportid', 'drugs', 'reactions')):
        return None
    return compact


def parse_label(document: Any) -> dict[str, Any] | None:
    """Flatten one SPL drug label."""
    if not isinstance(document, dict):
        return None
    openfda = document.get('openfda') if isinstance(document.get('openfda'), dict) else {}
    set_id = _text(document.get('set_id'))
    row: dict[str, Any] = {
        'mode': 'label',
        'source': SOURCE,
        'set_id': set_id,
        'id': _text(document.get('id')),
        'effective_time': _normalize_date(document.get('effective_time')),
        'spl_url': _spl_url(set_id),
    }
    for field in _LABEL_LIST_FIELDS:
        values = _string_list(openfda.get(field))
        if values:
            row[field] = values
    for field in _LABEL_TEXT_FIELDS:
        text = _join_text(document.get(field))
        if text:
            row[field] = text
    compact = _compact(row)
    if not any(key in compact for key in ('set_id', 'id')):
        return None
    return compact


def parse_recall(document: Any) -> dict[str, Any] | None:
    """Flatten one drug enforcement / recall report."""
    if not isinstance(document, dict):
        return None
    openfda = document.get('openfda') if isinstance(document.get('openfda'), dict) else {}
    row: dict[str, Any] = {
        'mode': 'recall',
        'source': SOURCE,
        'recall_number': _text(document.get('recall_number')),
        'status': _text(document.get('status')),
        'classification': _text(document.get('classification')),
        'recalling_firm': _text(document.get('recalling_firm')),
        'report_date': _normalize_date(document.get('report_date')),
        'product_quantity': _text(document.get('product_quantity')),
    }
    for field in _RECALL_TEXT_FIELDS:
        text = _join_text(document.get(field))
        if text:
            row[field] = text
    for field in ('brand_name', 'generic_name', 'substance_name', 'manufacturer_name'):
        values = _string_list(openfda.get(field))
        if values:
            row[field] = values
    compact = _compact(row)
    if not any(key in compact for key in ('recall_number', 'product_description', 'reason_for_recall')):
        return None
    return compact


def dedupe_key(mode: str, row: dict[str, Any]) -> str | None:
    """Stable identity used to drop duplicate rows inside one run."""
    if mode == 'event':
        value = row.get('safetyreportid')
    elif mode == 'label':
        value = row.get('set_id') or row.get('id')
    elif mode == 'recall':
        value = row.get('recall_number')
    else:
        value = None
    text = _text(value)
    return f'{mode}:{text}' if text else None


def _ordered_drugs(raw: Any) -> list[dict[str, Any]]:
    drugs = _dicts(raw)
    return [drug for _rank, drug in sorted(enumerate(drugs), key=lambda item: _drug_rank(item[1], item[0]))]


def _drug_rank(drug: dict[str, Any], index: int) -> tuple[int, int]:
    code = _text(drug.get('drugcharacterization')) or ''
    return (DRUG_CHARACTERIZATION_RANK.get(code, 9), index)


def _merge_openfda(blocks: Any) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for field in ('brand_name', 'generic_name', 'substance_name', 'manufacturer_name', 'rxcui'):
            bucket = merged.setdefault(field, [])
            markers = seen.setdefault(field, set())
            for value in _string_list(block.get(field), limit=MAX_LIST_ITEMS):
                marker = value.casefold()
                if marker in markers or len(bucket) >= MAX_LIST_ITEMS:
                    continue
                markers.add(marker)
                bucket.append(value)
    return {field: values for field, values in merged.items() if values}


def _manufacturers(openfda: dict[str, list[str]], sender: Any) -> str | None:
    names = list(openfda.get('manufacturer_name') or [])
    if isinstance(sender, dict):
        organization = _text(sender.get('senderorganization'))
        if organization and organization.casefold() != _PUBLIC_SENDER:
            marker = organization.casefold()
            if marker not in {name.casefold() for name in names}:
                names.append(organization)
    if not names:
        return None
    return truncate('; '.join(names[:MAX_LIST_ITEMS]))


def _patient_sex(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    return PATIENT_SEX.get(text)


def _patient_age(age: Any, unit: Any) -> str | None:
    text = _text(age)
    if not text:
        return None
    label = AGE_UNITS.get(_text(unit) or '')
    if label:
        return f'{text} {label}'
    return text


def _serious_flag(value: Any) -> bool | None:
    text = _text(value)
    if text == '1':
        return True
    if text == '2':
        return False
    return None


def _report_url(safetyreportid: str | None) -> str | None:
    if not safetyreportid:
        return None
    query = urlencode({'search': f'safetyreportid:"{safetyreportid}"', 'limit': '1'})
    return f'{EVENT_REPORT_URL}?{query}'


def _spl_url(set_id: str | None) -> str | None:
    if not set_id or _UUID_RE.fullmatch(set_id) is None:
        return None
    return DAILYMED_SPL_URL.format(set_id=set_id)


def _normalize_date(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    match = _DATE_RE.fullmatch(text)
    if match is None:
        return text
    year, month, day = (int(part) for part in match.groups())
    if year < 1900 or year > 2100 or not 1 <= month <= 12 or not 1 <= day <= 31:
        return text
    return f'{year:04d}-{month:02d}-{day:02d}'


def _join_text(value: Any) -> str | None:
    if isinstance(value, str):
        parts = [value]
    elif isinstance(value, list):
        parts = [item for item in value if isinstance(item, str)]
    else:
        return None
    chunks = [re.sub(r'[ \t]+', ' ', part).strip() for part in parts]
    text = '\n\n'.join(chunk for chunk in chunks if chunk)
    if not text:
        return None
    return truncate(text)


def truncate(text: str, limit: int = TEXT_MAX_LENGTH) -> str:
    """Cut ``text`` so the result is at most ``limit`` characters, with a visible marker."""
    if len(text) <= limit:
        return text
    keep = limit - len(TRUNCATION_SUFFIX)
    if keep < 1:
        return text[:limit]
    return text[:keep] + TRUNCATION_SUFFIX


def _string_list(value: Any, *, limit: int = MAX_LIST_ITEMS) -> list[str]:
    if isinstance(value, str):
        raw_items: list[Any] = [value]
    elif isinstance(value, list):
        raw_items = list(value)
    else:
        return []
    return _unique(_text(item) for item in raw_items)[:limit]


def _texts(values: Any) -> list[str | None]:
    return [_text(value) for value in values]


def _unique(values: Any) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = value if isinstance(value, str) else _text(value)
        if not text:
            continue
        marker = text.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        items.append(text)
        if len(items) >= MAX_LIST_ITEMS:
            break
    return items


def _dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in row.items():
        if value is None or value == '' or value == []:
            continue
        compact[key] = value
    return compact


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not value.is_integer():
            return None
        text = str(int(value))
    else:
        text = str(value).strip()
    return text or None
