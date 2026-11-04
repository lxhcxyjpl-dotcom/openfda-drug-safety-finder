"""Query building does not call openFDA."""

from __future__ import annotations

import pytest

from my_actor.query_builder import parse_actor_input


def test_plain_drug_name_is_quoted_and_or_ed_across_event_fields() -> None:
    plan = parse_actor_input({'search': 'aspirin'})
    assert plan.mode == 'event'
    assert plan.max_results == 50
    assert plan.skip == 0
    assert plan.api_key is None
    assert plan.search == (
        '(patient.drug.medicinalproduct:"aspirin" OR '
        'patient.drug.openfda.brand_name:"aspirin" OR '
        'patient.drug.openfda.generic_name:"aspirin" OR '
        'patient.drug.openfda.substance_name:"aspirin")'
    )


def test_plain_phrase_keeps_spaces_inside_one_pair_of_quotes() -> None:
    plan = parse_actor_input({'search': '  tylenol   extra strength  ', 'mode': 'label'})
    assert plan.search == (
        '(openfda.brand_name:"tylenol extra strength" OR '
        'openfda.generic_name:"tylenol extra strength" OR '
        'openfda.substance_name:"tylenol extra strength")'
    )


def test_recall_plain_text_includes_product_description() -> None:
    plan = parse_actor_input({'search': 'aspirin', 'mode': 'RECALL'})
    assert plan.mode == 'recall'
    assert plan.search == (
        '(openfda.brand_name:"aspirin" OR '
        'openfda.generic_name:"aspirin" OR '
        'openfda.substance_name:"aspirin" OR '
        'product_description:"aspirin")'
    )


def test_field_expression_is_sent_unchanged() -> None:
    expression = 'patient.drug.medicinalproduct:aspirin'
    plan = parse_actor_input({'search': expression, 'maxResults': 25, 'skip': 100})
    assert plan.search == expression
    assert plan.max_results == 25
    assert plan.skip == 100


def test_grouped_expression_is_sent_unchanged() -> None:
    expression = '(openfda.generic_name:"acetaminophen" AND effective_time:[20200101 TO 20241231])'
    plan = parse_actor_input({'search': expression, 'mode': 'label'})
    assert plan.search == expression


def test_lowercase_and_inside_a_drug_name_stays_a_phrase() -> None:
    plan = parse_actor_input({'search': 'cold and flu', 'mode': 'label'})
    assert 'openfda.brand_name:"cold and flu"' in plan.search
    assert ' AND ' not in plan.search


def test_quotes_and_backslashes_in_a_plain_name_are_escaped() -> None:
    plan = parse_actor_input({'search': 'acme "plus"\\tab', 'mode': 'label'})
    assert 'openfda.brand_name:"acme \\"plus\\"\\\\tab"' in plan.search


def test_name_fields_are_or_ed_only_when_search_is_empty() -> None:
    plan = parse_actor_input(
        {
            'mode': 'event',
            'brandName': 'Tylenol',
            'genericName': 'acetaminophen',
            'substanceName': 'acetaminophen',
        }
    )
    assert plan.search == (
        '(patient.drug.openfda.brand_name:"Tylenol" OR '
        'patient.drug.openfda.generic_name:"acetaminophen" OR '
        'patient.drug.openfda.substance_name:"acetaminophen")'
    )


def test_search_wins_over_name_fields() -> None:
    plan = parse_actor_input({'search': 'ibuprofen', 'brandName': 'Tylenol', 'mode': 'label'})
    assert 'ibuprofen' in plan.search
    assert 'Tylenol' not in plan.search


def test_one_name_field_has_no_extra_parentheses() -> None:
    plan = parse_actor_input({'brandName': 'Bayer', 'mode': 'recall'})
    assert plan.search == 'openfda.brand_name:"Bayer"'


def test_api_key_is_kept_but_hidden_from_repr() -> None:
    plan = parse_actor_input({'search': 'aspirin', 'apiKey': '  test-key.1234  '})
    assert plan.api_key == 'test-key.1234'
    assert 'test-key.1234' not in repr(plan)
    assert 'api_key=set' in repr(plan)


@pytest.mark.parametrize(
    ('raw', 'message'),
    [
        ({}, 'Provide a search'),
        ({'search': '   ', 'brandName': '  '}, 'Provide a search'),
        ({'mode': 'events', 'search': 'aspirin'}, 'mode must be one of'),
        ({'search': 'patient.drug.medicinalproduct:(aspirin'}, 'unbalanced parentheses'),
        ({'maxResults': 0, 'search': 'aspirin'}, 'between 1 and 500'),
        ({'maxResults': 501, 'search': 'aspirin'}, 'between 1 and 500'),
        ({'maxResults': True, 'search': 'aspirin'}, 'must be an integer'),
        ({'maxResults': '50', 'search': 'aspirin'}, 'must be an integer'),
        ({'skip': -1, 'search': 'aspirin'}, 'between 0 and 25000'),
        ({'skip': 25001, 'search': 'aspirin'}, 'between 0 and 25000'),
        ({'apiKey': 'short', 'search': 'aspirin'}, 'apiKey'),
        ({'search': 'a\x00b'}, 'control characters'),
        ({'search': 'patient.drug.medicinalproduct:aspirin&api_key=secret'}, 'must not contain an API key'),
        ({'brandName': 12}, 'brandName must be a string'),
    ],
)
def test_invalid_input_raises_value_error(raw: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_actor_input(raw)
