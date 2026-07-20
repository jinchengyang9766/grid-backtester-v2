# Grid Backtester V2 — frontend

Next.js (App Router) + React + TypeScript + Tailwind CSS. Authentication,
dataset management, backtest configuration and execution, history, the
persisted-result dashboard, and export downloads are implemented. Optimization
is **not** implemented yet.

## Requirements

- Node.js 20.9+ (Next.js 16 minimum)
- A running backend (see [`../backend/README.md`](../backend/README.md))

## Setup

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
```

`.env.local` is git-ignored. It holds one variable:

```text
BACKEND_ORIGIN=http://127.0.0.1:8000
```

`BACKEND_ORIGIN` is **server-only** — it is read inside the proxy route
handler, which runs on the Next.js server. It deliberately has no
`NEXT_PUBLIC_` prefix, because that would inline the backend origin into the
browser bundle. The browser must only ever talk to the Next.js origin.

## Running locally

Start the backend first, from the repository's `backend/` directory:

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then the frontend:

```powershell
cd frontend
npm run dev          # http://localhost:3000
```

For a production build:

```powershell
npm run build
npm run start
```

## Same-origin API proxy

The browser calls relative `/api/...` URLs on the Next.js origin. The catch-all
route handler at `app/api/[...path]/route.ts` forwards each request to
`BACKEND_ORIGIN`:

```text
browser  /api/auth/login  ->  Next.js  ->  BACKEND_ORIGIN/api/auth/login
```

This is SPEC Section 24.5's preferred same-origin architecture. Because every
browser request is same-origin by construction, the `SameSite=Lax` cookie
always attaches, and no credentialed CORS configuration is needed.

The proxy preserves the method, query string, request body, content type, the
`Cookie` request header, and every `Set-Cookie` response header, along with the
response status and content type. Bodies are streamed in both directions, so
multipart uploads keep their exact boundary and future binary CSV/PDF exports
are never decoded to text. It forwards only under the backend's `/api`
namespace — the prefix is a constant in the handler, so it cannot be turned
into a general-purpose open proxy — and it never reveals the backend origin to
the browser.

## Authentication design

The backend issues a **`HttpOnly` cookie** (`SameSite=Lax`, `Path=/api`,
`Secure` in production). Consequently:

- **No JavaScript ever reads, stores, or decodes the access token.** It is not
  in `localStorage`, `sessionStorage`, `document.cookie`, or any response body,
  and no `Authorization: Bearer` header is ever constructed. The browser
  attaches the cookie automatically; a token mirrored into JavaScript would
  only be a second copy able to disagree with the real session, and would be
  readable by any XSS.
- **The cookie is the single source of truth.** `lib/auth/auth-context.tsx`
  calls `GET /api/auth/me` once on mount and mirrors the answer. It never
  guesses a session from cached state.
- **A 401 from `/api/auth/me` is not an error** — it is the normal signed-out
  state. A network failure or 5xx is a distinct `error` state with a retry
  action, so a backend outage is never silently shown as "signed out".
- **Registration does not sign you in.** `POST /api/auth/register` creates the
  account; the user is then directed to sign in.
- **Logout** posts to `/api/auth/logout` (204) and clears the mirrored state.
  There is no JavaScript token to clear.

Guards render a loading state until `/api/auth/me` resolves, so a redirect can
never fire while the session is still unknown.

## Pages

| Route | Purpose | Auth |
|---|---|---|
| `/` | Public landing page (SPEC Section 27) | No |
| `/login` | Sign-in form; honours `?next=<path>` | No — signed-in visitors go to `/history` |
| `/register` | Registration form | No — signed-in visitors go to `/history` |
| `/history` | Backtest history — the authenticated landing | Yes |
| `/history/{id}` | Full persisted result dashboard | Yes |
| `/history/compare?ids=…` | Side-by-side stored metrics | Yes |
| `/datasets` | Dataset list, detail, and delete | Yes |
| `/backtest/new` | Upload wizard, strategy, and run | Yes |
| `/app` | Legacy alias; redirects to `/history` | Yes |

Unauthenticated access to a protected route redirects to
`/login?next=<encoded path>`, and signing in returns the user there. Only
same-origin relative paths are accepted as a `next` target, so the parameter
cannot be used as an open redirect. With no explicit target, signing in lands
on `/history` (SPEC Section 27).

`/app` was the temporary home before `/history` existed. It is kept only so
old links keep working and immediately replaces itself with `/history`.

## Datasets

### Uploading (`/backtest/new`)

Accepted uploads are **`.xls`** and **`.csv`**. A `.xls` file must be a
**TongdaXin text export** — tab-separated text, *not* a binary Excel workbook;
the backend rejects real OLE2/ZIP spreadsheets with
`400 UNSUPPORTED_FILE_TYPE`.

The wizard implements SPEC Section 28 end to end:

```text
UPLOAD → DETECTING → MAPPING → CLEANING_REVIEW → PREVIEW → DATASET_SAVED
       → STRATEGY_CONFIG → RUNNING → DONE
```

- **Upload** posts the file to `/api/datasets/preview` as `multipart/form-data`
  through the same-origin proxy, which streams the body so the multipart
  boundary survives untouched.
- **Mapping** shows one selector per canonical field (date, open, high, low,
  close, volume), initialised from the mapping the server reported. Date and
  Close are required; Open/High/Low must be mapped together or all cleared for
  a close-only dataset; one source column cannot feed two fields. Selectable
  columns come only from headers the server actually returned.
- **Cleaning review** renders the server's own summary, rejected rows, and
  duplicate dates — including zero counts. Nothing is recomputed in the
  browser. Duplicate dates keep the row appearing **last** in the file.
- **Preview** shows the cleaned rows the server returned. Decimal values stay
  strings and nulls render as a dash. Large datasets return a bounded sample
  (first and last rows), shown separately from the full saved row count.
- **Save** posts exactly `{ name, preview_token }` to `/api/datasets` and then
  replaces the URL with `/backtest/new?dataset_id={id}`.

### Mapping and token binding

A `preview_token` is bound to **one file and one mapping** (SPEC Section 25.2).
The wizard enforces that:

- Advancing with an **unchanged** mapping reuses the held token — no second
  request.
- Any **mapping edit** re-posts the original file with the complete
  `manual_mapping` (cleared fields sent as explicit `null`) and adopts the new
  response and token together before continuing.
- A **failed** re-preview keeps you on the mapping step; it never advances on a
  token whose mapping differs from what is on screen.
- **Selecting a different file** aborts any in-flight preview and clears the
  token, mapping, cleaning result, and suggested name.
- A save that returns `404 PREVIEW_TOKEN_NOT_FOUND` (expired or already used)
  offers **Refresh preview** rather than silently retrying with a dead token.

The selected `File` lives only in React state — never `localStorage`,
`sessionStorage`, IndexedDB, or Cache Storage — because a re-mapping needs the
original bytes again. The preview token is likewise memory-only: it is never
rendered, logged, written to a data attribute, or placed in a URL. Only
`dataset_id` ever travels in the query string.

### Managing datasets (`/datasets`)

Lists every owned dataset with its name, security name/code, source type,
original filename, data mode, date range, row count, and creation time.

- **View details** opens an accessible dialog with the stored `column_mapping`
  as a canonical-field → source-column table and a readable `cleaning_summary`.
  Price bars are never requested or shown.
- **Use for backtest** links to `/backtest/new?dataset_id={id}`, which loads the
  owned dataset and shows the saved handoff.
- **Delete** requires explicit confirmation (no name typing) and warns that the
  saved price rows go with it and that deletion is irreversible. The row is
  removed only after the server confirms `204` — never optimistically. A
  `409 DATASET_IN_USE` keeps the dataset and explains that the backtests using
  it must be deleted first; the frontend never cascades or calls a backtest
  endpoint.

There is no rename or edit control, because the backend exposes no dataset
update endpoint.

## Strategy configuration and execution

From `DATASET_SAVED` onward only the dataset **id** matters — the original file
and the preview token are no longer needed, so `/backtest/new?dataset_id={id}`
resumes cleanly after a reload and `/datasets → Use for backtest` enters the
same flow.

### Sections

The form covers every field of the backend's `BacktestConfigurationInput`,
grouped as: **Portfolio** (initial cash/shares, lot size, trade lots),
**Grid geometry** (optional baseline, A distance, C distance, grid step),
**Price execution** (tick size, intraday path mode), **Fees** (independent buy
and sell commissions, each with rate/minimum/fixed and its own enable flag),
**Slippage** (shared or separate per side), and **Risk assumptions** (annual
risk-free rate). A review section restates everything from form state before
the run; it never projects a return, trade count, or equity.

Starting values come from SPEC Section 25.3's illustrative request — the only
complete configuration the specification writes down. They are **starting
values, not frozen defaults** (the schema only defaults `baseline`,
`tick_size.value`, and `ohlc_path_mode` to null), and deliberately not the
Task-12 real-file smoke configuration, which is tuned to one security. Reset
restores them without changing the selected dataset.

### Decimal handling

Every financial value stays a **string** from keystroke to request body. It is
never passed through `Number`, `parseFloat`, unary `+`, or `toFixed`: binary
floating point cannot represent most decimal fractions exactly, so one
conversion would silently alter a price or rate before the backend's `Decimal`
parser saw it. Comparison (for example "C must exceed A") uses BigInt-scaled
integers, which is exact at any magnitude and treats `1`, `1.0`, and `1.000` as
equal. Percentages shown next to a rate are produced by shifting digits, not by
multiplying. Even integer counts travel as digit strings — Pydantic coerces
them losslessly, whereas a JavaScript number would cap at 2^53. Nothing is
rounded client-side; the backend remains the final parser and the final
validation authority.

### Running

`POST /api/backtests` executes **synchronously**, so `RUNNING` is a real state:
the form is replaced by a textual status while the browser waits on the single
response. There is no progress percentage (the server sends none) and no
Cancel (the backend supports none), and the request is never retried.

### COMPLETED versus FAILED

A `201` with `status: "FAILED"` is a **successfully created run**, not an HTTP
failure — the row exists and is saved. It shows the run id, generated name,
status, and the persisted `error_message`, with no fabricated metrics, and
offers to edit the configuration with the submitted values still in place.

A `201` with `status: "COMPLETED"` shows the run id, name, timestamps, and only
those headline figures already present in the response. No result series is
fetched and nothing is charted.

Either way the URL becomes `/backtest/new?backtest_id={id}` — only the id, never
the configuration or any metric. Reloading that URL loads
`GET /api/backtests/{id}` (with no `include`, so no trade or equity series),
confirms ownership through the backend's indistinguishable 404, and renders the
same handoff **without re-running the engine**.

A non-2xx response is different: the flow stays on `STRATEGY_CONFIG` with every
entered value preserved, shows the safe backend message, and maps
`details.field` onto the offending input. Grid-related codes such as
`INVALID_ZONE_CONFIG` and `GRID_TOO_DENSE` also appear beside the grid section.
A `DATASET_NOT_FOUND` explains the dataset may have been deleted and links to
`/datasets` without revealing whether a foreign dataset exists.

## History and results

`/history` is the authenticated landing (SPEC Section 27). It lists every owned
run newest-first, exactly in the order the backend returns.

- **Filters** — name search, dataset, and status, using the backend's own
  `search` / `dataset_id` / `status` parameters. Typing is debounced locally and
  superseded requests are aborted; nothing is retried. Filters and page live in
  the query string, so browser back/forward restores them, and only filter
  values and identifiers ever appear there.
- **Pagination** — `limit`/`offset`, with the total count shown and the controls
  disabled at each boundary. Changing a filter resets to page one.
- **Per-run actions** — view, rename, rerun, duplicate, delete, and select for
  comparison. They stay available on FAILED runs too, since those are valid
  history entries.

### Result dashboard (`/history/{id}`)

The detail is requested once with `include=trades,zone_events,daily_equity,event_equity`
and presented in tabs: overview, charts, benchmarks, costs & zones,
configuration, and the four result tables.

Every figure is read from the stored `result_metrics` document — nothing is
recomputed, averaged, or derived from the series, because a second calculation
in the browser could disagree with what the engine actually produced. Decimal
strings are shown exactly as stored; a ratio additionally gets a short
percentage hint, produced by shifting digits and marked `≈` when truncated so
it is never mistaken for the value. Missing metrics render as a dash and are
never inferred.

A **FAILED** run shows its persisted `error_message`, states that no metrics
were stored, and fabricates no charts. **PENDING**/**RUNNING** runs report their
status without inventing progress; nothing is polled.

### Charts

Three SVG charts are drawn with local components — no charting dependency:

- **Equity** — `DailyEquity.equity` with both persisted benchmark point series
  from `result_metrics.benchmark1/2.points[]`, on the same absolute axis. No
  rebasing, normalization, or smoothing.
- **Drawdown** — `DailyEquity.drawdown` read directly, with a zero reference
  line and negatives preserved. Running peaks are never recalculated.
- **Price and grid** — `DailyEquity.close` with the persisted baseline, A/C
  boundaries, and only those grid levels actually stored. `price_bars` is never
  requested and no level is synthesized; when none were stored the chart says so.

`lib/backtests/chart-data.ts` is the **only** module that converts a decimal
string to a JavaScript number, and the result is used solely for SVG
coordinates. Labels, tooltips, and every table cell keep the original strings.
Empty, single-point, flat, and all-zero series all render safely.

### Rename, delete, rerun, duplicate, compare

- **Rename** sends only `{ name }`; any other field would be a deliberate
  `422 IMMUTABLE_FIELD`.
- **Delete** removes the run and its stored result rows after a `204` — never
  optimistically. The dataset and its price data are untouched.
- **Rerun** re-executes the stored configuration against the dataset's current
  bars, creating a new run and leaving the source unchanged. Both COMPLETED and
  FAILED results open the new run's detail page.
- **Duplicate** opens the strategy form prefilled from the source run's exact
  configuration and submits the whole edited document as
  `configuration_overrides`; the backend validates the merged result through the
  same full-configuration model. The source dataset is fixed and the source run
  is never modified.
- **Compare** posts the selected ids to `/api/backtests/compare` and renders the
  response verbatim, one column per run in the requested order. No ranking,
  winner, difference, or percentage change is calculated. A missing or foreign
  id produces the all-or-nothing 404 without revealing which id failed.
  Selection is limited to the visible page and is cleared, with an accessible
  notice, when filters or page change.

## Exports

The result dashboard offers all four backend exports:

| Control | Endpoint | Downloaded as |
|---|---|---|
| Download trades CSV | `/api/backtests/{id}/exports/trades.csv` | `backtest-{id}-trades.csv` |
| Download equity CSV | `/api/backtests/{id}/exports/equity.csv` | `backtest-{id}-equity.csv` |
| Download complete result JSON | `/api/backtests/{id}/exports/result.json` | `backtest-{id}-result.json` |
| Download PDF report | `/api/backtests/{id}/exports/report.pdf` | `backtest-{id}-report.pdf` |

Each control is a plain **`<a download>` link**, not a button. Activating it is
an ordinary browser navigation: the browser streams the response straight to
disk using the backend's `Content-Disposition` filename. No JavaScript is
involved — no `fetch`, no `Blob`, no `URL.createObjectURL`, no `FileReader`.
That matters for more than simplicity: buffering a multi-megabyte export into a
JavaScript string would decode bytes the browser should never interpret, cap the
file at available memory, and give the download a browser-invented name instead
of the server's. Nothing is parsed, re-serialized, or rendered client-side —
in particular there is **no in-browser PDF viewer**, so the report the user
opens is byte-for-byte the file the backend produced.

The links are rendered whatever the run's status is; a FAILED or PENDING run
carries a note that the file will contain no result data rather than hiding the
control, so the backend stays the single authority on what an export contains.
Ownership is enforced only server-side, by the same indistinguishable
`404 BACKTEST_NOT_FOUND` used everywhere else. Links appear only after the
detail request has confirmed the run loaded.

## Accessibility and responsiveness

- Verified at **390×844**, **768×1024**, and **1440×900**. No page scrolls
  horizontally at any of those widths: wide content (result tables, charts)
  scrolls inside its own container instead of pushing the document sideways.
- Every page has one `main` landmark and exactly one `h1`; authenticated pages
  add a `banner` header and a labelled navigation landmark.
- A **Skip to main content** link is the first focusable element on
  authenticated pages, visible once focused.
- Dialogs are `aria-modal`, labelled by their heading, dismissed with `Escape`,
  and return focus to the control that opened them.
- Result tabs follow the ARIA tabs pattern, including `Arrow`/`Home`/`End`.
- Charts are exposed as `img` with a `<title>` and a `<desc>`, and every figure
  they show is also available as text in the result tables.
- State is never conveyed by colour alone — the current nav item, run statuses,
  and validation errors all say so in text. Errors are announced through live
  regions.

## Verification

```powershell
npm run lint         # ESLint
npm run typecheck    # tsc --noEmit (TypeScript strict mode)
npm test -- --run    # Vitest + React Testing Library (jsdom)
npm run build        # production build
npm run test:e2e     # Playwright (Chromium) — see below
```

### End-to-end suite

```powershell
npm run build        # test:e2e serves the production build
npx playwright install chromium
npm run test:e2e            # headless
npm run test:e2e:headed     # watch it run
```

`e2e/global-setup.ts` starts **both** servers itself, so nothing needs to be
running first. Each suite run gets:

- its own **SQLite database in a temp directory outside the repository**, created
  fresh and deleted afterwards — pass or fail;
- a **randomly generated auth secret**, so no secret is hard-coded in
  `playwright.config.ts` or committed anywhere;
- dedicated ports (backend `8123`, frontend `3123`) that do not collide with a
  developer's `8000`/`3000`.

The price CSV is **generated at runtime** by `e2e/fixtures/data.ts`, so no
financial dataset is checked in. Downloaded exports are read from Playwright's
temp directory, asserted on, and deleted immediately; `test-results/`,
`playwright-report/`, traces, videos, and screenshots are git-ignored.

The suite drives real user flows — registration and sign-in, the full dataset
wizard including a mapping edit and cleaning review, strategy configuration and
execution, history and filters, the result dashboard, rename/rerun/duplicate/
delete/compare, all four downloads, and the responsive and accessibility sweeps
above. Every flow also asserts the browser console is free of errors, that no
token is reachable from JavaScript, and that no unexpected server failures
occurred.

## Structure

```text
frontend/
  app/
    layout.tsx            root layout, mounts the auth provider
    page.tsx              public landing page
    login/page.tsx        /login
    register/page.tsx     /register
    app/                  authenticated shell (layout guards, page renders)
    api/[...path]/route.ts  same-origin backend proxy
  components/
    auth/                 login/register forms, logout button, route guards
    layout/               app header and navigation
    ui/                   button, input, form field, alert, loading state
    results/              result dashboard, tabs, tables, export controls
    history/              history list, filters, run actions, comparison
  lib/
    api/                  fetch client, typed error model, auth endpoints
    auth/                 authentication state provider and hook
    backtests/            decimal-string arithmetic, metrics, chart data
    routing/              safe `?next=` handling
  tests/                  Vitest suites
  e2e/                    Playwright suites
    fixtures/             server lifecycle, auth helpers, generated data
  playwright.config.ts
```

## Not implemented yet

Optimization (the backend exposes no optimization endpoint yet), and any
deployment or Docker setup. In-browser PDF rendering is deliberately absent —
see [Exports](#exports).
