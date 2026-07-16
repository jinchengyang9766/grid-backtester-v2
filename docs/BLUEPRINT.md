# Grid Backtester V2 — Product & Architecture Blueprint

**Project name:** `grid-backtester-v2`  
**Blueprint status:** Approved high-level design  
**Purpose of this file:** This is the source blueprint from which Claude should create a detailed `docs/SPEC.md`.  
**Important:** Do not write application code until the detailed specification has been generated, reviewed, and approved.

---

## 1. Product Vision

`grid-backtester-v2` is a portfolio-grade, full-stack grid-trading backtesting platform.

The project must demonstrate:

- A tested Python backtesting engine
- A FastAPI backend
- A Next.js + React + TypeScript frontend
- PostgreSQL persistence
- User registration and login
- Uploaded market-data parsing and cleaning
- Interactive charts and downloadable reports
- Parameter optimization through a background worker
- Professional software-engineering practices: Git, tests, typing, migrations, documentation, and later Docker

The main purpose is to create a strong GitHub and résumé project for Software Engineering internships. It may later become a publicly deployed web application.

---

## 2. Product Principles

1. **Correctness before UI polish.**
2. **The backtesting engine must be independent of FastAPI, PostgreSQL, and the frontend.**
3. **Every trading rule must be deterministic and testable.**
4. **No hidden assumptions.** OHLC path assumptions, fees, slippage, data cleaning, and benchmark rules must be shown to the user.
5. **No production trading.** This is a research and educational backtester, not a live-trading system.
6. **No short selling and no partial fills.**
7. **Claude works in small, reviewable tasks.**
8. **Each completed task must include tests, explanation, documentation updates, a Git commit, and a push.**

---

## 3. Scope

### 3.1 Final V2 Scope

The final project includes:

1. Upload market-data files
2. Parse TongdaXin text-export `.xls`
3. Parse regular `.csv`
4. Automatic and manual column mapping
5. Data cleaning with bad-row reporting
6. OHLCV mode
7. Close-only fallback mode
8. A-zone and C-zone configuration
9. Grid backtesting
10. Commission and slippage
11. Portfolio and risk metrics
12. Interactive charts
13. Trade log
14. CSV, JSON, and PDF exports
15. Two Buy-and-Hold benchmarks
16. User accounts
17. PostgreSQL history
18. Dataset reuse
19. Backtest comparison
20. Parameter optimization
21. Training/testing split
22. Background optimization worker
23. Automated tests from unit to end-to-end
24. Docker after the main application works
25. Public deployment after local completion

### 3.2 Explicitly Deferred

These are not part of the first completed V2 release:

- Live brokerage integration
- Real-time trading
- Automatic online stock-price download
- Stop loss
- Take profit
- Dynamic or moving baseline
- Moving grid
- B trading zone
- Intraday/minute/hourly data
- Volume-based liquidity constraints
- Market-impact model
- Multi-currency formatting
- Raw uploaded-file storage
- Automatic security-type detection

---

## 4. Technology Stack

### 4.1 Monorepo

Use one GitHub repository:

```text
grid-backtester-v2/
├── frontend/
├── backend/
├── docs/
├── docker-compose.yml
├── .gitignore
└── README.md
```

### 4.2 Frontend

- Next.js with App Router
- React
- TypeScript
- Tailwind CSS
- A reusable component library such as shadcn/ui
- React Hook Form for forms
- Zod for frontend validation
- TanStack Query for backend requests and server-state caching
- Plotly.js or an equivalent library capable of:
  - Candlestick charts
  - Line charts
  - Buy/sell markers
  - Heatmaps
  - Drawdown charts
- `next-themes` or equivalent for light/dark mode

### 4.3 Backend

- Python
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- pandas
- NumPy where useful
- `Decimal` for money, prices, fee calculations, grid stepping, and tick-size rounding
- JWT-based authentication
- Password hashing with Argon2id
- Secure HttpOnly cookies for authentication tokens

### 4.4 Background Jobs

Final architecture:

- Celery worker
- Redis broker/result backend
- PostgreSQL for durable optimization metadata and result summaries

Development order:

1. Implement a synchronous optimization engine first.
2. Test it independently.
3. Wrap it in Celery only after the optimization calculations are correct.

### 4.5 Testing

- `pytest` for Python unit tests
- FastAPI API/integration tests
- Frontend component tests
- Playwright end-to-end tests

### 4.6 Docker

Do not begin with Docker.

Add Docker after the main local application works:

- Frontend container
- FastAPI container
- Celery worker container
- PostgreSQL container
- Redis container

---

## 5. Core Domain Concepts

### 5.1 Dataset

A `Dataset` is cleaned and reusable market-price data.

A dataset contains:

- User owner
- Dataset name
- Original filename
- Security name, when detected
- Security code, when detected
- Data mode: `OHLCV` or `CLOSE_ONLY`
- Start date
- End date
- Row count
- Column mapping
- Data-cleaning summary
- Cleaned price bars

The raw uploaded file is not stored after parsing.

Multiple backtest runs may use the same dataset.

### 5.2 Baseline

- Default baseline: first row's `Close`
- User may override it
- Baseline is fixed throughout one backtest
- Baseline defines the center of A and C boundaries
- Baseline is also a normal grid level
- Changing the baseline does not invent a price movement before the dataset begins

### 5.3 A Zone

The A zone is the active trading region:

```text
A Lower <= price <= A Upper
```

Within A:

- Grid crossings can generate trades
- Buy on downward crossings
- Sell on upward crossings

A boundaries are symmetric around baseline.

A distance supports:

- Percent mode
- Fixed-value mode

### 5.4 C Zone and Outside-C Risk Area

The system has A and C boundaries:

```text
C Upper
A Upper
Baseline
A Lower
C Lower
```

Definitions:

- **A zone:** between A Lower and A Upper; trading enabled
- **C zone:** outside A but still between C Lower and C Upper; trading paused
- **Outside C:** price beyond C Upper or C Lower; no trading, but record a risk event

C boundaries are symmetric around baseline.

C distance supports:

- Percent mode
- Fixed-value mode

Validation:

```text
C Distance > A Distance > 0
```

### 5.5 Grid Levels

- Grid levels are globally anchored to baseline
- Baseline itself is a grid level
- Grid step supports Percent or Fixed mode
- Grid levels are generated only inside the A zone
- If A distance is not exactly divisible by grid step:
  - Keep only valid grid levels inside A
  - Do not force A boundaries to become grid levels
  - Do not modify the requested grid step

### 5.6 Market Cursor vs Trade Anchor

The engine must maintain two separate concepts.

#### Market Cursor

`market_cursor` represents the current position along the real or assumed price path.

It is used for:

- Determining actual movement direction
- Detecting entry into and exit from A/C
- Processing each OHLC segment
- Recording zone events

#### Trade Anchor

`trade_anchor` represents the last successfully executed grid price.

It is used for:

- Determining which grid level is eligible next
- Preventing the same completed grid step from immediately retriggering
- Preserving strategy state through C-zone pauses

Rules:

- On a successful trade, update `trade_anchor` to that grid level
- On a skipped trade, do not update it
- Entering C does not change it
- Returning to A does not change it
- C-zone price movement does not change it
- Missed trades in C are never backfilled
- If no successful trade has occurred, the initial trade anchor is:
  - First row `Open` in OHLCV mode
  - First row `Close` in Close-only mode

---

## 6. Input Data

### 6.1 Supported File Types

#### TongdaXin Export

Support TongdaXin files that:

- Use an `.xls` extension
- Are actually tab-separated text, not a real Excel workbook
- Commonly use GBK or GB18030 encoding
- May contain:
  - A security-name/title line
  - Blank lines
  - Chinese column names
  - Extra indicators such as MA, VOL, and MACD
  - A trailing source/footer line

The provided sample contains fields including:

- 时间
- 开盘
- 最高
- 最低
- 收盘
- 成交量

Only required market-data fields should be extracted.

#### Regular CSV

Support normal `.csv` files.

### 6.2 Automatic Column Recognition

Automatically match common English and Chinese names:

```text
Date:   Date / 日期 / 时间
Open:   Open / 开盘
High:   High / 最高
Low:    Low / 最低
Close:  Close / 收盘
Volume: Volume / 成交量
```

The user must be allowed to correct the mapping manually before saving the dataset.

### 6.3 Data Modes

#### OHLCV Mode

Requires:

- Date
- Open
- High
- Low
- Close

Volume is optional.

#### Close-only Mode

Requires:

- Date
- Close

Behavior:

- First row initializes the engine
- From the second row onward, process:
  - previous Close → current Close
- OHLC-path selection is disabled
- The first row does not invent a baseline-to-close movement

### 6.4 Validation and Cleaning

The upload wizard must:

1. Detect format and encoding
2. Parse candidate rows
3. Detect and map columns
4. Convert dates and numbers
5. Detect invalid rows
6. Display bad rows and reasons
7. Remove invalid rows
8. Sort by date ascending
9. Detect duplicate dates
10. Display a cleaning summary
11. Show a preview
12. Require user confirmation before saving

Bad or missing required values are removed after being shown.

The detailed SPEC must define the duplicate-date policy explicitly. Recommended default:

- Show duplicate rows as data issues
- Keep the last valid row for each date only after user confirmation

---

## 7. OHLC Path Processing

In OHLCV mode, the user selects one of three deterministic daily path assumptions.

### Option 1

```text
Open → High → Low → Close
```

### Option 2

```text
Open → Low → High → Close
```

### Automatic

If:

```text
Close >= Open
```

use:

```text
Open → Low → High → Close
```

Otherwise use:

```text
Open → High → Low → Close
```

Rules:

- The first day is processed using its full selected OHLC path
- The initial `market_cursor` and `trade_anchor` start at first-day Open
- Each adjacent pair is processed as one path segment
- The same day may contain buys and sells
- The same grid may be crossed again after price reverses
- Multiple crossed grids in one segment are processed in price order

---

## 8. Trading Rules

### 8.1 Direction

Use the actual segment direction determined by `market_cursor`.

- Downward segment: eligible grid crossings are buys
- Upward segment: eligible grid crossings are sells

### 8.2 Crossing Inclusivity

Reaching a grid line counts as crossing.

Recommended formal rules:

For a downward segment:

```text
segment_end <= grid_level < segment_start
```

For an upward segment:

```text
segment_start < grid_level <= segment_end
```

The detailed SPEC must additionally state how eligible levels are filtered relative to `trade_anchor`.

Required behavior:

- Downward movement may only attempt grid levels below `trade_anchor`
- Upward movement may only attempt grid levels above `trade_anchor`
- `trade_anchor` itself does not retrigger
- After each successful trade, continue from the new anchor
- A failed order does not prevent later crossed levels in the same segment from being attempted

### 8.3 Multi-grid Crossing

Example:

```text
Trade anchor: 1.00
Path segment: 1.00 → 0.80
Grid step: 0.05
```

Attempt in order:

```text
0.95 BUY
0.90 BUY
0.85 BUY
0.80 BUY
```

Every crossed level is attempted and logged.

### 8.4 Repeated Crossings

Example:

```text
1.00 → 0.95: BUY
0.95 → 1.00: SELL
1.00 → 0.95: BUY again
```

Repeated crossings are allowed.

### 8.5 A-to-C Transition

When a segment leaves A:

1. Process all valid A-zone grid crossings up to the A boundary
2. Enter C
3. Record `ENTER_C_ZONE`
4. Pause trading for the C portion of the path

### 8.6 C-to-A Transition

When a segment returns from C to A:

1. Record `EXIT_C_ZONE`
2. Preserve `trade_anchor` exactly
3. Do not execute a trade merely because of re-entry
4. Do not backfill any levels missed while in C
5. Resume processing the remaining in-A portion of the same segment
6. Only trade when the price truly reaches the next eligible grid relative to the preserved anchor

Example:

```text
A Lower = 0.90
Last successful trade anchor = 0.95
Price: 0.95 → 0.85 → 0.92
```

After returning to 0.92:

```text
trade_anchor remains 0.95
```

No trade occurs at re-entry.

If price later rises through 1.00, the next eligible sell is 1.00.

### 8.7 Outside-C Events

When crossing C boundaries, record:

- `OUTSIDE_C_BOUNDARY`
- `RETURN_INSIDE_C_BOUNDARY`

No forced liquidation occurs.

### 8.8 C-zone Logging

Do not create virtual skipped trades in C.

Record only meaningful zone/risk events:

- `ENTER_C_ZONE`
- `EXIT_C_ZONE`
- `OUTSIDE_C_BOUNDARY`
- `RETURN_INSIDE_C_BOUNDARY`

---

## 9. Order and Portfolio Rules

### 9.1 Initial Portfolio

User configures:

- Initial cash
- Initial shares

Initial shares:

- Must be a non-negative integer
- Do not have to be a multiple of lot size

Initial equity is marked using the first available market price, with the exact convention to be written in SPEC.

Recommended:

- OHLCV: first Open
- Close-only: first Close

### 9.2 Lot Size

- User configures `lot_size`
- Default: 100 shares
- User configures `trade_lots`
- Actual order quantity:

```text
order_shares = trade_lots × lot_size
```

All new orders therefore follow lot size.

### 9.3 Constraints

- No short selling
- No negative cash
- No partial fills
- A buy that cannot be fully afforded is skipped
- A sell with insufficient shares is skipped
- Every skipped order is logged with a reason
- All crossed grid levels are still attempted even after a failure
- Anchor updates only after successful execution

---

## 10. Execution Price, Slippage, Tick Size, and Fees

### 10.1 Slippage

Support:

- Percent mode
- Fixed-value mode

Default:

- One shared slippage setting

Advanced settings:

- Separate buy slippage
- Separate sell slippage

Rules:

```text
Buy execution price  = Grid Price + Buy Slippage
Sell execution price = Grid Price - Sell Slippage
```

Percent mode calculates slippage from grid price.

Track total slippage cost separately.

### 10.2 Tick Size

Tick size is optional and disabled by default.

When enabled:

- Grid prices and execution prices must be normalized to valid ticks
- Use `Decimal`
- Recommended deterministic default: nearest tick with `ROUND_HALF_UP`
- The exact order of operations between grid generation, slippage, and tick rounding must be explicitly written in SPEC and unit-tested

### 10.3 Commission

Buy and sell fee settings are separate.

Each side may enable any combination of:

- Percentage rate
- Minimum commission
- Fixed fee

Formula:

```text
percentage_component = notional × rate

if minimum commission is enabled:
    percentage_component =
        max(percentage_component, minimum_commission)

total_commission =
    percentage_component + fixed_fee
```

If the percentage component is disabled, it contributes zero.

Fee effects:

- Buy:
  - Cash decreases by notional + commission
- Sell:
  - Cash increases by notional - commission

---

## 11. Buy-and-Hold Benchmarks

Provide two benchmarks.

### Benchmark 1: Same Initial Portfolio, No Trades

- Keep the same initial cash
- Keep the same initial shares
- Never trade
- Mark equity over time

### Benchmark 2: Invest Available Cash on Day One

- Start with the same initial cash and initial shares
- Use all affordable cash on the first day
- Buy at first-day Open
- Apply buy slippage
- Apply buy commission
- Respect lot size
- Hold all resulting shares to the end

Show strategy and both benchmarks together where useful.

---

## 12. Metrics

Required metrics:

- Initial Equity
- Final Equity
- Net Profit
- Total Return
- Annualized Return
- Maximum Drawdown
- Sharpe Ratio
- Total Commission
- Total Slippage Cost
- Executed Trades
- Skipped Trades
- Buy Count
- Sell Count
- Days Closed in A Zone
- Days Closed in C Zone
- Days Closed Outside C Boundary
- A/C zone entry counts
- First Return to Initial Share Position Equity
- Days Until First Return to Initial Share Position

### 12.1 Sharpe Ratio

Use:

- Daily close equity returns
- 252 trading days per year
- Risk-free rate default: 0%
- User may modify annual risk-free rate in Advanced Settings

The SPEC must define behavior when:

- There are too few returns
- Return standard deviation is zero
- Equity reaches invalid values

### 12.2 Zone Time Metrics

Because source data is daily:

- Count zone days using the day's Close
- Do not claim to measure intraday hours
- Use names such as:
  - `Days Closed in A Zone`
  - `Days Closed in C Zone`

### 12.3 Equity Series

Retain two series:

- Daily close equity
- Event-level equity after market/trade events

The main dashboard displays daily equity by default.

---

## 13. Exports and Reports

Required downloads:

- Trade Log CSV
- Daily Equity CSV
- Complete Result JSON
- PDF report

PDF is generated on demand and is not stored permanently.

PDF content:

- Project/backtest name
- Security information
- Data range
- Data-cleaning summary
- Strategy parameters
- Fee/slippage assumptions
- OHLC-path assumption
- Core metrics
- Both Buy-and-Hold benchmarks
- Price chart
- Equity curve
- Drawdown chart
- First 20 trades
- Cost summary
- Risk disclaimer

---

## 14. Authentication

Implement:

- Email registration
- Email/password login
- Logout
- Current-user endpoint
- JWT authentication
- Access token in secure HttpOnly cookie
- Password hashing with Argon2id

Security requirements:

- Never store plaintext passwords
- Do not expose password hashes
- Validate ownership on every dataset, backtest, export, and optimization request
- Use secure cookie settings appropriate to local development and production
- Keep secrets in environment variables
- Never commit `.env` files

---

## 15. Persistence Model

Minimum logical entities:

### User

- id
- email
- password_hash
- created_at
- updated_at

### Dataset

- id
- user_id
- name
- source_type
- original_filename
- security_name
- security_code
- data_mode
- start_date
- end_date
- row_count
- column_mapping
- cleaning_summary
- created_at

### PriceBar

- id
- dataset_id
- timestamp/date
- open nullable
- high nullable
- low nullable
- close
- volume nullable

### BacktestRun

- id
- user_id
- dataset_id
- name
- status
- configuration JSON
- OHLC path mode
- start/end dates
- result metrics JSON or normalized fields
- created_at
- completed_at

### Trade

- id
- backtest_run_id
- timestamp/date
- event sequence
- side
- grid_price
- execution_price
- shares
- notional
- commission
- slippage_cost
- cash_after
- shares_after
- equity_after
- status
- skip_reason nullable

### ZoneEvent

- id
- backtest_run_id
- timestamp/date
- event sequence
- event type
- price

### DailyEquity

- id
- backtest_run_id
- date
- close
- cash
- shares
- equity
- drawdown
- zone_at_close

### EventEquity

- id
- backtest_run_id
- timestamp/date
- event sequence
- market_price
- cash
- shares
- equity

### OptimizationJob

- id
- user_id
- dataset_id
- status
- search configuration
- training/testing configuration
- progress
- current combination
- current best
- estimated remaining time
- cancel_requested
- created_at
- started_at
- completed_at

### OptimizationResult

- id
- optimization_job_id
- parameter combination
- training metrics
- testing metrics
- rank fields
- created_at

Use Alembic migrations from the first database milestone.

---

## 16. Backtest History Features

History must support:

- List
- Search/filter
- View result
- Rename
- Delete
- Rerun
- Duplicate configuration into a new backtest
- Compare two or more runs
- Download stored results

Backtest name:

- Automatically generated
- User may edit

Example:

```text
159825 — A Grid 2% — 2026-07-15
```

---

## 17. Parameter Optimization

### 17.1 Optimizable Strategy Parameters

- A Distance
- A Grid Step
- A Trade Lots
- C Distance

Do not optimize:

- Commission
- Slippage
- OHLC path assumption

Those are modeling assumptions, not strategy-search parameters.

### 17.2 Range Types

Each selected parameter supports appropriate ranges:

- Percent range
- Fixed-value range
- Integer lot range

Each range includes:

- Start
- End
- Increment

Use deterministic Decimal stepping and include valid endpoints.

### 17.3 Search Modes

Support:

- One-parameter scan
- Multi-parameter Cartesian-product scan

Before starting, show:

- Total combinations
- Expected workload warning

### 17.4 Ranking Options

Allow sorting/ranking by:

- Final Equity
- Total Return
- Sharpe Ratio
- Maximum Drawdown
- Net Profit
- First Return to Initial Share Position Equity
- Days Until First Return to Initial Share Position

The detailed SPEC must define ascending/descending direction and missing-value behavior for each metric.

### 17.5 Training and Testing

Support:

- Automatic 70% training / 30% testing split
- Manual split date

Process:

1. Search parameter combinations on training data
2. Rank using the selected training metric
3. Evaluate selected/top combinations on testing data
4. Show training and testing results separately
5. Never silently rank using testing results

### 17.6 Storage and Display

- Save summary results for every combination
- Frontend shows top 20 by default
- User may inspect more
- Preserve the best run's detailed result when useful

### 17.7 Background Job Experience

Required UI:

- Progress bar
- Current combination
- Current best result
- Cancel button
- Estimated remaining time

Celery worker requirements:

- Periodically update job progress
- Check cancellation between combinations
- Persist enough state to display status after page refresh
- Mark failure with a useful error message

---

## 18. Frontend Information Architecture

Routes:

```text
/
  Landing page

/register
/login

/backtest/new
  Upload and data-confirmation wizard
  Strategy configuration

/backtest/[id]
  Results dashboard

/history
  Saved backtests

/optimization
  New and existing optimization jobs

/datasets
  Dataset management
```

### 18.1 New Backtest Flow

Recommended steps:

1. Upload file
2. Detect format
3. Confirm column mapping
4. Review bad rows and cleaning summary
5. Preview cleaned data
6. Save/reuse dataset
7. Configure portfolio and strategy
8. Run backtest
9. Navigate to result dashboard

### 18.2 Result Dashboard

Must show:

- Core metrics
- Benchmark comparison
- Candlestick chart when OHLC exists
- Close-price line
- A/C boundaries
- Baseline
- Grid lines
- Buy/sell markers
- Equity curve
- Drawdown chart
- Trade distribution
- Trade table
- Zone/risk events
- Export buttons

Grid-line display options:

- Hide
- Show all
- Show only near current/visible price range

### 18.3 Theme

Support light and dark themes.

The design should look like a professional trading dashboard, not a default admin template.

---

## 19. API Blueprint

The detailed SPEC must define exact request/response schemas.

Minimum endpoint groups:

### Authentication

```text
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
```

### Datasets

```text
POST   /api/datasets/preview
POST   /api/datasets
GET    /api/datasets
GET    /api/datasets/{dataset_id}
DELETE /api/datasets/{dataset_id}
```

`preview` accepts multipart upload and parsing options but does not permanently save the raw file.

### Backtests

```text
POST   /api/backtests
GET    /api/backtests
GET    /api/backtests/{backtest_id}
PATCH  /api/backtests/{backtest_id}
DELETE /api/backtests/{backtest_id}
POST   /api/backtests/{backtest_id}/rerun
POST   /api/backtests/{backtest_id}/duplicate
POST   /api/backtests/compare
```

### Exports

```text
GET /api/backtests/{backtest_id}/exports/trades.csv
GET /api/backtests/{backtest_id}/exports/equity.csv
GET /api/backtests/{backtest_id}/exports/result.json
GET /api/backtests/{backtest_id}/exports/report.pdf
```

### Optimizations

```text
POST /api/optimizations
GET  /api/optimizations
GET  /api/optimizations/{job_id}
POST /api/optimizations/{job_id}/cancel
GET  /api/optimizations/{job_id}/results
```

---

## 20. Backtest Engine Boundaries

The backtest engine must be a pure Python package with no dependency on:

- FastAPI request objects
- SQLAlchemy sessions
- HTTP
- React
- Celery
- PostgreSQL

Recommended backend separation:

```text
backend/app/
├── domain/
│   ├── models/
│   ├── enums/
│   └── exceptions/
├── data_import/
├── backtest/
│   ├── grid/
│   ├── execution/
│   ├── engine/
│   ├── metrics/
│   └── benchmarks/
├── optimization/
├── api/
├── db/
├── auth/
└── services/
```

The API/service layer converts database and request data into pure engine inputs, calls the engine, then persists outputs.

---

## 21. Testing Blueprint

### 21.1 Parser Tests

Include:

- TongdaXin GBK/GB18030 text-export `.xls`
- Normal UTF-8 CSV
- Chinese column detection
- English column detection
- Manual mapping
- Extra indicator columns
- Blank lines
- Footer/source line
- Invalid numeric rows
- Missing required values
- Duplicate dates
- Descending dates
- Close-only data
- Missing Volume

### 21.2 Grid Tests

Include:

- Percent A/C distance
- Fixed A/C distance
- Percent grid step
- Fixed grid step
- Baseline as grid
- Non-divisible distance/step
- Decimal precision
- Optional tick size

### 21.3 Engine Tests

Include:

- One downward crossing
- One upward crossing
- Exact-touch triggering
- Multi-grid crossings
- Same-day buy then sell
- Same-day sell then buy
- Repeated crossing of same grid
- Cash insufficient
- Shares insufficient
- No partial fill
- Anchor unchanged on skip
- Later levels attempted after skip
- A-to-C transition
- C-to-A transition
- Anchor preserved through C
- No C backfill
- Outside-C events
- First-day OHLC processing
- All three OHLC path modes
- Close-only processing

### 21.4 Fee Tests

Include:

- Buy/sell separate fees
- Percentage only
- Fixed only
- Minimum only with rate
- Rate + minimum + fixed
- Slippage percent/fixed
- Separate buy/sell slippage
- Tick rounding order

### 21.5 Metrics Tests

Include:

- Final equity
- Return
- Annualized return
- Max drawdown
- Sharpe
- Zero-volatility Sharpe case
- Commission/slippage totals
- Zone day counts
- Benchmark calculations
- First return to initial share position

### 21.6 API Tests

Include:

- Authentication
- Ownership isolation
- Dataset preview/save
- Backtest create/read/delete
- History operations
- Export endpoints
- Optimization lifecycle

### 21.7 Frontend and E2E Tests

Include:

- Upload wizard
- Column mapping
- Cleaning confirmation
- Strategy validation
- Run backtest
- Result dashboard
- History operations
- Login protection
- Optimization progress/cancel
- Downloads

---

## 22. Development Plan

The user plans roughly three intensive days, about eight hours per day, with additional time allowed if necessary.

### Day 1 — Foundation and Correct Engine

1. Create monorepo and GitHub repository
2. Create root README and blueprint/spec docs
3. Initialize backend environment
4. Define domain models and enums
5. Implement TongdaXin and CSV parser
6. Add parser tests
7. Implement boundary and grid generation
8. Add grid tests
9. Implement OHLC path segmentation
10. Implement execution engine
11. Add engine edge-case tests
12. Commit and push after each small feature

### Day 2 — API, Database, Auth, and Basic Frontend

1. Initialize FastAPI application
2. Add SQLAlchemy and Alembic
3. Add PostgreSQL entities/migrations
4. Implement auth
5. Implement dataset preview/save APIs
6. Implement backtest API and persistence
7. Initialize Next.js frontend
8. Build login/register pages
9. Build upload and cleaning wizard
10. Build strategy configuration
11. Connect frontend to backend
12. Build first working result dashboard

### Day 3 — Product Completion and Engineering

1. Complete charts and result tables
2. Add history and dataset pages
3. Add exports and PDF
4. Implement synchronous optimizer
5. Add optimizer tests
6. Add Celery + Redis worker
7. Build optimization UI
8. Add frontend component tests
9. Add Playwright E2E tests
10. Improve README and screenshots
11. Add Docker
12. Prepare public deployment

This is an aggressive target. Correctness and understanding take priority over finishing every feature in exactly three days.

---

## 23. Git Workflow

Branch:

```text
main
```

Use small commits, for example:

```text
chore: initialize monorepo
docs: add product blueprint
docs: add detailed specification
feat(parser): parse TongdaXin text exports
test(parser): cover invalid and Chinese data
feat(grid): generate fixed and percent grid levels
feat(engine): execute multi-level grid crossings
test(engine): preserve anchor through C zone
feat(api): add dataset preview endpoint
feat(auth): add JWT cookie authentication
feat(frontend): add upload wizard
feat(history): persist and list backtests
feat(optimizer): add synchronous parameter search
feat(worker): run optimization with Celery
feat(report): export PDF backtest report
test(e2e): cover complete backtest flow
```

Never commit:

- `.env`
- Secrets
- `.venv`
- `node_modules`
- Python caches
- Next.js build output
- Uploaded user files
- Local database files
- Generated reports

---

## 24. Claude Working Protocol

Claude must follow this workflow for every implementation task:

1. Explain the purpose of the task
2. List the files it plans to create or modify
3. Make one small cohesive change, normally touching 2–5 related files
4. Run relevant tests
5. Run type checking and linting
6. Show the actual command results
7. Explain the new code — in English; the user uses a separate assistant for Chinese summaries
8. Explain how data flows through the change
9. Ask the user to confirm understanding
10. Update README/SPEC when behavior changes
11. Create a meaningful Git commit
12. Push to GitHub

Claude must not:

- Generate the whole application in one step
- Change frozen trading rules without permission
- Hide failing tests
- Use mock behavior while claiming a feature is complete
- Add dependencies without explaining them
- Combine unrelated features into one task
- Rewrite working modules without a clear reason
- Commit secrets

---

## 25. Definition of Done

The project is complete when:

1. A user can register and log in
2. A user can upload the provided TongdaXin-style `.xls`
3. The system shows detected columns and bad rows
4. The system saves a cleaned reusable dataset
5. The user can configure all agreed strategy parameters
6. The engine correctly applies the frozen A/C and anchor rules
7. OHLC and Close-only modes work
8. Backtests persist in PostgreSQL
9. The dashboard shows all required metrics and charts
10. Both Buy-and-Hold benchmarks are shown
11. History operations work
12. Exports work
13. Optimization runs through a worker with progress and cancellation
14. Training/testing results remain separate
15. Unit, API, frontend, and E2E tests pass
16. README explains setup, architecture, strategy, and limitations
17. No secrets or generated artifacts are committed
18. The project can be run locally from documented commands
19. Docker setup works after being added
20. The code is understandable and explainable by the user

---

## 26. Required Next Step

Claude must now create:

```text
docs/SPEC.md
```

The SPEC must transform this blueprint into a detailed implementation contract containing:

- Exact terminology
- Exact validation rules
- Exact formulas
- Exact state transitions
- Exact grid-crossing algorithm
- Exact tick-rounding order
- Exact fee order
- Exact metric formulas
- Exact API request/response schemas
- Exact database constraints and relationships
- Exact error codes and error responses
- Exact page states
- Exact background-job lifecycle
- Acceptance criteria for every feature
- A traceability table mapping requirements to tests

Claude must first identify any genuine ambiguity that prevents a deterministic implementation. It must not ask questions about decisions already frozen in this blueprint.

No application code should be written until `docs/SPEC.md` is reviewed and approved.
