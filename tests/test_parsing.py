"""Parsing uses saved openFDA documents, not the network."""

from __future__ import annotations

import json
from pathlib import Path

from my_actor.constants import TEXT_MAX_LENGTH, TRUNCATION_SUFFIX
from my_actor.parsing import parse_event, parse_label, parse_recall, parse_record, truncate

FIXTURES = Path(__file__).parent / 'fixtures'


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_event_fixture_flattens_to_one_row() -> None:
    row = parse_event(_load('event_aspirin.json'))
    assert row is not None
    assert row['mode'] == 'event'
    assert row['source'] == 'openFDA'
    assert row['safetyreportid'] == '10003304'
    assert row['receivedate'] == '2014-03-12'
    assert row['serious'] is True
    assert row['seriousnessdeath'] is True
    assert row['seriousnesslifethreatening'] is True
    assert 'seriousnesshospitalization' not in row
    assert row['patientSex'] == 'Female'
    assert row['patientAge'] == '65 years'
    assert row['reactions'] == ['Nausea', 'Headache']
    assert row['drugs'] == ['ASPIRIN 81 MG', 'ACETAMINOPHEN']
    assert row['indications'] == ['Pain']
    assert row['manufacturer'] == 'Example Pharma'
    assert row['brand_name'] == ['ASPIRIN', 'TYLENOL']
    assert row['generic_name'] == ['ASPIRIN', 'ACETAMINOPHEN']
    assert row['substance_name'] == ['ASPIRIN']
    assert row['rxcui'] == ['243670', '198440']
    assert row['reportUrl'] == (
        'https://api.fda.gov/drug/event.json?search=safetyreportid%3A%2210003304%22&limit=1'
    )
    assert 'patient' not in row
    assert 'sender' not in row
    assert all(value is not None and value != '' and value != [] for value in row.values())


def test_not_serious_is_kept_and_public_sender_is_not_a_manufacturer() -> None:
    row = parse_record('event', _load('event_page.json')['results'][0])
    assert row is not None
    assert row['serious'] is False
    assert row['patientSex'] == 'Male'
    assert 'patientAge' not in row
    assert 'manufacturer' not in row
    assert 'seriousnessdeath' not in row


def test_sender_organization_is_used_when_openfda_has_no_manufacturer() -> None:
    row = parse_event(
        {
            'safetyreportid': '9',
            'serious': '1',
            'sender': {'senderorganization': 'Example Labs'},
            'patient': {'drug': [{'medicinalproduct': 'ASPIRIN', 'drugcharacterization': '1'}]},
        }
    )
    assert row is not None
    assert row['manufacturer'] == 'Example Labs'
    assert row['serious'] is True


def test_unknown_sex_and_age_without_a_unit_are_kept() -> None:
    row = parse_event(
        {
            'safetyreportid': '10',
            'patient': {'patientsex': '0', 'patientonsetage': '6', 'patientonsetageunit': '802'},
        }
    )
    assert row is not None
    assert row['patientSex'] == 'Unknown'
    assert row['patientAge'] == '6 months'


def test_label_fixture_flattens_openfda_and_builds_a_spl_url() -> None:
    row = parse_label(_load('label_aspirin.json'))
    assert row is not None
    assert row['mode'] == 'label'
    assert row['source'] == 'openFDA'
    assert row['set_id'] == '0058175f-3474-40c3-a046-6cfaec86d84b'
    assert row['id'] == '008ee85b-5cac-45a6-a857-a828f8125175'
    assert row['effective_time'] == '2024-04-16'
    assert row['brand_name'] == ['ASPIRIN']
    assert row['generic_name'] == ['ASPIRIN']
    assert row['manufacturer_name'] == ['Example Labeler']
    assert row['product_ndc'] == ['0536-1234']
    assert row['rxcui'] == ['243670']
    assert row['indications_and_usage'] == 'Temporarily relieves minor aches and pains.'
    assert row['spl_url'] == (
        'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=0058175f-3474-40c3-a046-6cfaec86d84b'
    )
    assert 'openfda' not in row
    assert 'product_type' not in row
    assert 'adverse_reactions' not in row


def test_long_label_text_is_truncated_with_a_marker() -> None:
    warnings = 'W' * (TEXT_MAX_LENGTH + 50)
    row = parse_label(
        {
            'set_id': '0058175f-3474-40c3-a046-6cfaec86d84b',
            'warnings': [warnings, 'second paragraph'],
        }
    )
    assert row is not None
    assert row['warnings'].endswith(TRUNCATION_SUFFIX)
    assert len(row['warnings']) == TEXT_MAX_LENGTH
    assert 'second paragraph' not in row['warnings']


def test_truncate_leaves_short_text_unchanged() -> None:
    assert truncate('short') == 'short'


def test_recall_fixture_flattens_enforcement_fields() -> None:
    row = parse_recall(_load('recall_aspirin.json'))
    assert row is not None
    assert row['mode'] == 'recall'
    assert row['source'] == 'openFDA'
    assert row['recall_number'] == 'D-0170-2024'
    assert row['status'] == 'Terminated'
    assert row['classification'] == 'Class II'
    assert row['product_description'] == 'Low Dose ASPIRIN, 81 mg, enteric coated tablets.'
    assert row['reason_for_recall'] == 'Products were stored outside labeled conditions.'
    assert row['recalling_firm'] == 'EXAMPLE DISTRIBUTION'
    assert row['report_date'] == '2024-01-03'
    assert row['distribution_pattern'] == 'Nationwide in the United States'
    assert row['product_quantity'] == '2 units'
    assert row['code_info'] == 'Batch P126201'
    assert row['brand_name'] == ['ASPIRIN']
    assert row['manufacturer_name'] == ['Example Laboratories']
    assert 'city' not in row
    assert 'openfda' not in row


def test_records_without_an_identity_are_skipped() -> None:
    assert parse_event({'serious': '1'}) is None
    assert parse_label({'warnings': ['none']}) is None
    assert parse_recall({'status': 'Ongoing'}) is None
    assert parse_record('event', ['not-a-document']) is None
