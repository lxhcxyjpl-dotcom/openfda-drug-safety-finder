"""Actor schemas stay aligned with the fields the code can write."""

from __future__ import annotations

import json
from pathlib import Path

from my_actor.constants import MODES

ROOT = Path(__file__).resolve().parents[1]
ACTOR = ROOT / '.actor'


def _load(name: str) -> dict:
    return json.loads((ACTOR / name).read_text())


def test_actor_metadata_names_this_actor() -> None:
    actor = _load('actor.json')
    assert actor['name'] == 'openfda-drug-safety-finder'
    assert actor['title'] == 'OpenFDA Drug Safety Finder'
    assert actor['meta']['templateId'] == 'python-empty'
    assert actor['meta']['generatedBy'] == 'Cursor with Grok 4.7'
    assert 'FAERS' in actor['description'] or 'adverse' in actor['description'].lower()


def test_mode_enum_matches_the_code() -> None:
    schema = _load('input_schema.json')
    assert schema['properties']['mode']['enum'] == list(MODES)
    assert schema['properties']['mode']['default'] == 'event'
    assert schema['properties']['search']['prefill'] == 'aspirin'
    assert schema['properties']['apiKey']['isSecret'] is True
    assert schema['properties']['maxResults']['minimum'] == 1
    assert schema['properties']['maxResults']['maximum'] == 500
    assert 'mode' in schema['required']


def test_dataset_views_only_use_declared_fields() -> None:
    schema = _load('dataset_schema.json')
    declared = set(schema['fields']['properties'])
    assert {'mode', 'source', 'safetyreportid', 'set_id', 'recall_number', 'reportUrl', 'spl_url'} <= declared
    for name, view in schema['views'].items():
        fields = view['transformation']['fields']
        missing = [field for field in fields if field not in declared]
        assert missing == [], name
        display = set(view['display']['properties'])
        assert display == set(fields)


def test_readme_has_the_faers_disclaimer_and_price() -> None:
    readme = (ROOT / 'README.md').read_text()
    assert 'not medical advice' in readme.lower() or 'not a diagnosis' in readme.lower()
    assert 'does not prove' in readme.lower()
    assert '$0.003' in readme
    assert 'api.fda.gov' in readme
