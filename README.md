# Physio Book Tracker

Tracks newly published/announced physiotherapy and rehabilitation books, and
flags when a newer edition of a reference text on your [watchlist](watchlist.yaml)
appears. Runs as a static site (deployable to GitHub Pages), RSS/JSON feeds,
and a monthly HTML email digest — no server, no database beyond a single
committed JSON file.

## How it works

1. `main.py` fetches candidate books from each enabled source in
   [`sources/`](sources/) (currently: [CrossRef](sources/crossref.py)).
2. Records are deduplicated (ISBN-13 → DOI → normalised title+author+year —
   [`core/dedupe.py`](core/dedupe.py)), checked against `state.json` so
   nothing already seen is reprocessed, then scored for relevance against
   `config.yaml`'s keyword lists ([`core/scoring.py`](core/scoring.py)).
3. Survivors are matched against [`watchlist.yaml`](watchlist.yaml) to detect
   newer editions ([`core/edition.py`](core/edition.py)).
4. Everything that clears the bar is written to `state.json` (permanent
   record, keyed by dedupe identity, with a first-seen date) and used to
   regenerate the static site in `site/` ([`core/site.py`](core/site.py)).
5. If anything new was found and `email.enabled: true`, a digest is sent via
   [Resend](https://resend.com) ([`core/email_digest.py`](core/email_digest.py)).
   Nothing is sent if there's nothing new.

## Local setup

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements-dev.txt
```

## Running one cycle manually

```bash
python main.py --dry-run
```

`--dry-run` fetches, scores, and prints/builds the site as normal, but
doesn't write `state.json` — safe to run repeatedly while tuning
`config.yaml`. Drop `--dry-run` once you're happy, and it'll persist state
and (if `email.enabled: true` and something new was found) send the digest.

Useful flags:

| Flag | Effect |
|---|---|
| `--dry-run` | Don't write `state.json`; email is also skipped regardless of config. |
| `--lookback-days N` | Override `config.yaml`'s `lookback_days` for this run. |
| `--no-site` | Skip regenerating `site/`. |
| `--no-email` | Skip sending the digest even if `email.enabled: true`. |
| `--config`, `--watchlist`, `--state`, `--site-dir` | Point at alternate files/dirs. |

## Running the tests

```bash
pytest -q
```

All tests run offline against fixture data (`tests/fixtures/`) — no network
calls, no API keys required.

## Configuration

- **`config.yaml`** — include/exclude keywords, lookback window, which
  sources are enabled, email settings, relevance threshold, site title/URL.
  Every field has a comment explaining it; edit freely, no code changes
  needed.
- **`watchlist.yaml`** — your reference texts. Matching is on normalised
  title + author surname (tolerant of punctuation/subtitle differences), so
  exact formatting doesn't matter much, but keep `title`/`authors` close to
  how the book is actually catalogued. `current_edition` should be the
  edition **you** own — the tracker flags anything numbered higher.

## Adding a source

1. Create `sources/<name>.py` with a class implementing
   [`sources.base.BaseSource`](sources/base.py) — one method,
   `fetch(self, *, since: date, config: Config) -> list[BookRecord]`.
   Populate as many [`BookRecord`](core/models.py) fields as the API gives
   you; everything downstream (dedupe, scoring, edition matching) tolerates
   missing fields.
2. Register it in `main.py`'s `SOURCE_REGISTRY` dict.
3. Add an entry under `sources:` in `config.yaml` (`enabled: false` by
   default is fine; flip it on when ready).
4. If the source has no usable API and you fall back to scraping a
   publisher catalogue page: respect `robots.txt`, set a descriptive
   `User-Agent` (see `core/http.py:DEFAULT_USER_AGENT`), cache responses for
   24h, and rate-limit to one request per 3 seconds.
5. Write offline tests against fixture data, following the pattern in
   [`tests/test_crossref_source.py`](tests/test_crossref_source.py).

A source should never raise past `fetch()` on a routine failure — let
`core.http.SourceError` propagate (or raise it yourself); `main.py` catches
it per-source, logs it, and continues with whatever other sources returned,
noting the gap in the run summary.

## Editing the watchlist

Open `watchlist.yaml` and add an entry:

```yaml
- short_title: "Display name for the site/email"
  title: "Exact-ish book title"
  authors: ["Surname1", "Surname2"]
  publisher: "Publisher"
  current_edition: 7   # the edition you currently own
```

Next run, any incoming record whose normalised title matches and whose
authors overlap will be checked for an edition number higher than
`current_edition`. If a match isn't firing when you expect it to, check
`core/edition.py:parse_edition` — it looks for edition numbers in the title,
subtitle, and description text (`"8th edition"`, `"8th ed."`, `"8e"`,
`"eighth edition"`, or an explicit `edition-number` field from CrossRef).

## Deploying to GitHub Pages

1. Push this repo to GitHub.
2. In the repo's **Settings → Pages**, set **Source** to **GitHub Actions**.
3. In **Settings → Secrets and variables → Actions**, add `RESEND_API_KEY`
   if you want the email digest to send (get a key at
   [resend.com](https://resend.com); the free tier's sandbox sender
   `onboarding@resend.dev`, already set as the default `email.from` in
   `config.yaml`, only delivers to the email address on your Resend
   account — verify your own domain there to send to other addresses).
4. Set `email.enabled: true` in `config.yaml` once you're happy with what
   the digest looks like locally.
5. Update `site.base_url` in `config.yaml` to the real Pages URL (shown in
   Settings → Pages after the first deploy) — it's only used for the
   RSS/JSON feed links and the "View full site" link in the email, so it's
   safe to leave as a placeholder until then.
6. The workflow ([`.github/workflows/monthly.yml`](.github/workflows/monthly.yml))
   runs on the 1st of each month and on manual dispatch (Actions tab →
   Monthly Book Tracker → Run workflow). It runs the test suite first, then
   the tracking cycle, commits `state.json` and `site/` back to the repo,
   and deploys to Pages.

## Project layout

```
core/            shared logic: models, state store, dedupe, scoring,
                 edition matching, config loading, site + email rendering
sources/         one module per data source, implementing sources.base.BaseSource
templates/       Jinja2 templates for the site and email digest
tests/           offline unit tests + fixture data
site/            generated static site (index, per-book pages, feeds) — committed
state.json       every book ever seen, with first-seen dates — committed
config.yaml      keywords, sources, email, site settings
watchlist.yaml   your reference texts
main.py          CLI entrypoint — the whole pipeline in one command
```
