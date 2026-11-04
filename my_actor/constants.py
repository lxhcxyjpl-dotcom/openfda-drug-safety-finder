"""Shared constants for the OpenFDA Drug Safety Finder Actor."""

from __future__ import annotations

TOOL_NAME = 'openfda-drug-safety-finder'
CONTACT_EMAIL = 'actor@apify.local'
OPENFDA_BASE = 'https://api.fda.gov'
USER_AGENT = f'{TOOL_NAME}/0.1 ({CONTACT_EMAIL})'

# Official openFDA paths. This Actor never requests FDA HTML pages.
ENDPOINTS: dict[str, str] = {
    'event': '/drug/event.json',
    'label': '/drug/label.json',
    'recall': '/drug/enforcement.json',
}

# Newest records first. Sort is separate from the search expression.
SORT: dict[str, str] = {
    'event': 'receivedate:desc',
    'label': 'effective_time:desc',
    'recall': 'report_date:desc',
}

# Plain drug text is quoted and OR-ed across these fields.
# https://open.fda.gov/apis/drug/event/searchable-fields/
SIMPLE_SEARCH_FIELDS: dict[str, tuple[str, ...]] = {
    'event': (
        'patient.drug.medicinalproduct',
        'patient.drug.openfda.brand_name',
        'patient.drug.openfda.generic_name',
        'patient.drug.openfda.substance_name',
    ),
    'label': (
        'openfda.brand_name',
        'openfda.generic_name',
        'openfda.substance_name',
    ),
    'recall': (
        'openfda.brand_name',
        'openfda.generic_name',
        'openfda.substance_name',
        'product_description',
    ),
}

# Optional name inputs, used only when `search` is empty.
NAME_FIELDS: dict[str, dict[str, str]] = {
    'event': {
        'brand': 'patient.drug.openfda.brand_name',
        'generic': 'patient.drug.openfda.generic_name',
        'substance': 'patient.drug.openfda.substance_name',
    },
    'label': {
        'brand': 'openfda.brand_name',
        'generic': 'openfda.generic_name',
        'substance': 'openfda.substance_name',
    },
    'recall': {
        'brand': 'openfda.brand_name',
        'generic': 'openfda.generic_name',
        'substance': 'openfda.substance_name',
    },
}

# openFDA: 240 requests/minute with or without a key. The key raises the
# daily cap from 1,000/IP to 120,000/key. A 10% gap stays under that ceiling.
REQUESTS_PER_MINUTE = 240.0
RATE_SAFETY_FACTOR = 1.1

PAGE_SIZE = 100
MAX_ATTEMPTS = 5
DEFAULT_MAX_RESULTS = 50
MIN_MAX_RESULTS = 1
MAX_MAX_RESULTS = 500
MAX_SKIP = 25000
MAX_QUERY_LENGTH = 4000
MAX_NAME_LENGTH = 300
TEXT_MAX_LENGTH = 4000
TRUNCATION_SUFFIX = '… [truncated]'
MAX_LIST_ITEMS = 40

SOURCE = 'openFDA'
EVENT_REPORT_URL = 'https://api.fda.gov/drug/event.json'
DAILYMED_SPL_URL = 'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}'

# FAERS sex codes and age-unit codes from the openFDA drug event dictionary.
PATIENT_SEX: dict[str, str] = {
    '0': 'Unknown',
    '1': 'Male',
    '2': 'Female',
}
AGE_UNITS: dict[str, str] = {
    '800': 'decades',
    '801': 'years',
    '802': 'months',
    '803': 'weeks',
    '804': 'days',
    '805': 'hours',
}

# drugcharacterization: 1 suspect, 2 concomitant, 3 interacting.
DRUG_CHARACTERIZATION_RANK: dict[str, int] = {
    '1': 0,
    '3': 1,
    '2': 2,
}

FAERS_DISCLAIMER = (
    'FAERS reports describe adverse events submitted to FDA. '
    'A report does not prove that the drug caused the reaction, '
    'and these rows are not medical advice or incidence estimates.'
)

MODES: tuple[str, ...] = ('event', 'label', 'recall')
