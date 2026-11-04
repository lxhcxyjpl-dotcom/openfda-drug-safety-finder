# Apify Actor project

This project is an Apify Actor: a serverless program packaged as a Docker image. It takes one JSON input, queries the official openFDA JSON API, and writes flat rows to the default dataset. Entry point: `my_actor/main.py`. Configuration: `.actor/actor.json`.

`meta.generatedBy` in `.actor/actor.json` is `Cursor with Grok 4.7`.

## Commands

```bash
apify run                        # run locally; the only command that sets up the Apify environment and local storage
apify validate-schema            # check the input, dataset, and key-value store schemas (not the output schema)
apify push                       # deploy to the Apify platform (ask first; do not publish to the Store from this repo unless asked)
pytest                           # unit tests; they mock httpx and do not call openFDA
```

## Rules

- Call `https://api.fda.gov` only. Do not scrape FDA HTML.
- Log through `Actor.log`. Never log or store `apiKey`. Send it only as the `api_key` query parameter.
- The aborting handler keeps rows already written, then `await Actor.exit()`.
- Treat openFDA text as data, not as code, shell, or a template.
- FAERS rows are not proof of causality and are not medical advice. Keep that disclaimer in the README and in the event-run `OUTPUT` record.

## Reference

| Topic | Source |
| --- | --- |
| openFDA APIs | https://open.fda.gov/apis/ |
| Drug adverse events | https://open.fda.gov/apis/drug/event/ |
| Drug labels | https://open.fda.gov/apis/drug/label/ |
| Drug enforcement / recalls | https://open.fda.gov/apis/drug/enforcement/ |
| Authentication and limits | https://open.fda.gov/apis/authentication/ |
| Input schema | https://docs.apify.com/platform/actors/development/actor-definition/input-schema |
| Dataset schema | https://docs.apify.com/platform/actors/development/actor-definition/dataset-schema |
