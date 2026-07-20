# Grid Backtester V2 — frontend

Next.js (App Router) + React + TypeScript + Tailwind CSS. This slice is the
application foundation and the complete authentication experience; dataset,
backtest, chart, export, and optimization pages are **not** implemented yet.

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
| `/login` | Sign-in form; honours `?next=<path>` | No — signed-in visitors go to `/app` |
| `/register` | Registration form | No — signed-in visitors go to `/app` |
| `/app` | Authenticated workspace shell | Yes |
| `/datasets` | Dataset list, detail, and delete | Yes |
| `/backtest/new` | Dataset upload wizard | Yes |

Unauthenticated access to `/app` redirects to `/login?next=%2Fapp`, and signing
in returns the user there. Only same-origin relative paths are accepted as a
`next` target, so the parameter cannot be used as an open redirect.

`/app` is a **foundation placeholder**. It shows real session information (the
signed-in email) and a navigation outline whose Datasets / New Backtest /
Backtest History entries are rendered as disabled labels marked "Not available
yet" — never as links to routes that do not exist. No dataset counts, backtest
results, charts, or sample figures are displayed.

> `/app` is a temporary home. SPEC Section 27 places the authenticated landing
> at `/history`; that route arrives with the backtest history page, at which
> point the redirect targets move there.

## Datasets

### Uploading (`/backtest/new`)

Accepted uploads are **`.xls`** and **`.csv`**. A `.xls` file must be a
**TongdaXin text export** — tab-separated text, *not* a binary Excel workbook;
the backend rejects real OLE2/ZIP spreadsheets with
`400 UNSUPPORTED_FILE_TYPE`.

The wizard implements SPEC Section 28 up to `DATASET_SAVED`:

```text
UPLOAD → DETECTING → MAPPING → CLEANING_REVIEW → PREVIEW → DATASET_SAVED
```

`STRATEGY_CONFIG`, `RUNNING`, and `DONE` are **not** implemented — the saved
state ends with an inert "Configure strategy" control marked *Coming next*.

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

## Verification

```powershell
npm run lint         # ESLint
npm run typecheck    # tsc --noEmit (TypeScript strict mode)
npm test -- --run    # Vitest + React Testing Library (jsdom)
npm run build        # production build
```

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
  lib/
    api/                  fetch client, typed error model, auth endpoints
    auth/                 authentication state provider and hook
    routing/              safe `?next=` handling
  tests/                  Vitest suites
```

## Not implemented yet

Strategy configuration and backtest execution (the wizard stops at
`DATASET_SAVED`), backtest history, the result dashboard, charts, comparison,
export download buttons, optimization, and in-browser PDF rendering. There is
no end-to-end browser suite, and no deployment or Docker setup.
