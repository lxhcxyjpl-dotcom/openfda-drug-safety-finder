## What does OpenFDA Drug Safety Finder do?

**OpenFDA Drug Safety Finder** queries the official [openFDA](https://open.fda.gov/apis/) JSON API and saves **one flat row per record** for drug safety, labeling, and recall work. It reads three public datasets on `https://api.fda.gov`:

- **FAERS adverse events** (`mode=event`, `/drug/event.json`)
- **Drug labels / Structured Product Labeling** (`mode=label`, `/drug/label.json`)
- **Drug recalls / enforcement reports** (`mode=recall`, `/drug/enforcement.json`)

The Actor does not download or parse FDA website HTML, and it does not need a login. An openFDA API key is optional. Every row includes `mode` and `source` set to `openFDA`. Empty fields are left out.

## Why use OpenFDA Drug Safety Finder?

Pharmacovigilance, medical information, and quality teams use openFDA when they need a spreadsheet of public safety records instead of a browser session:

- Pull recent **FAERS adverse event** reports for a brand, generic, or substance
- Export **drug label** sections such as indications, warnings, dosage, and adverse reactions
- List **drug recall** classification, reason, recalling firm, and distribution
- Schedule the run, call it from the Apify API, or connect it to Make, Zapier, or n8n

Because the source is the documented API, the run does not depend on the FDA website layout, a headless browser, or proxy rotation. That is a different approach from Store Actors that scrape Drugs.com, DailyMed HTML, or fda.gov pages and charge more for the same public records.

## What data can OpenFDA Drug Safety Finder extract?

Dates stored as `YYYYMMDD` are rewritten as `YYYY-MM-DD`. Text fields longer than 4,000 characters are cut and end with `… [truncated]`. Lists are de-duplicated.

### Adverse events (FAERS)

| Field | What it contains |
| --- | --- |
| `safetyreportid` | FAERS safety report id |
| `receivedate` | Date FDA received the report |
| `serious` | `true` when openFDA marks the report serious (`1`), `false` when it is not (`2`) |
| `seriousnessdeath`, `seriousnesshospitalization` | `true` when that outcome flag is `1`. The same rule applies to `seriousnesslifethreatening`, `seriousnessdisabling`, `seriousnesscongenitalanomali` (openFDA's field name), and `seriousnessother` |
| `patientSex`, `patientAge` | Mapped from FAERS codes (`Female`, `Male`, `Unknown`; age such as `65 years`) |
| `reactions` | MedDRA preferred terms |
| `drugs`, `indications` | Product names as reported, and drug indications. Suspect products are listed before concomitant ones |
| `manufacturer` | openFDA manufacturer names, or the sender organization when it is not the public-use sender |
| `brand_name`, `generic_name`, `substance_name`, `rxcui` | openFDA harmonized names and RxNorm CUIs, when FDA attached them |
| `reportUrl` | Official API URL for that safety report id |

A FAERS report can list several drugs and several reactions. openFDA does not link one drug to one reaction. Presence on a row is not evidence that the drug caused the reaction.

### Drug labels

| Field | What it contains |
| --- | --- |
| `set_id`, `id` | SPL set id and document id |
| `brand_name`, `generic_name`, `manufacturer_name`, `substance_name` | openFDA names |
| `indications_and_usage`, `warnings`, `dosage_and_administration`, `adverse_reactions` | Label text, truncated |
| `product_ndc`, `package_ndc`, `rxcui`, `spl_id`, `unii`, `application_number` | openFDA identifiers |
| `effective_time` | Label effective time |
| `spl_url` | DailyMed SPL page built from `set_id` when that id is a UUID |

### Recalls

| Field | What it contains |
| --- | --- |
| `recall_number`, `status`, `classification` | Enforcement report id, status, and class |
| `product_description`, `reason_for_recall`, `code_info` | What was recalled and why |
| `recalling_firm`, `report_date`, `distribution_pattern`, `product_quantity` | Firm, date, where it was distributed, and how much |
| `brand_name`, `generic_name`, `substance_name`, `manufacturer_name` | openFDA names when the report has them |

## How to search FAERS adverse events, drug labels, and recalls

1. Open the Actor and choose **Try it** or **Start**.
2. Leave **Search** as a plain name such as `aspirin`, or paste an [openFDA search expression](https://open.fda.gov/apis/query-syntax/).
3. Choose **Mode**: adverse events, drug labels, or recalls. The default is adverse events.
4. If Search is empty, fill **Brand name**, **Generic name**, or **Substance name** instead. Those three are combined with OR.
5. Set **Maximum results** (1–500, default 50). The Actor sorts by the dataset date, newest first, and stops at this cap.
6. Optionally paste an **openFDA API key**. Without it the public limit is 240 requests per minute and 1,000 requests per day per IP. With a free key the daily limit is 120,000. The Actor still waits between calls. The key is sent only to `api.fda.gov`.
7. Run the Actor and open the dataset. Download JSON, CSV, Excel, or XML, or call the dataset API.

### How a plain name becomes a search

If **Search** contains `field:term` syntax, it is sent as written. Examples:

- `patient.drug.medicinalproduct:aspirin`
- `openfda.brand_name:"tylenol extra strength"`
- `openfda.generic_name:"acetaminophen" AND effective_time:[20200101 TO 20241231]`

If **Search** has no field colon, the Actor quotes the whole phrase and ORs it across the name fields for that mode.

Adverse events:

`(patient.drug.medicinalproduct:"aspirin" OR patient.drug.openfda.brand_name:"aspirin" OR patient.drug.openfda.generic_name:"aspirin" OR patient.drug.openfda.substance_name:"aspirin")`

Drug labels:

`(openfda.brand_name:"aspirin" OR openfda.generic_name:"aspirin" OR openfda.substance_name:"aspirin")`

Recalls use those three openFDA fields plus `product_description`.

A lowercase word such as “cold and flu” stays one phrase. The uppercase operators `AND`, `OR`, and `NOT` are only special when you write a field expression yourself. Parentheses in an expression must balance. Do not paste an API key into Search.

## How much will it cost to get openFDA drug safety records?

On the Apify Store this Actor is priced as pay per result: about **$0.003 per result** written to the dataset. A run that saves 50 rows is about $0.15 in result charges, before any platform plan discounts. Rows that are not saved are not result rows. Raising `maxResults` raises the maximum number of charged rows.

The price is not hard-coded in the Actor. Store billing uses the normal dataset-item event. An openFDA API key does not change the per-result price. It only raises the daily request cap. You can create a key from the [openFDA authentication page](https://open.fda.gov/apis/authentication/).

There is no browser time and no residential proxy in a normal run, so platform compute stays small next to Actors that render FDA or pharmacy HTML.

## Input

See the **Input** tab for every field. `storage/key_value_stores/default/INPUT.json` is a small sample (`aspirin`, adverse events, 10 rows) for a local `apify run`.

| Field | Required | Notes |
| --- | --- | --- |
| `search` | One of the search fields | Plain text or an openFDA expression. Example prefill: `aspirin` |
| `mode` | Yes | `event` (default), `label`, or `recall` |
| `brandName`, `genericName`, `substanceName` | One of the search fields | Used only when `search` is empty |
| `maxResults` | No | Integer from 1 to 500. Default 50 |
| `apiKey` | No | Secret. Never stored in the dataset or the run overview |
| `skip` | No | Advanced. Integer from 0 to 25000, for resuming a result set |

The run fails with a clear status message when the effective search is empty, `mode` is not one of the three values, or `maxResults` / `skip` / `apiKey` is not valid.

## Output

You can download the dataset as JSON, CSV, Excel, XML, or RSS. The key-value record `OUTPUT` stores the row count, the openFDA total when the API sent one, the effective search, and the endpoint. It does not contain the API key. Adverse-event runs also store the FAERS disclaimer there.

```json
{
  "mode": "event",
  "source": "openFDA",
  "safetyreportid": "10003304",
  "receivedate": "2014-03-12",
  "serious": true,
  "seriousnessdeath": true,
  "patientSex": "Female",
  "patientAge": "65 years",
  "reactions": ["Nausea", "Headache"],
  "drugs": ["ASPIRIN 81 MG", "ACETAMINOPHEN"],
  "indications": ["Pain"],
  "manufacturer": "Example Pharma",
  "brand_name": ["ASPIRIN"],
  "generic_name": ["ASPIRIN"],
  "rxcui": ["243670"],
  "reportUrl": "https://api.fda.gov/drug/event.json?search=safetyreportid%3A%2210003304%22&limit=1"
}
```

```json
{
  "mode": "label",
  "source": "openFDA",
  "set_id": "0058175f-3474-40c3-a046-6cfaec86d84b",
  "brand_name": ["ASPIRIN"],
  "generic_name": ["ASPIRIN"],
  "manufacturer_name": ["Example Labeler"],
  "indications_and_usage": "Temporarily relieves minor aches and pains.",
  "effective_time": "2024-04-16",
  "spl_url": "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=0058175f-3474-40c3-a046-6cfaec86d84b"
}
```

```json
{
  "mode": "recall",
  "source": "openFDA",
  "recall_number": "D-0170-2024",
  "status": "Terminated",
  "classification": "Class II",
  "product_description": "Low Dose ASPIRIN, 81 mg, enteric coated tablets.",
  "reason_for_recall": "Products were stored outside labeled conditions.",
  "recalling_firm": "EXAMPLE DISTRIBUTION",
  "report_date": "2024-01-03",
  "brand_name": ["ASPIRIN"],
  "generic_name": ["ASPIRIN"]
}
```

The output tab has separate tables for adverse events, labels, and recalls. A run uses one mode, so the other tables are empty.

## Tips

- Start with `maxResults` at 10 while you confirm the drug name, then raise it.
- Prefer a field expression when you need one column only, for example `patient.drug.openfda.generic_name:"ibuprofen"`.
- Use `skip` to continue a previous run. openFDA will not page past a skip of 25000; narrow the search instead of looping forever.
- The Actor requests at most 100 records at a time, waits between calls, and retries HTTP 429 and 5xx with backoff. A search openFDA cannot parse fails immediately instead of being retried.
- A run with no matches finishes successfully and writes `resultCount: 0`.
- This Actor does not count reactions, compute disproportionality, or join a drug to a reaction. Those steps need a method you choose after export.

## How this differs from an FDA HTML scraper

HTML scrapers read fda.gov, DailyMed, or pharmacy pages and break when the markup changes. This Actor uses the JSON API documented at [open.fda.gov/apis](https://open.fda.gov/apis/). Drug adverse events, labels, and recalls are three `mode` values on that API, not three website crawls. openFDA annotates records with brand, generic, substance, and RxCUI when it can. The data are U.S. government public-domain data. API use follows the [openFDA terms](https://open.fda.gov/terms/).

## FAQ, disclaimers, and support

### Is this medical advice?

No. This Actor is for **research, pharmacovigilance review, and education**. It is not a diagnosis, a treatment recommendation, or a substitute for the product label or a clinician. Do not make a medical decision from a row in this dataset.

### Do FAERS reports prove the drug caused the reaction?

No. FDA Adverse Event Reporting System reports are submitted by patients, clinicians, and manufacturers. FDA does not require a proven causal link. Reports are not verified scientific studies, they are not a count of how often an event happens, and a drug can appear often simply because many people take it. Submission of a report is not an admission that the drug caused the event. The same limit is stored on the `OUTPUT` record for every adverse-event run: a report does not prove that the drug caused the reaction, and these rows are not medical advice or incidence estimates.

### Does the Actor collect private patient data?

It reads public openFDA records. Those records can include patient sex and age as FDA published them. They are not a medical record from your system. Do not put patient names, emails, phone numbers, or medical record numbers in the search box. Personal data is protected by the GDPR in the European Union and by other laws elsewhere. Use the output only for a legitimate purpose.

### What are the API limits?

Without a key: 240 requests per minute and 1,000 requests per day per IP. With a free key: 240 requests per minute and 120,000 requests per day per key. See [openFDA authentication](https://open.fda.gov/apis/authentication/). The Actor stays under the per-minute cap and does not log the key.

### What if openFDA is busy?

The Actor retries rate-limit and server errors, then fails with a short status message if openFDA keeps failing. It does not scrape a backup HTML page. A search with no matches is a successful empty run, not an error.

### Where do I report a problem?

Use the **Issues** tab on the Actor page. For programmatic runs, use the **API** tab and the dataset items endpoint from the run.

## Local development

```bash
pip install -r requirements-dev.txt
pytest
```

Tests use fixtures and a mock HTTP client. They do not call openFDA. `apify validate-schema` checks the input, dataset, and key-value store schemas.
