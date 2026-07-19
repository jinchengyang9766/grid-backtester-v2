# Grid Backtester V2 — Detailed Implementation Specification

**Status:** Approved for implementation — no application code has been written against this document yet.
**Relationship to `docs/BLUEPRINT.md`:** BLUEPRINT.md is the frozen, high-level source of truth for product scope and trading rules. This SPEC.md is the deterministic implementation contract derived from it. Wherever the two conflict, BLUEPRINT.md wins for *what* the product does; this document is authoritative for *exactly how* it is implemented. Any gap BLUEPRINT.md left open is closed here and explicitly logged in [Section 0](#0-engineering-decisions-derived-from-the-blueprint-summary-index).

**Confirmed with the user before writing this document:** Percent-mode grid step uses **arithmetic (uniform-dollar) spacing** — `step_size = baseline × step_pct`, computed once, then grid levels are `baseline ± k × step_size`. This is now a frozen trading rule (see [8.3](#83-grid-step-percent-mode-formulas)).

---

## Table of Contents

0. Engineering Decisions Derived from the Blueprint (summary index)
1. Terminology and Domain Definitions
2. Input Data Formats
3. TongdaXin `.xls` Parsing Rules
4. CSV Parsing and Column Mapping
5. Data Cleaning and Duplicate-Date Behavior
6. OHLCV and Close-Only Processing
7. Baseline, A Zone, C Zone, Outside-C
8. Grid Generation
9. Decimal Precision and Tick Size
10. `market_cursor`, `trade_anchor`, and Zone State
11. OHLC Path Processing
12. Crossing Inclusivity Rules
13. Multi-Grid Crossing
14. A↔C State Transitions
15. Trade Anchor Preservation and No-Backfill Rule
16. Order Execution Rules
17. Cash, Shares, Lot Size, Skipped Orders
18. Slippage
19. Commission
20. Buy-and-Hold Benchmarks
21. Metrics
22. Event-Level and Daily Equity
23. Database Schema
24. Authentication and Ownership
25. API Endpoints and Schemas
26. Standard API Error Format
27. Frontend Routes and Page States
28. Upload Wizard States
29. Backtest Dashboard
30. History and Comparison
31. Exports
32. PDF Report
33. Parameter Optimization
34. Training/Testing Split
35. Ranking Directions and Missing-Value Behavior
36. Celery Job Lifecycle
37. Security and Environment Variables
38. Acceptance Criteria
39. Requirement-to-Test Traceability Table
40. Implementation Phases and Dependency Order

---

## 0. Engineering Decisions Derived from the Blueprint (summary index)

BLUEPRINT.md deliberately left some mechanics as "recommended defaults" or asked SPEC.md to define them exactly. Per the task instructions, these are decided here and labeled — none of them alter product scope or reverse a rule BLUEPRINT.md already froze.

| # | Decision | Section |
|---|---|---|
| ED-1 | Duplicate dates: keep the row that appears **last in original file order** for each date | [5.3](#53-duplicate-date-policy) |
| ED-2 | Grid step Percent mode = arithmetic spacing, `step_size = baseline × step_pct` (user-confirmed) | [8.3](#83-grid-step-percent-mode-formulas) |
| ED-3 | The tradeable price path is **continuous across the whole dataset**, including the overnight gap `Close[N] → Open[N+1]` | [11.1](#111-path-construction-across-the-dataset) |
| ED-4 | Exact order of grid generation → tick rounding → slippage → tick rounding → fees | [9.3](#93-tick-rounding-order-frozen) |
| ED-5 | OHLC internal-consistency validation rules added to data cleaning | [5.2](#52-row-validity-rules) |
| ED-6 | Sharpe ratio edge-case behavior (too few returns, zero std dev) | [21.3](#213-sharpe-ratio) |
| ED-7 | Annualized Return uses trading-day-count basis (252/yr), not calendar days | [21.2](#212-annualized-return) |
| ED-8 | Maximum Drawdown is computed from the **Daily Close Equity** series (canonical), not event-level equity | [21.4](#214-maximum-drawdown) |
| ED-9 | "First Return to Initial Share Position" uses **executed trade events** (`shares_after` on each `EXECUTED` Trade), not end-of-day daily shares, and only counts a return after a genuine prior deviation | [21.10](#2110-first-return-to-initial-share-position) |
| ED-10 | Ranking sort directions per metric; nulls always sort last regardless of direction | [35](#35-ranking-directions-and-missing-value-behavior) |
| ED-11 | Optimization computes **both training and testing metrics for every combination** (not just the top N) | [33.4](#334-training-vs-testing-evaluation-scope) |
| ED-12 | Safety cap on total optimization combinations (default 5,000) and total grid levels per zone (default 10,000) | [33.2](#332-combination-count-safety-cap), [8.5](#85-grid-level-count-safety-cap) |
| ED-13 | Train/test split conventions: manual split date is `train < split_date <= test`; automatic 70/30 splits by **row ordinal**, not calendar time | [34](#34-trainingtesting-split) |
| ED-14 | Tick rounding function: `ROUND_HALF_UP` to nearest tick using `Decimal` | [9.2](#92-tick-rounding-function) |
| ED-15 | Baseline override may be any positive value, including outside the historical price range (produces a valid, possibly zero-trade backtest) | [7.1](#71-baseline) |
| ED-16 | JWT access-token expiry default 24h, no refresh token in V2, cookie flag conventions | [24.3](#243-token-and-cookie-rules) |
| ED-17 | Password policy: minimum 8 characters, Argon2id hashing | [24.2](#242-registration-rules) |
| ED-18 | Standard API error envelope shape and HTTP status mapping | [26](#26-standard-api-error-format) |
| ED-19 | `trade_lots` must be a positive integer (≥ 1) | [17.2](#172-lot-size-and-order-quantity) |
| ED-20 | `skip_reason` enum: `INSUFFICIENT_CASH`, `INSUFFICIENT_SHARES`, `INSUFFICIENT_CASH_FOR_COMMISSION` (revised — see [17.5](#175-numeric-and-zero-equity-validation)) | [17.4](#174-skip-reasons) |
| ED-21 | TongdaXin encoding detection order: `utf-8-sig` then `gb18030` (superset of GBK, so a separate `gbk` attempt is redundant) | [3.1](#31-encoding-detection) |
| ED-22 | TongdaXin header/footer detection heuristic | [3.2](#32-header-and-footer-detection) |
| ED-23 | Internal Decimal context precision 28 significant digits; DB columns `NUMERIC(20,8)` | [9.1](#91-decimal-precision) |
| ED-24 | Zone state enum: `IN_A`, `IN_C`, `OUTSIDE_C` | [10.3](#103-zone-state) |
| ED-25 | Commission component disable semantics (each of rate/minimum/fixed toggles independently; disabled = contributes 0) | [19.1](#191-commission-formula) |
| ED-26 | Frozen raw input-date contract (from the authoritative 159825 sample): trim, exact zero-padded `YYYY/MM/DD` only, `strptime` validation, applied identically to TongdaXin and CSV | [5.1](#51-cleaning-pipeline-order) |

These decisions are technical fill-ins, not scope or trading-rule changes. Items with real product-judgment risk were asked of the user before writing this document (see the grid-step decision above); no other blocking ambiguities were found.

---

## 1. Terminology and Domain Definitions

| Term | Definition |
|---|---|
| **Bar** | One row of cleaned price data for a single date: `(date, open?, high?, low?, close, volume?)`. |
| **Dataset** | A named, cleaned, reusable ordered sequence of Bars owned by a User. |
| **Baseline** | The reference price that centers the A and C zones. Default = first Bar's Close; user-overridable. Fixed for the duration of one backtest. |
| **A Zone** | `A Lower <= price <= A Upper`, the region where grid trading is active. |
| **C Zone** | Price is outside A but within `[C Lower, C Upper]`; trading is paused. |
| **Outside C** | Price is beyond `C Upper` or below `C Lower`; trading is paused, a risk event is recorded. |
| **Grid Level** | A discrete price value inside the A zone, generated by stepping from Baseline, at which trades may trigger. |
| **`market_cursor`** | The engine's current position along the continuous price path. Used for direction, zone detection, and segment processing. |
| **`trade_anchor`** | The last successfully executed grid price (or the initial anchor if none yet). Used to determine the next eligible grid level. |
| **Segment** | One adjacent pair of points along the price path (e.g. `Open → High`, or `Close[N] → Open[N+1]`), processed as one monotonic price move. |
| **Zone Event** | A non-trade record of a zone-boundary crossing: `ENTER_C_ZONE`, `EXIT_C_ZONE`, `OUTSIDE_C_BOUNDARY`, `RETURN_INSIDE_C_BOUNDARY`. |
| **Trade** | An executed or skipped order attempt at a specific grid level. |
| **Notional** | `execution_price × shares`, before commission. |
| **Lot** | `lot_size` shares (default 100). All order quantities are integer multiples of a lot (`trade_lots × lot_size`). |
| **OHLC Path Mode** | One of `HIGH_FIRST` (Open→High→Low→Close), `LOW_FIRST` (Open→Low→High→Close), or `AUTO` (chooses per-day based on Close vs Open). |
| **Data Mode** | `OHLCV` or `CLOSE_ONLY`, set per Dataset. |
| **Event Sequence** | A monotonically increasing integer, unique within a `backtest_run_id` (database-enforced via the `backtest_events` table, [23.5](#235-backtest_events)), ordering all Trades and ZoneEvents chronologically in one shared sequence (including same-day, same-segment ordering). |
| **Backtest Run** | One execution of the engine against one Dataset with one configuration, producing Trades, ZoneEvents, DailyEquity, EventEquity, and summary metrics. |
| **Optimization Job** | A background search over a Cartesian product of strategy-parameter ranges, each combination producing a training-period and testing-period result summary. |

---

## 2. Input Data Formats

### 2.1 Accepted Upload Types

| Type | Extension | Detection |
|---|---|---|
| TongdaXin text export | `.xls` | File does not parse as a valid OLE2/XLSX container (`zipfile`/`xlrd` open fails) **and** its decoded text contains tab-separated rows. Treated as tab-delimited text, never as a real spreadsheet. |
| Regular CSV | `.csv` | Parsed with `csv`/`pandas.read_csv`, delimiter auto-detected among `,`, `;`, `\t` (comma is the default assumption; sniffed via `csv.Sniffer` on the header line, falling back to comma on sniff failure). |

Any other extension is rejected with `UNSUPPORTED_FILE_TYPE` (see [26](#26-standard-api-error-format)).

### 2.2 Required Fields by Data Mode

| Data Mode | Required columns | Optional columns |
|---|---|---|
| `OHLCV` | Date, Open, High, Low, Close | Volume |
| `CLOSE_ONLY` | Date, Close | — |

A Dataset's `data_mode` is determined automatically from which columns were successfully mapped: if Open/High/Low all map, the dataset is `OHLCV`; if only Date/Close map, it is `CLOSE_ONLY`. If Close is missing, the upload is rejected (`MISSING_REQUIRED_COLUMN`). If exactly one or two of Open/High/Low map (not all three), the upload is rejected and the user must either complete the OHLCV mapping manually or explicitly proceed as Close-only by clearing the partial mapping — the wizard must never silently drop High or Low.

### 2.3 Column Name Recognition Table

Matching is case-insensitive, trims whitespace, and strips a leading/trailing BOM. Exact-match against this table first; if no exact match, no fuzzy matching is attempted (ambiguous columns must be mapped manually — no guessing).

| Field | Recognized headers |
|---|---|
| Date | `Date`, `date`, `日期`, `时间` |
| Open | `Open`, `open`, `开盘`, `开盘价` |
| High | `High`, `high`, `最高`, `最高价` |
| Low | `Low`, `low`, `最低`, `最低价` |
| Close | `Close`, `close`, `收盘`, `收盘价` |
| Volume | `Volume`, `volume`, `成交量` |

Any column not in this table (e.g. `MA5`, `VOL`, `MACD`, `成交额`, `涨跌幅`) is preserved in the raw preview grid but excluded from mapping candidates and never written to `PriceBar`.

---

## 3. TongdaXin `.xls` Parsing Rules

### 3.1 Encoding Detection

Try, in order, until one decodes the full byte stream without a `UnicodeDecodeError`:

1. `utf-8-sig`
2. `gb18030`

`gb18030` is a strict superset of `GBK`, so a separate `gbk` attempt is redundant (ED-21). If both fail, reject with `ENCODING_DETECTION_FAILED`.

```python
def decode_tdx_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise EncodingDetectionFailed()
```

### 3.2 Header and Footer Detection

The file is split into lines, each line split on `\t`.

1. **Title/blank lines**: any line before the header row with fewer than 2 tab-separated tokens, or matching `^[一-鿿\w\s()（）0-9]+$` with no recognized column keyword, is a title/blank line and is skipped.
2. **Header row**: the first line whose tab-separated tokens contain at least 2 headers matching [2.3](#23-column-name-recognition-table) (checking Chinese variants first, since TongdaXin exports are Chinese by default). This line's tokens become the column list.
3. **Data rows**: every line after the header row, until the footer, split on `\t` and mapped positionally to the header tokens.
4. **Footer detection**: parsing stops — the current line and every subsequent line are discarded as footer — **only** when a line matches a **recognized footer/source marker**: its joined text contains one of a known set of trailing-line phrases (`数据来源`, `来源：`, `来源:`, `免责声明`, `以上数据`, case-insensitive `disclaimer`, case-insensitive `source:`). These are the actual trailing lines TongdaXin exports append (e.g. `数据来源：通达信`). This is a keyword/pattern match, not a shape-based one — token count is deliberately **not** a footer signal (see below). No other "unambiguous TongdaXin footer signature" is defined for V2; if a future export format is found to append a distinct, reliably-recognizable trailing marker, it is added to this same keyword set, not implemented as a new shape-based heuristic.

   Everything else in the data section — including a row with fewer than 2 tab-separated tokens, a single un-delimited token, or any other malformed shape that isn't a recognized footer marker — is **not** a footer signal and does **not** stop parsing. If such a row's Date column fails to parse (which a 1-token or otherwise malformed row almost always will, since `align_to_header` cannot populate a Date field from a token that doesn't exist), it is reported as a bad row with reason `UNPARSEABLE_DATE` ([5.2](#52-row-validity-rules)), excluded from `data_rows`, and parsing **continues** — later rows in the file are still parsed and may be valid. This closes two related bugs from earlier drafts: first, stopping at the *first* unparseable-date row regardless of cause (any later valid rows were silently discarded); second, treating *any* short/low-token-count row as an automatic footer trigger (a single malformed data row — e.g. one missing its trailing tabs — could not be distinguished from a genuine footer line and would incorrectly discard every subsequent row, including valid ones). A malformed row is data-shaped noise to be reported and skipped, never a signal to stop reading the rest of the file.
5. **Row numbering**: every line in the data section (after the header, footer/blank lines excluded from consideration by construction) is numbered `row_number` = its 1-indexed position within that data section, assigned once, in original file order, before any row is classified as bad or dropped. This numbering is stable — a row's `row_number` never shifts because an earlier row turned out to be bad and was removed — so bad-row reports in the preview UI always point at the row's true original position.

```python
FOOTER_MARKERS = ("数据来源", "来源：", "来源:", "免责声明", "以上数据", "disclaimer", "source:")

def is_footer_line(tokens: list[str]) -> bool:
    # Keyword/pattern match only. Token count, line length, and other shape-based
    # signals are deliberately NOT used here -- a malformed data row (e.g. one
    # that lost its trailing tabs) is indistinguishable from a "short" footer
    # line by shape alone, and misclassifying it as footer would silently
    # discard every valid row after it. Shape-based rows that don't match a
    # marker fall through to the normal bad-row path in parse_tdx_text below.
    joined = "".join(tokens).strip().lower()
    return any(marker.lower() in joined for marker in FOOTER_MARKERS)

def parse_tdx_text(text: str) -> tuple[list[str], list[tuple[int, dict]], list[BadRow]]:
    lines = [ln.split("\t") for ln in text.splitlines() if ln.strip() != ""]
    header_idx = None
    for i, tokens in enumerate(lines):
        matches = sum(1 for t in tokens if normalize(t) in KNOWN_HEADERS)
        if matches >= 2:
            header_idx = i
            break
    if header_idx is None:
        raise HeaderNotFound()

    header = lines[header_idx]
    data_rows: list[tuple[int, dict]] = []   # (row_number, row)
    bad_rows: list[BadRow] = []
    for row_number, tokens in enumerate(lines[header_idx + 1:], start=1):
        if is_footer_line(tokens):
            break   # recognized footer/source marker -- stop entirely
        row = align_to_header(tokens, header)   # malformed/short/one-token rows align with blanks/missing fields
        if not is_parseable_date(row.get("date_raw")):
            bad_rows.append(BadRow(row_number=row_number, reason="UNPARSEABLE_DATE", raw=row))
            continue   # this row only is dropped; keep scanning subsequent rows
        data_rows.append((row_number, row))
    return header, data_rows, bad_rows
```

### 3.3 Extra Indicator Columns

Columns such as `MA5`, `MA10`, `VOL`, `MACD` are recognized as "present but unused" — they appear in the raw preview but are never candidates for the required-field mapping and are dropped when the Dataset is saved.

### 3.4 Security Name/Code Detection

If a title line exists above the header (per 3.2 step 1) and matches the pattern `<Chinese/alnum name>(<6-digit code>)` or `<name>\t<code>`, extract `security_name` and `security_code`. If no such line is found, both fields are left null — this is a best-effort convenience field, not a required one (`3.2 Explicitly Deferred` in BLUEPRINT.md rules out automatic security-type detection, but name/code extraction from an explicit title line is a much narrower, low-risk parse and is kept).

---

## 4. CSV Parsing and Column-Mapping Rules

1. Detect encoding the same way as [3.1](#31-encoding-detection) (CSV exports may also be GBK/GB18030 from Chinese tools).
2. Detect delimiter via `csv.Sniffer` on the first non-blank line; default to `,` on failure.
3. First non-blank row is always treated as the header row (no title/footer heuristics for CSV — if a CSV has extra header/footer lines, the user must clean it before upload or use manual row-skip, which is out of scope for V2 and not offered).
4. Column matching uses [2.3](#23-column-name-recognition-table). Unmatched headers are shown in the manual-mapping UI as free-choice dropdown targets.
5. Manual mapping overrides automatic mapping for any field the user changes. The final mapping used to save the Dataset is always exactly the mapping embedded in the `preview_token` the user confirms with — any edit to the mapping requires re-calling `POST /api/datasets/preview` with the edited `manual_mapping` to obtain a new token bound to that mapping and its resulting cleaning result ([25.2](#252-datasets)); there is no path that applies a mapping chosen at confirmation time to a cache produced under a different, earlier mapping.

---

## 5. Data Cleaning and Duplicate-Date Behavior

### 5.1 Cleaning Pipeline Order

1. Parse candidate rows (per format-specific rules above).
2. Apply column mapping → produce candidate `(date_raw, open_raw, high_raw, low_raw, close_raw, volume_raw)` tuples.
3. Convert `date_raw` to a date under the frozen raw-date contract below (ED-26); convert numeric fields to `Decimal`.
4. Apply row-validity rules ([5.2](#52-row-validity-rules)); invalid rows are set aside as **bad rows** with a reason, not included in later steps.
5. Sort remaining valid rows by date ascending.
6. Detect duplicate dates among valid rows ([5.3](#53-duplicate-date-policy)).
7. Produce the cleaning summary ([5.4](#54-cleaning-summary-shape)).
8. Show the wizard preview (first 50 + last 50 rows, bad-row table, duplicate-row table, summary).
9. On user confirmation, persist only the final deduplicated, sorted, valid rows as `PriceBar` records.

**Frozen raw input-date contract (ED-26).** Derived in Task 5A from the authoritative 159825 TongdaXin sample and applied identically to TongdaXin input and to the CSV `时间` column:

1. Trim leading and trailing whitespace from the raw value.
2. The trimmed value must match `^\d{4}/\d{2}/\d{2}$` exactly — zero-padded `YYYY/MM/DD` and nothing else.
3. A matching value is then validated with `datetime.strptime(value, "%Y/%m/%d")`; impossible calendar dates (e.g. `2024/02/30`) are rejected.
4. Every other form is rejected as `UNPARSEABLE_DATE`: empty or whitespace-only values, `YYYY-MM-DD`, `YYYYMMDD`, un-padded `YYYY/M/D`, values containing a time-of-day component, day-first or month-first slash forms, and any other format. No `dateutil`, fuzzy, or locale-dependent parsing is ever used. Additional accepted formats require an explicit future specification revision.

### 5.2 Row Validity Rules

A row is invalid (bad row) if any of the following hold, in this check order (the first matched reason is the recorded reason — checks stop at the first failure per row):

| Order | Reason code | Condition |
|---|---|---|
| 1 | `UNPARSEABLE_DATE` | Date cannot be parsed |
| 2 | `MISSING_CLOSE` | Close is blank or non-numeric |
| 3 | `NON_POSITIVE_PRICE` | Any present price field (Open/High/Low/Close) is `<= 0` |
| 4 | `MISSING_OHLC_FIELD` | In `OHLCV` mode, Open/High/Low is blank or non-numeric (ED-5: required once the dataset is determined to be OHLCV) |
| 5 | `INVALID_OHLC_RANGE` | (ED-5) In `OHLCV` mode: `High < Low`, or `High < Open`, or `High < Close`, or `Low > Open`, or `Low > Close` |
| 6 | `INVALID_VOLUME` | Volume is mapped and nonblank but cannot be parsed under the strict numeric contract (commas, currency symbols, scientific notation, `NaN`, `Infinity`, etc.) |
| 7 | `NEGATIVE_VOLUME` | Volume parses and is `< 0` |

Rule 4/5 (ED-5) are added because the engine's OHLC path processing assumes internally consistent bars; BLUEPRINT.md does not name this check explicitly, but its own principle #4 ("No hidden assumptions") requires it — an inconsistent bar would silently corrupt path segmentation.

### 5.3 Duplicate-Date Policy

Applied to already-valid, already-sorted rows.

- Group rows by date.
- For any date with more than one row, keep the row that appeared **last in the original (pre-sort) file order** (ED-1) — this matches BLUEPRINT.md's recommended default ("keep the last valid row for each date") and resolves the "last" ambiguity concretely.
- All other rows in that date group are listed in the wizard's duplicate-row table with the date, their values, and `reason: "DUPLICATE_DATE_DISCARDED"`.
- Deduplication only happens after explicit user confirmation, per BLUEPRINT.md 6.4 rule 12; until confirmed, the preview shows what *would* be kept/discarded.

### 5.4 Cleaning Summary Shape

```json
{
  "total_rows_parsed": 495,
  "valid_rows": 480,
  "bad_rows": 15,
  "duplicate_dates": 5,
  "final_row_count": 475,
  "date_range": { "start": "2020-01-02", "end": "2021-12-31" },
  "data_mode": "OHLCV",
  "bad_row_reasons": {
    "UNPARSEABLE_DATE": 2,
    "MISSING_CLOSE": 1,
    "NON_POSITIVE_PRICE": 3,
    "MISSING_OHLC_FIELD": 4,
    "INVALID_OHLC_RANGE": 5,
    "INVALID_VOLUME": 0,
    "NEGATIVE_VOLUME": 0
  }
}
```

`duplicate_dates` counts the number of **valid duplicate rows discarded** (one per `DUPLICATE_DATE_DISCARDED` record), not the number of distinct dates that had duplicates. `valid_rows` counts parsed rows minus bad rows, before duplicate removal. Therefore the counts always satisfy `valid_rows == total_rows_parsed - bad_rows` and `final_row_count == valid_rows - duplicate_dates`. `bad_row_reasons` always contains every reason key, including zero counts. When no valid rows remain, `date_range` is `null`.

---

## 6. OHLCV and Close-Only Processing

### 6.1 OHLCV Mode

- All four of Open/High/Low/Close are present per Bar (Volume optional).
- The user selects an OHLC Path Mode ([11](#11-ohlc-path-processing)) at backtest-configuration time (not at dataset-save time — the same Dataset can be backtested with different path modes).

### 6.2 Close-Only Mode

- Only Close is present per Bar.
- OHLC-path selection is disabled/hidden in the strategy configuration UI.
- Segment sequence is exactly one segment per adjacent Bar pair: `Close[i] → Close[i+1]`.
- The first Bar does not generate a segment; it only initializes `market_cursor = Close[0]` and, if no override, `trade_anchor = Close[0]` (per BLUEPRINT.md 5.6, restated in [10](#10-market_cursor-trade_anchor-and-zone-state)).
- Baseline default = `Close[0]`.

---

## 7. Baseline, A Zone, C Zone, Outside-C

### 7.1 Baseline

- Default: first cleaned Bar's `Close`.
- User override: any positive `Decimal` value (ED-15) — not required to fall within the dataset's historical price range. A baseline far outside the data's range is valid and will simply produce a backtest where price never enters A (zero trades), which is a legitimate, informative result, not an error.
- Fixed for the duration of one Backtest Run.

### 7.2 A Zone Boundaries

```text
if A_distance_mode == PERCENT:
    A_Upper = baseline * (1 + a_distance_pct)
    A_Lower = baseline * (1 - a_distance_pct)
if A_distance_mode == FIXED:
    A_Upper = baseline + a_distance_fixed
    A_Lower = baseline - a_distance_fixed
```

### 7.3 C Zone Boundaries

```text
if C_distance_mode == PERCENT:
    C_Upper = baseline * (1 + c_distance_pct)
    C_Lower = baseline * (1 - c_distance_pct)
if C_distance_mode == FIXED:
    C_Upper = baseline + c_distance_fixed
    C_Lower = baseline - c_distance_fixed
```

### 7.4 Validation

- `a_distance > 0`, `c_distance > 0` (in whichever unit each is configured — percent or fixed).
- `C Distance > A Distance` compared **after both are converted to absolute price distance from baseline** (i.e. `C_Upper - baseline > A_Upper - baseline`), since one may be Percent and the other Fixed. Violation → `INVALID_ZONE_CONFIG`.
- A Distance mode and C Distance mode are independent of each other and of Grid Step mode — any combination of Percent/Fixed across the three is valid.

### 7.5 Zone Classification

```text
IN_A        if A_Lower <= price <= A_Upper
IN_C        if (C_Lower <= price < A_Lower) or (A_Upper < price <= C_Upper)
OUTSIDE_C   if price < C_Lower or price > C_Upper
```

Boundaries themselves belong to the more restrictive (inner) zone — e.g. `price == A_Upper` is `IN_A`, not `IN_C`; `price == C_Upper` is `IN_C`, not `OUTSIDE_C`. This makes zone membership consistent with the crossing-inclusivity convention in [12](#12-crossing-inclusivity-rules).

---

## 8. Grid Generation

### 8.1 Grid Anchoring

Grid levels are generated directly from Baseline (not from A_Lower/A_Upper, and not path-dependently from each other), then filtered to those falling inside `[A_Lower, A_Upper]`. Baseline itself is always level `k = 0` and is always included (it is inside A by construction, since `A_Lower <= baseline <= A_Upper` always holds).

### 8.2 Grid Step Fixed Mode

```text
step_size = grid_step_fixed          # a literal price amount, Decimal
level(k) = baseline + k * step_size    for integer k (..., -2, -1, 0, 1, 2, ...)
```

### 8.3 Grid Step Percent Mode Formulas

**Frozen per user confirmation (ED-2):** arithmetic spacing.

```text
step_size = baseline * grid_step_pct   # computed once, a fixed Decimal price amount
level(k) = baseline + k * step_size    for integer k (..., -2, -1, 0, 1, 2, ...)
```

This is intentionally identical in shape to Fixed mode once `step_size` is derived — Percent mode only differs in *how* `step_size` is computed, never in how levels are spaced from each other.

### 8.4 Non-Divisible A Distance

```python
def generate_grid_levels(baseline: Decimal, a_lower: Decimal, a_upper: Decimal,
                          step_size: Decimal) -> list[Decimal]:
    assert step_size > 0
    levels = [baseline]
    k = 1
    while True:
        lvl = baseline + k * step_size
        if lvl > a_upper:
            break
        levels.append(lvl)
        k += 1
    k = -1
    while True:
        lvl = baseline + k * step_size
        if lvl < a_lower:
            break
        levels.append(lvl)
        k -= 1
    return sorted(levels)
```

- `A_Lower`/`A_Upper` are **never** forced onto the grid (BLUEPRINT.md 5.5).
- `grid_step` is never adjusted to fit evenly (BLUEPRINT.md 5.5).
- The last level below `A_Upper` and the last level above `A_Lower` may leave an uneven gap to the boundary itself — this is expected and not an error.
- This function always produces the **raw** levels, at full Decimal precision. When Tick Size is enabled, these raw levels are never used directly for crossing/logging/execution — they are the input to the tick-normalization step in [9.4](#94-canonical-grid-levels-tick-size-enabled), which produces the actual `grid_levels` the rest of the engine uses.

### 8.5 Grid Level Count Safety Cap

(ED-12) If the loop above would produce more than `MAX_GRID_LEVELS` (default **10,000**, configurable via environment/config, not user-facing) levels in either direction, generation is aborted and the backtest/optimization-combination request is rejected with `GRID_TOO_DENSE`. This guards against pathological configs (e.g. a near-zero step size) causing unbounded memory/time use; it is a defensive engineering limit, not a product feature, and is documented here so it is not mistaken for a silent scope cut.

---

## 9. Decimal Precision and Tick Size

### 9.1 Decimal Precision

(ED-23) All price, cash, share-value, commission, and slippage arithmetic uses Python's `Decimal` with a context precision of **28 significant digits** (the `decimal` module default). No intermediate rounding is applied unless Tick Size is enabled ([9.2](#92-tick-rounding-function)). Database columns storing these values are `NUMERIC(20,8)` (see [23](#23-database-schema)). Share counts are always integers (`NUMERIC(20,0)` / `BIGINT`).

When Tick Size is disabled, values are never forcibly rounded by the engine; API responses serialize `Decimal` as strings (not floats) to avoid precision loss, and the frontend formats for display (default 4 decimal places for prices, 2 for cash/equity) without mutating the underlying value.

### 9.2 Tick-Rounding Function

(ED-14) When Tick Size is enabled:

```python
def round_to_tick(value: Decimal, tick_size: Decimal) -> Decimal:
    ticks = (value / tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return ticks * tick_size
```

`tick_size > 0` is required whenever `tick_size.enabled == true` — validated as `422 NON_POSITIVE_TICK_SIZE` ([17.5](#175-numeric-and-zero-equity-validation)); a zero or negative tick size makes `value / tick_size` either undefined or sign-reversing, which has no sensible trading interpretation.

### 9.3 Tick-Rounding Order (frozen)

(ED-4) Applies only when Tick Size is enabled. Grid-level tick-rounding happens **once**, at grid-generation time, producing the canonical `grid_levels` list ([9.4](#94-canonical-grid-levels-tick-size-enabled)) — it is not repeated per trade attempt. The exact pipeline for one trade attempt is:

1. Take the level from the canonical `grid_levels` list ([9.4](#94-canonical-grid-levels-tick-size-enabled)) — already tick-rounded (Tick Size enabled) or exact (disabled). This is the **same** value used for the crossing-eligibility test ([12](#12-crossing-inclusivity-rules), [13](#13-multi-grid-crossing)) and for `Trade.grid_price` logging ([23.6](#236-trades)) — one canonical price serves all three purposes.
2. Apply slippage to that canonical grid price (per [18](#18-slippage)) → raw execution price.
3. Round the raw execution price to the nearest tick → **tick-rounded execution price**. This is the price actually used for the trade.
4. Compute `notional = tick_rounded_execution_price × shares`.
5. Compute commission from `notional` (per [19](#19-commission)). Commission itself is **not** tick-rounded (it is a monetary fee, not a tradeable price).

Baseline and A/C boundaries are **never** tick-rounded (per BLUEPRINT.md 10.2's explicit wording "Grid prices and execution prices must be normalized to valid ticks" — boundaries are neither). `trade_anchor` comparisons are not separately rounded either. This splits into two distinct cases, per [10.2](#102-initialization): before any successful trade, `trade_anchor` is the initial anchor (`Open[0]` for OHLCV, `Close[0]` for CLOSE_ONLY) — an arbitrary market price, not required to be a grid level and **not** tick-rounded, even when Tick Size is enabled. After the first successful trade, `trade_anchor` is reassigned to the executed level, which is always drawn from the canonical `grid_levels` list ([13.2](#132-algorithm)) and is therefore always already tick-rounded from that point on. This is unit-tested by asserting the exact sequence: `raw grid → tick → dedupe` (once, at setup — [9.4](#94-canonical-grid-levels-tick-size-enabled)), then `canonical grid → slippage → tick → fees` (per attempt) — and separately, that the pre-trade initial anchor is never run through `round_to_tick` at all.

### 9.4 Canonical Grid Levels (Tick Size enabled)

There is exactly one `grid_levels` list per backtest run (or per optimization combination), and it is used, unmodified, for **crossing eligibility** ([12](#12-crossing-inclusivity-rules), [13](#13-multi-grid-crossing)), **trade logging** (`Trade.grid_price`, [23.6](#236-trades)), and **execution** ([16](#16-order-execution-rules)) — never a raw list for one purpose and a rounded list for another.

```python
def canonical_grid_levels(baseline: Decimal, a_lower: Decimal, a_upper: Decimal,
                           step_size: Decimal, tick_enabled: bool,
                           tick_size: Decimal | None) -> list[Decimal]:
    raw_levels = generate_grid_levels(baseline, a_lower, a_upper, step_size)   # 8.4
    if not tick_enabled:
        return raw_levels

    rounded = [round_to_tick(lv, tick_size) for lv in raw_levels]             # 9.2
    # A rounded level can fall outside [a_lower, a_upper] even though its raw
    # source level did not, since boundaries themselves are never tick-rounded
    # (9.3). Such a level is simply not part of the grid -- the same "never
    # forced onto the grid" philosophy as 8.4, just applied post-rounding.
    in_range = sorted(set(lv for lv in rounded if a_lower <= lv <= a_upper))

    if len(in_range) < len(raw_levels):
        # Two or more distinct raw levels rounded to the same tick, and/or a
        # level rounded outside the A zone. Silently trading a smaller level
        # set than the user's a_distance/grid_step configuration implies would
        # violate the "no hidden assumptions" principle, so this configuration
        # is rejected rather than silently deduplicated.
        raise GridCollapsesAfterTickRounding(raw_count=len(raw_levels),
                                              canonical_count=len(in_range))
    return in_range
```

`state.grid_levels = canonical_grid_levels(...)` is computed once, before path processing begins. `trade_anchor`'s *initial* value is **not** drawn from this list — per [10.2](#102-initialization), it starts as `Open[0]`/`Close[0]` verbatim, an ordinary market price that is not required to coincide with any canonical grid level and is never tick-rounded, whether or not Tick Size is enabled. Only from the first successful trade onward is `trade_anchor` reassigned a value drawn from `grid_levels` ([13.2](#132-algorithm)) — from that point on, by construction, it is always already tick-rounded when Tick Size is enabled. `Trade.grid_price` always stores the canonical (post-rounding) price, never the pre-rounding raw one, for every logged trade attempt — that guarantee is about `Trade` rows, not about the pre-trade initial anchor, which is never itself logged as a `Trade`.

**`GRID_COLLAPSES_AFTER_TICK_ROUNDING`**: if `canonical_grid_levels` raises, `POST /api/backtests` — and per-combination validation during optimization ([33.2](#332-combination-count-safety-cap)) — rejects with `422 GRID_COLLAPSES_AFTER_TICK_ROUNDING`, `details: { "raw_count": ..., "canonical_count": ... }`. This check runs *after* [8.5](#85-grid-level-count-safety-cap)'s `GRID_TOO_DENSE` cap (which bounds the raw level count before tick rounding is even considered) and is independent of it — a configuration can fail either, both, or neither.

**Collapse example**: `baseline = 10.00`, `step_size = 0.003` (Percent mode producing a sub-tick step), `tick_size = 0.01`. Raw levels near baseline include `10.000`, `10.003`, `10.006`, `10.009`, `10.012`, ...; rounding to the nearest `0.01` tick collapses `10.000`/`10.003` both to `10.00`, and `10.006`/`10.009` both to `10.01` — `canonical_count < raw_count`, so this configuration is rejected with `GRID_COLLAPSES_AFTER_TICK_ROUNDING` rather than silently trading a coarser grid than the user configured.

---

## 10. `market_cursor`, `trade_anchor`, and Zone State

### 10.1 Relationship

Three pieces of engine state evolve together but serve different purposes:

- **`market_cursor`**: the current point on the price path. Updates continuously as segments are processed; used to detect direction and zone.
- **`trade_anchor`**: the last successfully executed grid price (or the initial anchor). Updates **only** on a successful trade. Used to compute the next eligible grid level.
- **`zone_state`** ([10.3](#103-zone-state)): engine-mutable state, changed only by initialization and by the explicit boundary-crossing transitions in [14.3](#143-segment-processing-algorithm-supersedes-113s-sketch) — never recomputed from an arbitrary in-transit `market_cursor` position via `classify()`. See [14.1](#141-zone_state-model-single-source-of-truth) for the full model and why `classify()` cannot drive in-transit transitions.

`trade_anchor` is intentionally decoupled from `market_cursor`: the cursor can wander through C and back without moving the anchor at all (BLUEPRINT.md 5.6, 8.6).

### 10.2 Initialization

```text
OHLCV mode:      market_cursor = trade_anchor = Open[0]
CLOSE_ONLY mode: market_cursor = trade_anchor = Close[0]
zone_state       = classify(market_cursor)        # 7.5, computed once here
```

(BLUEPRINT.md 5.6 "If no successful trade has occurred, the initial trade anchor is...", 7 "The initial market_cursor and trade_anchor start at first-day Open".)

### 10.3 Zone State

Enum (ED-24): `IN_A`, `IN_C`, `OUTSIDE_C`. Set once at initialization via `classify(market_cursor)` ([7.5](#75-zone-classification)); thereafter changed only by the explicit boundary-crossing transitions defined in [14.2](#142-boundary-crossing-transition-table)–[14.3](#143-segment-processing-algorithm-supersedes-113s-sketch). It is mutable engine state, not a value re-derived from `market_cursor` on demand — see [14.1](#141-zone_state-model-single-source-of-truth) for why `classify()` is unsafe to use for in-transit crossing decisions (it cannot distinguish "about to enter the outer zone" from "resting on the boundary of the inner zone," since both map to the same boundary price). `classify()` is still used, separately, for `zone_at_close` in the Daily Equity table ([21.6](#216-zone-day-counts), [22.2](#222-daily-equity-calculation)) — a point-in-time snapshot of a closing price, not a crossing decision.

---

## 11. OHLC Path Processing

### 11.1 Path Construction Across the Dataset

(ED-3) The tradeable price path is one continuous sequence spanning the entire dataset, not independent per-day paths. Every point on the path carries the date of the `Bar` it belongs to, plus whether it is that `Bar`'s **final** point — this metadata is what [11.6](#116-event-date-attribution-and-daily-equity-capture-point) uses to make date attribution and Daily Equity capture fully deterministic, including across the overnight gap.

```python
@dataclass(frozen=True)
class PathPoint:
    price: Decimal
    date: date          # the Bar this point belongs to
    is_bar_final: bool  # True iff this is the last point contributed by its Bar
                         # (the Close point, in OHLCV mode; always True in
                         # CLOSE_ONLY mode, since each Bar contributes exactly
                         # one point there)
```

For `OHLCV` mode with `N` bars:

```python
def build_path_ohlcv(bars: list[Bar], ohlc_path_mode) -> list[PathPoint]:
    points = []
    for i, bar in enumerate(bars):
        mid1, mid2 = select_mids(bar, ohlc_path_mode, i)   # 11.2
        points += [
            PathPoint(bar.open,  bar.date, is_bar_final=False),
            PathPoint(mid1,      bar.date, is_bar_final=False),
            PathPoint(mid2,      bar.date, is_bar_final=False),
            PathPoint(bar.close, bar.date, is_bar_final=True),
        ]
    return points
```

Every **adjacent pair** in this flattened sequence is one segment, including the overnight-gap pair `Close[i] → Open[i+1]` (i.e. `points[4i+3] → points[4i+4]`). Rationale: BLUEPRINT.md 5.6 describes `market_cursor` as tracking "the real or assumed price path" (singular, continuous) and BLUEPRINT.md 7 states the cursor "starts at first-day Open" — implying the path is one uninterrupted sequence, not a per-day reset. Treating the overnight gap as a real segment is also required for correctness: without it, a gap that jumps straight through several grid levels or through a zone boundary overnight would be invisible to the engine, violating BLUEPRINT.md principle #4 ("No hidden assumptions").

For `CLOSE_ONLY` mode:

```python
def build_path_close_only(bars: list[Bar]) -> list[PathPoint]:
    return [PathPoint(bar.close, bar.date, is_bar_final=True) for bar in bars]
```

One segment per adjacent pair, per [6.2](#62-close-only-mode). Every segment here (`Close[i] → Close[i+1]`) is structurally the same kind of cross-day gap as `OHLCV`'s overnight segment — see [11.6](#116-event-date-attribution-and-daily-equity-capture-point) for why this needs no separate rule.

### 11.2 Path Mode Selection

```text
HIGH_FIRST: mid1 = High, mid2 = Low     (Open → High → Low → Close)
LOW_FIRST:  mid1 = Low,  mid2 = High    (Open → Low → High → Close)
AUTO:       per-day, if Close[i] >= Open[i]: use LOW_FIRST for day i
            else: use HIGH_FIRST for day i
```

`AUTO` is evaluated independently for each day; different days in the same backtest may use different sub-paths.

### 11.3 Segment Processing Algorithm

```python
def process_path(points: list[PathPoint], state: EngineState) -> None:
    # CLOSE_ONLY mode's initial point doubles as Bar 0's only (and therefore
    # final) point, with no preceding segment to trigger a capture for it --
    # see 11.6 for why this one-time check at the top is necessary and why
    # OHLCV mode never needs it (its initial point is Open[0], never a bar's
    # final point).
    if points[0].is_bar_final:
        capture_daily_equity(points[0].date, points[0].price, state)   # 22.2

    for start, end in zip(points, points[1:]):
        direction = "DOWN" if end.price < start.price else "UP"
        process_segment(start.price, end.price, direction, state,
                         event_date=end.date)   # 14.3, the canonical definition;
                                                 # event_date is always the segment's
                                                 # END point's date -- 11.6
        if end.is_bar_final:
            capture_daily_equity(end.date, end.price, state)   # 22.2 -- fires once per Bar, strictly
                                                      # before the next loop iteration (which,
                                                      # for the Bar just closed, is exactly the
                                                      # overnight-gap segment leading out of it)
```

`process_segment` — including zone-boundary handling, sub-segment splitting, and the A↔C state machine — is specified exactly once, in [14.3](#143-segment-processing-algorithm-supersedes-113s-sketch); this section does not define its own competing version. `attempt_grid_crossings` is specified in [13](#13-multi-grid-crossing). `capture_daily_equity` is specified in [22.2](#222-daily-equity-calculation).

### 11.4 First-Day Processing

Day 0's segments (`Open[0]→mid1[0]`, `mid1[0]→mid2[0]`, `mid2[0]→Close[0]`) are processed exactly like any other day's segments — there is no special-cased "day 0 does nothing" behavior beyond the fact that `market_cursor`/`trade_anchor` initialize at `Open[0]` rather than at some prior value, so the *first* segment naturally starts there (BLUEPRINT.md 7).

### 11.5 Same-Day and Repeated Crossings

- The same day can contain both buys and sells (e.g. `Open→High` segment sells, `High→Low` segment buys), per BLUEPRINT.md 7.
- The same grid level can be crossed multiple times across the whole path, each a fresh eligible trade once `trade_anchor` has moved off it, per BLUEPRINT.md 8.4.

### 11.6 Event-Date Attribution and Daily Equity Capture Point

**Every `Trade`/`ZoneEvent` a segment produces is dated with that segment's END point's date — one uniform rule, no per-segment-kind special case.** [11.3](#113-segment-processing-algorithm)'s loop passes `event_date=end.date` into `process_segment` for every segment, and `process_segment`/`attempt_grid_crossings`/`apply_boundary_transition` ([13.2](#132-algorithm), [14.3](#143-segment-processing-algorithm-supersedes-113s-sketch)) only ever forward that one value into `log_trade`/`emit_zone_event` — they never derive a date from a price or from `direction`. For an ordinary intraday segment (e.g. `mid1[i] → mid2[i]`), both endpoints share `bars[i].date`, so the rule is trivially "today." For the overnight-gap segment `Close[i] → Open[i+1]`, the end point is `Open[i+1]`, which carries `bars[i+1].date` by construction ([11.1](#111-path-construction-across-the-dataset)) — so every `Trade`/`ZoneEvent` produced while the cursor is between `Close[i]` and `Open[i+1]` is dated `bars[i+1].date`, satisfying this requirement exactly, as a consequence of the general rule rather than a special case written for it. The same reasoning applies uniformly to `CLOSE_ONLY` mode's `Close[i] → Close[i+1]` segments (end point `Close[i+1]`, date `bars[i+1].date`) — every segment in that mode is a "cross-day gap" in this sense, and none needs distinct handling from any other.

**Daily Equity for `bars[i].date` is captured exactly once, immediately after `bars[i]`'s own final point is reached as a segment's end, and strictly before the next segment (the overnight gap leading into `bars[i+1]`) is processed.** This is what [11.3](#113-segment-processing-algorithm)'s `if end.is_bar_final: capture_daily_equity(...)` check inside the loop guarantees structurally: the capture for `Bar i` runs synchronously within the loop iteration whose segment ends at `Bar i`'s final point (`Close[i]` for `OHLCV`, `Close[i]` for `CLOSE_ONLY` too, since it's the bar's only point), and the very next iteration — the one that would process any overnight-gap segment leading out of `Bar i` — cannot begin until that capture has already returned. There is no separate ordering assumption to maintain elsewhere; the sequencing is inherent to the loop itself, not a convention that could be violated by reordering unrelated code.

The one case that check alone cannot cover is `CLOSE_ONLY` mode's `Bar 0`: its single point (`Close[0]`) is both the path's very first point (per [10.2](#102-initialization), `market_cursor = trade_anchor = Close[0]`) and `Bar 0`'s final point — but a "first point" is never reached as a segment's *end* (there is no segment before it), so the in-loop check would never fire for it. [11.3](#113-segment-processing-algorithm)'s one-time check before the loop begins (`if points[0].is_bar_final: capture_daily_equity(...)`) exists specifically for this case; it is a no-op in `OHLCV` mode, where the initial point is `Open[0]` and `is_bar_final` is always `False` there.

---

## 12. Crossing Inclusivity Rules

For a single monotonic segment `[segment_start, segment_end]` restricted to the portion currently `IN_A` (per [14](#14-ac-state-transitions)):

```text
Downward segment (segment_end < segment_start):
    eligible grid_level  <=>  segment_end <= grid_level < segment_start
                          AND grid_level < trade_anchor

Upward segment (segment_end > segment_start):
    eligible grid_level  <=>  segment_start < grid_level <= segment_end
                          AND grid_level > trade_anchor
```

- Reaching a grid line exactly counts as a crossing (`<=`/`>=` at the far end of the range).
- `trade_anchor` itself is excluded from being retriggered (BLUEPRINT.md 8.2) — this is the strict `<`/`>` against `trade_anchor` above, layered on top of the inclusive range test against the segment endpoints.
- Zone-boundary inclusivity (A/C boundaries) uses the same "far/inner edge belongs to the more restrictive zone" convention established in [7.5](#75-zone-classification): a segment that reaches exactly `A_Upper` while moving up is still `IN_A` at that instant and can still trigger a sell at that level if `A_Upper` happens to coincide with a grid level.

---

## 13. Multi-Grid Crossing

### 13.1 Ordering Rule

Within one segment (or one A-restricted sub-segment), all eligible grid levels — per [12](#12-crossing-inclusivity-rules) — are attempted **in strict price order along the direction of travel** (BLUEPRINT.md 8.3):

- Downward segment: attempt from the highest eligible level down to the lowest.
- Upward segment: attempt from the lowest eligible level up to the highest.

### 13.2 Algorithm

```python
def attempt_grid_crossings(seg_start: Decimal, seg_end: Decimal, direction: str,
                            state: EngineState, event_date: date) -> None:
    levels = state.grid_levels  # sorted ascending, fixed for the whole backtest;
                                 # canonical (already tick-rounded when Tick Size
                                 # is enabled, 9.4) -- the same list used for
                                 # logging and execution, not a raw list
    if direction == "DOWN":
        candidates = [lv for lv in levels
                      if seg_end <= lv < seg_start and lv < state.trade_anchor]
        candidates.sort(reverse=True)   # highest first
    else:
        candidates = [lv for lv in levels
                      if seg_start < lv <= seg_end and lv > state.trade_anchor]
        candidates.sort()               # lowest first

    side = "BUY" if direction == "DOWN" else "SELL"
    for level in candidates:
        result = execute_or_skip(level, side, state)  # see 16
        log_trade(result, state, event_date)   # event_date, not derived from the price --
                                                # see 11.6 for why it's always the caller's
                                                # segment-end date, passed down from process_path
        if result.executed:
            state.trade_anchor = level
        # Per BLUEPRINT.md 9.3: a failed order does NOT stop later levels
        # in the same segment from being attempted.
```

This directly encodes BLUEPRINT.md's worked example (anchor 1.00, path 1.00→0.80, step 0.05 → attempts 0.95, 0.90, 0.85, 0.80 BUY in that order) and the "failed order does not block later levels" rule (BLUEPRINT.md 8.2, 9.3).

---

## 14. A↔C State Transitions

### 14.1 `zone_state` Model (single source of truth)

`zone_state` is engine-mutable state, not a value re-derived from `market_cursor` on demand. It changes in exactly two ways, and no others:

1. **Initialization** — once, at backtest start: `zone_state = classify(market_cursor_initial)` ([7.5](#75-zone-classification), [10.2](#102-initialization)).
2. **Explicit boundary-crossing transitions** — during path processing, applied only by the table-driven algorithm in [14.2](#142-boundary-crossing-transition-table)–[14.3](#143-segment-processing-algorithm-supersedes-113s-sketch).

`classify()` is a pure function of a price and never drives an in-transit transition directly, because it cannot distinguish "the path is about to leave the inner zone through this boundary" from "the path is resting exactly on the inner zone's edge" — both map to the same boundary price under §7.5's inner-zone-wins rule. After initialization, `classify()` is used only for two purposes that do not conflict with the mutable `zone_state` above:
- resolving the resting zone when a segment's *end* lands exactly on a boundary ([14.3](#143-segment-processing-algorithm-supersedes-113s-sketch), final step);
- computing `zone_at_close` for the Daily Equity table ([21.6](#216-zone-day-counts), [22.2](#222-daily-equity-calculation)) — an independent point-in-time snapshot of a closing price, not a crossing decision.

This is the one consistent model referenced throughout this document; earlier drafts described `zone_state` as both "purely derived" ([10.1](#101-relationship) old wording) and independently mutated by `process_segment` — that contradiction is resolved in favor of "mutable, transitioned only by §14.2's table."

### 14.2 Boundary-Crossing Transition Table

Zone boundaries are strictly ordered around baseline (`C_Lower < A_Lower < baseline < A_Upper < C_Upper`, enforced by [7.4](#74-validation)), and each has exactly one **outward** direction of travel (away from baseline, entering the wider zone) and one **inward** direction (toward baseline, entering the narrower zone). The transition triggered by reaching a boundary therefore depends **only** on which boundary it is and the direction of travel — never on `classify(boundary)`, and never computed by "nearest boundary by distance":

| Boundary | Direction | Required prior `zone_state` | New `zone_state` | Event |
|---|---|---|---|---|
| `A_Upper` | UP (outward) | `IN_A` | `IN_C` | `ENTER_C_ZONE` |
| `A_Lower` | DOWN (outward) | `IN_A` | `IN_C` | `ENTER_C_ZONE` |
| `C_Upper` | UP (outward) | `IN_C` | `OUTSIDE_C` | `OUTSIDE_C_BOUNDARY` |
| `C_Lower` | DOWN (outward) | `IN_C` | `OUTSIDE_C` | `OUTSIDE_C_BOUNDARY` |
| `A_Upper` | DOWN (inward) | `IN_C` | `IN_A` | `EXIT_C_ZONE` |
| `A_Lower` | UP (inward) | `IN_C` | `IN_A` | `EXIT_C_ZONE` |
| `C_Upper` | DOWN (inward) | `OUTSIDE_C` | `IN_C` | `RETURN_INSIDE_C_BOUNDARY` |
| `C_Lower` | UP (inward) | `OUTSIDE_C` | `IN_C` | `RETURN_INSIDE_C_BOUNDARY` |

This table is the **only** place a transition is decided (BLUEPRINT.md 8.5–8.7: A→C is `ENTER_C_ZONE`/no anchor change/no trade; C→A is `EXIT_C_ZONE`/no anchor change/no backfill; Outside-C is `OUTSIDE_C_BOUNDARY`/`RETURN_INSIDE_C_BOUNDARY`/no liquidation/no anchor change/no trade — all preserved exactly, just relocated into one table instead of three prose subsections that individually under-specified the boundary-price edge cases below).

### 14.3 Segment Processing Algorithm (supersedes §11.3's sketch)

This is the canonical, non-recursive definition; [11.3](#113-segment-processing-algorithm) invokes it directly.

```python
def boundary_kind(price: Decimal) -> str | None:
    if price == A_Upper: return "A_UPPER"
    if price == A_Lower: return "A_LOWER"
    if price == C_Upper: return "C_UPPER"
    if price == C_Lower: return "C_LOWER"
    return None

def apply_boundary_transition(boundary: Decimal, direction: str, state: EngineState,
                               event_date: date) -> None:
    old_zone, new_zone, event_type = TRANSITION_TABLE[(boundary_kind(boundary), direction)]
    assert state.zone_state == old_zone           # invariant: 7.4 guarantees no two boundaries
                                                    # share a price, so this can never mismatch
    emit_zone_event(event_type, boundary, state, event_date)   # exactly once per call
    state.zone_state = new_zone
    state.market_cursor = boundary

def process_segment(seg_start: Decimal, seg_end: Decimal, direction: str,
                     state: EngineState, event_date: date) -> None:
    # event_date is the date every Trade/ZoneEvent this segment produces is
    # stamped with (via emit_zone_event/log_trade -> the shared backtest_events
    # row, 23.5) -- it is passed down from process_path (11.6) as the calling
    # segment's END point's date, uniformly for ordinary intraday segments and
    # for the overnight-gap segment alike. process_segment itself never
    # derives a date from seg_start/seg_end/direction; it only forwards the
    # one it was given.
    if seg_end == seg_start:
        return  # no movement, nothing to evaluate

    # --- Case: seg_start sits exactly on a boundary ------------------------
    # Continuing OUTWARD past it is a transition, fired here at zero distance,
    # before any grid attempt on this segment. Continuing INWARD from it is
    # not: the point already belongs to the inner zone (7.5), so motion
    # simply continues inside that zone and nothing fires.
    starting_kind = boundary_kind(seg_start)
    if starting_kind is not None:
        expected_old_zone = TRANSITION_TABLE[(starting_kind, direction)][0]
        if state.zone_state == expected_old_zone:
            apply_boundary_transition(seg_start, direction, state, event_date)

    # --- Interior boundaries, in the order this segment reaches them -------
    ordered_boundaries = [A_Upper, A_Lower, C_Upper, C_Lower]
    crossed = sorted(
        (b for b in ordered_boundaries if is_strictly_between(seg_start, b, seg_end)),
        reverse=(direction == "DOWN"),
    )
    sub_start = seg_start
    for boundary in crossed:
        if state.zone_state == "IN_A":
            attempt_grid_crossings(sub_start, boundary, direction, state, event_date)
        apply_boundary_transition(boundary, direction, state, event_date)   # exactly once per boundary
        sub_start = boundary

    # --- Final leg -----------------------------------------------------------
    if state.zone_state == "IN_A":
        attempt_grid_crossings(sub_start, seg_end, direction, state, event_date)
    state.market_cursor = seg_end

    # --- Case: seg_end lands exactly on a boundary ----------------------------
    # Reaching the line is not the same as continuing past it. If the leg that
    # just ended was on the OUTER side (e.g. OUTSIDE_C approaching C_Upper from
    # above), touching the boundary already reclassifies as the inner zone
    # (7.5) -- emit the matching "inward" event once. If the leg was already on
    # the INNER side (e.g. IN_A reaching A_Upper from below), the resting zone
    # is unchanged and nothing fires (12 still allows a trade exactly at
    # seg_end in that case, since zone_state never left IN_A).
    ending_kind = boundary_kind(seg_end)
    if ending_kind is not None:
        resting_zone = classify(seg_end)   # 7.5, inner-zone-wins
        if state.zone_state != resting_zone:
            inward_direction = "DOWN" if ending_kind in ("A_UPPER", "C_UPPER") else "UP"
            apply_boundary_transition(seg_end, inward_direction, state, event_date)
```

**Why no recursion, and no duplicate events:** the whole segment is processed by two flat passes over a precomputed, direction-sorted list of at most 4 boundaries (`ordered_boundaries`) — never by re-scanning for "the next boundary" after mutating state, which is what made the previous recursive `next_boundary_crossing` design vulnerable to reprocessing a boundary or looping if a boundary price happened to re-satisfy a betweenness test after `market_cursor` was set to it. `is_strictly_between` excludes both of its own endpoints by construction, so a boundary equal to `seg_start` or `seg_end` can never also appear in `crossed`; combined with the fact that the pre-check only fires for `seg_start`, the loop only fires for boundaries strictly inside the segment, and the ending-check only fires for `seg_end`, `apply_boundary_transition` is called **at most once per boundary per segment**, across three mutually exclusive call sites.

### 14.4 Worked Examples

- **A → C mid-segment** (BLUEPRINT.md 8.5): path `0.94 → 0.97`, `A_Upper = 0.95`. `crossed = [0.95]`. Grid crossings attempted on `[0.94, 0.95]` while `IN_A`; `apply_boundary_transition(0.95, UP, ...)` fires `ENTER_C_ZONE`, `zone_state → IN_C`; the final leg `[0.95, 0.97]` attempts no grid crossings.
- **C → A mid-segment** (BLUEPRINT.md 8.6): symmetric — `EXIT_C_ZONE` fires when the segment crosses back through `A_Upper`/`A_Lower` from `IN_C`; `trade_anchor` is untouched throughout ([15](#15-trade-anchor-preservation-and-no-backfill-rule)).
- **Gap straight through both boundaries** (BLUEPRINT.md 8.7): path `0.94 → 1.10`, `A_Upper = 0.95`, `C_Upper = 1.05`. `crossed = [0.95, 1.05]` (ascending, direction `UP`). The loop fires `ENTER_C_ZONE` at `0.95`, then — with `zone_state == IN_C`, so no grid attempt in between — fires `OUTSIDE_C_BOUNDARY` at `1.05`. Both events are recorded, in that price order, within one segment, with no recursion involved.
- **Starting exactly on a boundary, moving outward**: the previous segment ended exactly at `A_Upper = 0.95` with no event (see the next example). The next segment is `0.95 → 0.98`. `starting_kind = "A_UPPER"`, `direction = UP`, `expected_old_zone = IN_A`, which matches the current state — `apply_boundary_transition(0.95, UP, ...)` fires `ENTER_C_ZONE` immediately; `0.95` is then excluded from `crossed` (it equals `seg_start`), so it is never processed a second time.
- **Starting exactly on a boundary, moving inward**: segment `0.95 → 0.90` (`A_Lower = 0.90`, `zone_state = IN_A`). `starting_kind = "A_UPPER"`, but `expected_old_zone` for `(A_UPPER, DOWN)` is `IN_C`, which does not match the current `IN_A` — no transition fires; the segment is processed as an ordinary in-`A` segment.
- **Ending exactly on a boundary, approached from inside**: segment `0.92 → 0.95` (`A_Upper = 0.95`), `zone_state = IN_A` throughout. `ending_kind = "A_UPPER"`, `resting_zone = classify(0.95) = IN_A`, equal to the current `zone_state` — no event; `zone_state` stays `IN_A`. A sell at `0.95` (if it is also a grid level) is still eligible, per [12](#12-crossing-inclusivity-rules).
- **Ending exactly on a boundary, approached from outside**: segment `1.10 → 1.05` (`C_Upper = 1.05`), `zone_state = OUTSIDE_C` throughout. `ending_kind = "C_UPPER"`, `resting_zone = classify(1.05) = IN_C`, which differs from `OUTSIDE_C` — `apply_boundary_transition(1.05, DOWN, ...)` fires `RETURN_INSIDE_C_BOUNDARY`; `zone_state → IN_C`. (If the segment had instead continued past `1.05` within the same leg, that is handled by the interior-boundary loop, not this final step.)

---

## 15. Trade Anchor Preservation and No-Backfill Rule

Restating BLUEPRINT.md 5.6/8.6 as hard invariants, enforced by construction in the algorithms above (not by an extra check):

- `trade_anchor` changes **only** inside `execute_or_skip` on a successful fill ([16](#16-order-execution-rules)), never anywhere else in the engine.
- Entering C, moving within C, and exiting C never touch `trade_anchor`.
- Grid levels whose price was passed while `zone_state != IN_A` are never retroactively attempted — `attempt_grid_crossings` is only ever called on the `IN_A` portion of a sub-segment ([14.3](#143-segment-processing-algorithm-supersedes-113s-sketch)), so a level crossed while `IN_C` structurally cannot appear in any `candidates` list, now or later.

Worked example from BLUEPRINT.md 8.6 (`A_Lower=0.90`, anchor `0.95`, path `0.95→0.85→0.92`, later `→1.00`): after `0.92`, `trade_anchor` is still `0.95`; the next eligible sell is `1.00` (the first grid level `> 0.95` reached going up), not `0.90` or any level skipped inside C. This is exactly what [12](#12-crossing-inclusivity-rules)'s `grid_level > trade_anchor` test produces.

---

## 16. Order Execution Rules

### 16.1 Execution Pipeline for One Attempted Level

```python
def execute_or_skip(grid_level: Decimal, side: str, state: EngineState) -> TradeResult:
    # grid_level is drawn from state.grid_levels, which is already the
    # canonical, tick-rounded list (9.4) -- no re-rounding of the grid price
    # happens here, only of the post-slippage execution price.
    raw_exec_price = (grid_level + state.buy_slippage(grid_level)) if side == "BUY" \
                 else (grid_level - state.sell_slippage(grid_level))
    exec_price = round_to_tick(raw_exec_price, state.tick_size) if state.tick_enabled else raw_exec_price
    if exec_price <= 0:
        # Defensive invariant, not a normal skip: a non-positive execution price means
        # the configuration (grid price vs. fixed slippage magnitude) is nonsensical, not
        # that this particular attempt happened to fail a cash/share check. 17.5.
        raise NonPositiveExecutionPriceError(grid_price=grid_level, execution_price=exec_price)

    shares = state.trade_lots * state.lot_size
    notional = exec_price * shares
    commission = compute_commission(side, notional, state)

    if side == "BUY":
        total_cost = notional + commission
        if total_cost > state.cash:
            return TradeResult(executed=False, skip_reason="INSUFFICIENT_CASH",
                                grid_price=grid_level, execution_price=None,
                                cash_after=state.cash, shares_after=state.shares,
                                equity_after=state.cash + state.shares * grid_level)   # 16.4 --
                                # cash/shares unchanged (the buy never happened), marked at
                                # grid_level (this attempt's canonical_grid_price), not exec_price
        state.cash -= total_cost
        state.shares += shares
    else:  # SELL
        if shares > state.shares:
            return TradeResult(executed=False, skip_reason="INSUFFICIENT_SHARES",
                                grid_price=grid_level, execution_price=None,
                                cash_after=state.cash, shares_after=state.shares,
                                equity_after=state.cash + state.shares * grid_level)   # 16.4
        if state.cash + (notional - commission) < 0:
            # commission exceeds notional by more than current cash can absorb -- 17.5
            return TradeResult(executed=False, skip_reason="INSUFFICIENT_CASH_FOR_COMMISSION",
                                grid_price=grid_level, execution_price=None,
                                cash_after=state.cash, shares_after=state.shares,
                                equity_after=state.cash + state.shares * grid_level)   # 16.4
        state.cash += (notional - commission)
        state.shares -= shares

    return TradeResult(executed=True, grid_price=grid_level, execution_price=exec_price,
                        shares=shares, notional=notional, commission=commission,
                        slippage_cost=abs(exec_price - grid_level) * shares,
                        cash_after=state.cash, shares_after=state.shares,
                        equity_after=state.cash + state.shares * grid_level)   # 16.4 --
                        # grid_level (canonical_grid_price), never exec_price; see 16.4 for why
```

`grid_price` in the returned `TradeResult` — and therefore in `Trade.grid_price` ([23.6](#236-trades)) and `trade_anchor` when this fill executes ([13.2](#132-algorithm)) — is always the same canonical value used for the crossing-eligibility test that selected this level in the first place; there is no longer a separate raw-vs-rounded value logged.

### 16.2 Buy Rule

Direction `DOWN` only. `execution_price = grid_price(+tick) + buy_slippage`. Executes only if `notional + commission <= cash` (no partial fills — BLUEPRINT.md 6/9.3).

### 16.3 Sell Rule

Direction `UP` only. `execution_price = grid_price(+tick) - sell_slippage`. Executes only if **both** `shares_needed <= shares_held` (no short selling — BLUEPRINT.md 6/9.3) **and** `cash + (notional - commission) >= 0` (a sell can never make cash negative, [17.5](#175-numeric-and-zero-equity-validation)) — the shares check is evaluated first, and the cash check only applies once it passes.

### 16.4 `Trade.equity_after` and `EventEquity.equity`, Exactly

**`Trade.equity_after`** ([23.6](#236-trades)), for **every** `Trade` row — `EXECUTED` or `SKIPPED` alike:

```text
equity_after = cash_after + shares_after * canonical_grid_price
```

`canonical_grid_price` is `grid_level` — the same canonical, already-tick-rounded value ([9.4](#94-canonical-grid-levels-tick-size-enabled)) used for this attempt's crossing-eligibility test and stored as `Trade.grid_price`. It is **not** `execution_price`: `execution_price` (grid price plus/minus slippage, then tick-rounded again, [9.3](#93-tick-rounding-order-frozen)) determines how much cash moves — via `notional`, `commission`, and slippage — but once that cash movement is applied, the *remaining* portfolio (whatever shares are held after this attempt) is marked at the canonical grid price, not at the execution price that was only relevant to the shares/cash actually transacted in this one attempt. This applies identically whether the trade executed or was skipped: a `SKIPPED` trade's `cash_after`/`shares_after` are simply unchanged from before the attempt ([17.3](#173-constraints)), but `equity_after` is still computed — marked at that attempt's `grid_level` — so every `Trade` row, executed or not, carries a well-defined portfolio value at that instant.

**`canonical_grid_price` is also this event's `backtest_events.market_price`** ([23.5](#235-backtest_events): "grid price for a trade attempt") — `log_trade` writes the same `grid_level` value into both places. There is exactly one canonical price per trade attempt, used for crossing, logging, `Trade.grid_price`, `Trade.equity_after`'s mark, and `backtest_events.market_price` alike — never a second, different price computed for any one of these purposes.

**`EventEquity.equity`** ([23.9](#239-event_equity)), for every `EventEquity` row, `Trade`-linked or `ZoneEvent`-linked alike:

```text
equity = cash + shares * backtest_event.market_price
```

using the `cash`/`shares` already stored on that same `EventEquity` row (the engine state immediately after the event, [22.3](#223-event-equity-calculation)) and the `market_price` of its parent `backtest_events` row — `canonical_grid_price` for a `Trade`-linked event, the zone-boundary price for a `ZoneEvent`-linked one ([23.5](#235-backtest_events)). One direct consequence: for a `Trade`-linked `EventEquity` row, `cash == Trade.cash_after`, `shares == Trade.shares_after`, and `market_price == canonical_grid_price` are the exact same three values `Trade.equity_after` was computed from — so that row's `equity` always equals the linked `Trade.equity_after` exactly, by construction, not by coincidence. For a `ZoneEvent`-linked row, this formula is the *only* place that event's equity is computed at all (`ZoneEvent` itself has no `equity` column), marked at the boundary price the zone transition occurred at.

---

## 17. Cash, Shares, Lot Size, Skipped Orders

### 17.1 Initial Portfolio

- `initial_cash: Decimal >= 0`.
- `initial_shares: int >= 0`, not required to be a multiple of `lot_size` (BLUEPRINT.md 9.1).
- Initial equity mark: `OHLCV → Open[0]`, `CLOSE_ONLY → Close[0]` (BLUEPRINT.md 9.1 recommended convention, adopted as-is):
  `initial_equity = initial_cash + initial_shares * mark_price`.

### 17.2 Lot Size and Order Quantity

```text
order_shares = trade_lots * lot_size
```

- `lot_size: int >= 1`, default `100`.
- `trade_lots: int >= 1` (ED-19) — a configuration with `trade_lots < 1` is rejected at validation (`INVALID_TRADE_LOTS`); there is no such thing as a zero-size order.
- `order_shares` is constant for every executed trade within one backtest run (BLUEPRINT.md 9.2 — a single global setting, not per-level).

### 17.3 Constraints

- No short selling: a sell is skipped if `order_shares > shares_held` at attempt time.
- No negative cash: a buy is skipped if `notional + commission > cash` at attempt time; a sell is skipped if `cash + (notional - commission) < 0` at attempt time — i.e. a sell can never make cash negative even when commission exceeds the sale's notional ([17.5](#175-numeric-and-zero-equity-validation)).
- No partial fills: an order either fully executes at `order_shares` or is fully skipped — there is no reduced-quantity fallback.
- Every skipped order is logged as a `Trade` row with `status=SKIPPED` and a `skip_reason`.
- A skip never prevents later crossed levels in the same segment from being attempted (state carries `cash`/`shares` forward unchanged, and the loop in [13.2](#132-algorithm) continues regardless of `result.executed`).
- `trade_anchor` updates only on `status=EXECUTED`.

### 17.4 Skip Reasons

(ED-20, revised) Enum: `INSUFFICIENT_CASH` (buy), `INSUFFICIENT_SHARES` (sell), `INSUFFICIENT_CASH_FOR_COMMISSION` (sell, [17.5](#175-numeric-and-zero-equity-validation)). No other skip reasons exist in V2 scope (there is no volume/liquidity constraint per BLUEPRINT.md 3.2 Explicitly Deferred).

### 17.5 Numeric and Zero-Equity Validation

Every numeric field below is checked at `POST /api/backtests` request-validation time ([25.3](#253-backtests)) — and, for optimization, against every generated combination ([33.8](#338-invalid-combination-handling)) — as `422 VALIDATION_ERROR` with the listed `error.code` in `details`, **except** `NON_POSITIVE_EXECUTION_PRICE`, which is a runtime engine invariant (it depends on the interaction of grid prices, actual price data, and slippage, so it cannot be ruled out purely from the submitted configuration) and instead fails the `BacktestRun` ([25.3](#253-backtests), synchronous-failure behavior).

| Rule | Error code | Where enforced |
|---|---|---|
| `initial_cash >= 0` | `NEGATIVE_INITIAL_CASH` | [17.1](#171-initial-portfolio) |
| `initial_shares >= 0` | `NEGATIVE_INITIAL_SHARES` | [17.1](#171-initial-portfolio) |
| `initial_equity > 0` (fails only when `initial_cash == 0` **and** `initial_shares == 0`, since `mark_price > 0` always — [5.2](#52-row-validity-rules)) | `ZERO_INITIAL_EQUITY` | [17.1](#171-initial-portfolio), [21.1](#211-basic-metrics) |
| `lot_size >= 1` | `INVALID_LOT_SIZE` | [17.2](#172-lot-size-and-order-quantity) |
| `trade_lots >= 1` | `INVALID_TRADE_LOTS` | [17.2](#172-lot-size-and-order-quantity) (ED-19, unchanged) |
| Every enabled commission component (`rate` when `rate_enabled`, `minimum` when `minimum_enabled`, `fixed` when `fixed_enabled` — buy and sell independently) `>= 0` | `NEGATIVE_COMMISSION_COMPONENT` | [19.1](#191-commission-formula) |
| Every enabled slippage value (`slippage_pct` or `slippage_fixed`, buy and sell independently) `>= 0` | `NEGATIVE_SLIPPAGE` | [18.2](#182-modes) |
| `tick_size > 0` whenever `tick_size.enabled == true` | `NON_POSITIVE_TICK_SIZE` | [9.2](#92-tick-rounding-function) |
| `risk_free_rate_annual > -1` (required for `(1 + rate) ** (1/252)` in [21.3](#213-sharpe-ratio) to be real-valued) | `INVALID_RISK_FREE_RATE` | [21.3](#213-sharpe-ratio) |
| `execution_price > 0` for every attempted trade (runtime, not request-time) | `NON_POSITIVE_EXECUTION_PRICE` | [16.1](#161-execution-pipeline-for-one-attempted-level) |
| A sell's cash effect can never make `cash` negative | `INSUFFICIENT_CASH_FOR_COMMISSION` (skip reason, not a validation error — the configuration is valid, this specific attempt just doesn't clear) | [16.1](#161-execution-pipeline-for-one-attempted-level), [16.3](#163-sell-rule) |

**Commission exceeds sell notional.** This is not rejected at validation time — a `minimum_commission` floor legitimately can exceed a small trade's notional (e.g. a `¥5` minimum commission on a `¥3` notional), and that is an economically real outcome the engine must be able to represent, not a configuration error. When it happens, `cash += (notional - commission)` **decreases** cash (since `notional - commission < 0`); the sell still executes normally as long as `cash + (notional - commission) >= 0` (§16.3's second condition). Only when this would drive cash negative is the sell skipped, with `skip_reason = INSUFFICIENT_CASH_FOR_COMMISSION`.

**`NON_POSITIVE_EXECUTION_PRICE` failure behavior.** If the engine ever computes `execution_price <= 0` (only possible with a `FIXED`-mode `sell_slippage` whose magnitude exceeds a low grid price, or an equivalently pathological `FIXED` buy-slippage/tick combination), the trade attempt raises rather than returning a `TradeResult` — this is a data/configuration pathology, not a normal cash/share shortfall, so it is not logged as a `SKIPPED` trade. The engine aborts the run: `BacktestRun.status = "FAILED"`, `error_message` set to a sanitized description naming the offending grid price and computed execution price (full detail logged server-side), consistent with [25.3](#253-backtests)'s general engine-failure handling.

## 18. Slippage

### 18.1 Formulas (BLUEPRINT.md 10.1, restated exactly)

```text
Buy execution price  = Grid Price (post-tick) + Buy Slippage
Sell execution price = Grid Price (post-tick) - Sell Slippage
```

### 18.2 Modes

```text
Percent mode: slippage_amount = grid_price * slippage_pct
Fixed mode:   slippage_amount = slippage_fixed
```

Percent-mode slippage is always computed from the **tick-rounded grid price** (per the frozen order in [9.3](#93-tick-rounding-order-frozen)), never from the raw pre-tick grid price and never from the resulting execution price.

`slippage_pct`/`slippage_fixed` (buy and sell independently) must be `>= 0` — validated as `422 NEGATIVE_SLIPPAGE` ([17.5](#175-numeric-and-zero-equity-validation)). A negative value would mean "slippage that improves the price," which is not a real execution phenomenon this engine models.

### 18.3 Buy/Sell Symmetry Configuration

- Default: one shared `slippage` setting applied to both sides.
- Advanced: independent `buy_slippage` / `sell_slippage`, each with its own mode (Percent/Fixed) and value.

### 18.4 Total Slippage Cost Tracking

Per trade: `slippage_cost = abs(execution_price - tick_rounded_grid_price) * shares`. Backtest-level `Total Slippage Cost = sum(slippage_cost over all EXECUTED trades)`.

---

## 19. Commission

### 19.1 Commission Formula

(BLUEPRINT.md 10.3, exact; ED-25 clarifies the disable semantics)

```text
percentage_component = notional * rate   if rate_enabled, else 0

if minimum_enabled:
    percentage_component = max(percentage_component, minimum)

total_commission = percentage_component + (fixed if fixed_enabled else 0)
```

Request/schema field names ([23.4](#234-backtest_runs)'s `configuration` JSONB, [25.3](#253-backtests)): each of `buy_commission`/`sell_commission` is `{ rate_enabled, rate, minimum_enabled, minimum, fixed_enabled, fixed }` — three independent boolean toggles, each paired with its own value field:

- `rate_enabled` (bool) / `rate` (Decimal): when `rate_enabled == false`, `percentage_component` starts at exactly `0` regardless of what `rate` holds (an unused, disabled field's value is never read into the formula) — matching how `minimum_enabled`/`fixed_enabled` already behave. When `rate_enabled == true`, `rate >= 0` is required.
- `minimum_enabled` (bool) / `minimum` (Decimal): unchanged from earlier drafts — when enabled, floors `percentage_component` at `minimum`; when disabled, no floor is applied at all (not a floor of `0`).
- `fixed_enabled` (bool) / `fixed` (Decimal): unchanged — when enabled, added to `total_commission`; when disabled, contributes `0`.
- All three toggle independently, on both `buy_commission` and `sell_commission` separately (BLUEPRINT.md 10.3 "Buy and sell fee settings are separate").
- Every **enabled** component's value, on both sides, must be `>= 0` — validated as `422 NEGATIVE_COMMISSION_COMPONENT` ([17.5](#175-numeric-and-zero-equity-validation)), which applies uniformly to `rate` (when `rate_enabled`), `minimum` (when `minimum_enabled`), and `fixed` (when `fixed_enabled`). A **disabled** component's value is not validated at all (it is never read), consistent with it never being read into the formula either. A `minimum` floor can still legitimately exceed a small trade's `notional` (see [17.5](#175-numeric-and-zero-equity-validation)'s "commission exceeds sell notional" case) — that is a valid outcome of a valid (non-negative) configuration, not something this rule forbids.

### 19.2 Cash Effects

```text
Buy:  cash -= (notional + commission)
Sell: cash += (notional - commission)
```

---

## 20. Buy-and-Hold Benchmarks

### 20.1 Benchmark 1 — Same Initial Portfolio, No Trades

```text
shares_b1[t] = initial_shares                      for all t
cash_b1[t]   = initial_cash                         for all t
equity_b1[t] = initial_cash + initial_shares * close[t]
```

Computed for every daily Bar `t`, using that day's Close.

### 20.2 Benchmark 2 — Invest Available Cash on Day One

Benchmark 2's single day-one purchase reuses the **exact same** execution pipeline as a normal strategy BUY ([16.1](#161-execution-pipeline-for-one-attempted-level)/[9.3](#93-tick-rounding-order-frozen)) — first-price selection, tick normalization, buy slippage, the second post-slippage tick normalization, commission, and lot-size rounding are not reimplemented with different logic; only the *quantity-selection* step differs (a max-affordable search instead of a fixed `trade_lots`), because Benchmark 2 has no `trade_lots` setting of its own — it always buys the largest whole-lot quantity it can afford (BLUEPRINT.md 11.2).

```python
def benchmark2_execution_price(first_price: Decimal, state: EngineState) -> tuple[Decimal, Decimal]:
    # Identical in shape to execute_or_skip's BUY path (16.1): tick-round the reference
    # price, apply buy slippage to the tick-rounded price, tick-round the result again.
    # The only difference from a normal grid buy is that the "grid price" here is the
    # day-one first price (Open[0] for OHLCV, Close[0] for CLOSE_ONLY -- the same mark
    # price convention as 17.1), not a canonical grid level.
    # Returns (tick_price, exec_price) -- tick_price is kept for slippage_cost (16.1's
    # abs(exec_price - grid_level) convention), not just the final exec_price.
    tick_price = round_to_tick(first_price, state.tick_size) if state.tick_enabled else first_price
    raw_exec_price = tick_price + state.buy_slippage(tick_price)
    exec_price = round_to_tick(raw_exec_price, state.tick_size) if state.tick_enabled else raw_exec_price
    return tick_price, exec_price
```

**Maximum affordable whole-lot quantity — deterministic binary search.** `affordable(lots)` — "can `lots` whole lots be bought without exceeding `initial_cash`" — is monotonic: `notional = exec_price * lots * lot_size` is strictly increasing in `lots` (`exec_price > 0`, [17.5](#175-numeric-and-zero-equity-validation)), and `compute_commission` ([19](#19-commission)) is non-decreasing in `notional` even with a `minimum_commission` floor (the floor only ever raises the fee, never lowers it) — so total cost is strictly increasing in `lots`, and once `affordable(lots)` is `false` it is `false` for every larger `lots` too. This monotonicity is exactly what makes a binary search valid, and it replaces the previous one-lot-at-a-time incremental loop (which was correct but did `O(affordable_lots)` calls to `compute_commission` — unbounded in the size of `initial_cash`) with an `O(log(affordable_lots))` search:

```python
def benchmark2_day_one_buy(initial_cash: Decimal, initial_shares: int,
                            tick_price: Decimal, exec_price: Decimal,
                            lot_size: int, commission_config) -> BenchmarkDayOneResult:
    def affordable(lots: int) -> bool:
        if lots == 0:
            return True
        shares = lots * lot_size
        notional = exec_price * shares
        commission = compute_commission("BUY", notional, commission_config)   # 19
        return notional + commission <= initial_cash

    lo, hi = 0, 1
    while affordable(hi):
        lo = hi
        hi *= 2   # exponential search for an upper bound -- affordable_lots is finite and
                  # small in practice (bounded by initial_cash / (lot_size * tick_size or
                  # smaller realistic prices)), so this terminates quickly
    # invariant: affordable(lo) is true, affordable(hi) is false
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if affordable(mid):
            lo = mid
        else:
            hi = mid
    lots = lo   # the maximum affordable whole-lot quantity, exact

    if lots == 0:
        # Zero-affordable-lot case: initial_cash cannot cover even one lot at
        # exec_price (plus its commission). No order is attempted, so nothing
        # about the portfolio changes and compute_commission is never called
        # for a zero-share order -- calling it would be wrong, since a
        # minimum_commission floor or a fixed_fee component would otherwise
        # charge a fee for a trade that never happened.
        return BenchmarkDayOneResult(
            cash_after=initial_cash, shares_after=initial_shares,
            commission=Decimal("0"), slippage_cost=Decimal("0"),
        )

    shares = lots * lot_size
    notional = exec_price * shares
    commission = compute_commission("BUY", notional, commission_config)
    cash_after = initial_cash - notional - commission
    shares_after = initial_shares + shares
    slippage_cost = abs(exec_price - tick_price) * shares   # 18.4's convention
    return BenchmarkDayOneResult(
        cash_after=cash_after, shares_after=shares_after,
        commission=commission, slippage_cost=slippage_cost,
    )
```

`BenchmarkDayOneResult.commission`/`.slippage_cost` are exactly `benchmark2_day_one_commission`/`benchmark2_day_one_slippage_cost` ([21.8](#218-buy-and-hold-benchmark-metrics)) — both `Decimal("0")` in the zero-affordable-lot case, never the output of `compute_commission(..., notional=0, ...)`, which could be nonzero under a `minimum_commission` or `fixed_fee` configuration and would misreport a fee for a trade that never happened.

This search is exact regardless of how the commission formula's `minimum_commission` floor interacts with notional size — the same guarantee the previous incremental loop provided, just without the unbounded iteration count; a closed-form division is still not safe once a minimum-commission floor is possible, which is why this remains a search rather than arithmetic. After day one:

```text
shares_b2[t] = shares_after       for all t >= 0 (constant, held to the end)
cash_b2[t]   = cash_after         for all t >= 0 (constant, never reinvested)
equity_b2[t] = cash_after + shares_after * close[t]
```

No partial fills — the search above only ever accepts whole lots, matching [17.3](#173-constraints)'s constraint for ordinary trades.

---

## 21. Metrics

All metrics are computed once per completed Backtest Run and stored (see [23](#23-database-schema)). Series-based metrics (Annualized Return, Max Drawdown, Sharpe) use the **Daily Close Equity** series (ED-8) unless stated otherwise.

### 21.1 Basic Metrics

```text
Initial Equity = initial_cash + initial_shares * mark_price[0]     (17.1)
Final Equity   = DailyEquity[last].equity
Net Profit     = Final Equity - Initial Equity
Total Return   = Final Equity / Initial Equity - 1
```

`Initial Equity == 0` (only possible if `initial_cash == 0` and `initial_shares == 0`) can no longer reach this calculation — it is rejected at request-validation time with `422 ZERO_INITIAL_EQUITY` ([17.5](#175-numeric-and-zero-equity-validation)), so `Total Return` can always safely divide by `Initial Equity` without a `null`/`N/A` case to handle here.

That guarantee is about `Initial Equity` only — it says nothing about `Final Equity` (or any other day's equity). `Final Equity == 0` is a legitimate, fully representable outcome (a strategy that loses its entire position and all cash, with nothing left by the end of the backtest — see [21.11](#2111-zero-equity-and-division-safety) for exactly how this can happen without short selling or negative cash). When it does, `Total Return = 0 / Initial Equity - 1 = -1` exactly: a `-100%` total loss, not an error and not a `null`. `Net Profit = -Initial Equity` in that case, also a plain, finite, correctly-signed number.

### 21.2 Annualized Return

(ED-7) Trading-day-count basis, consistent with Sharpe's 252/year convention:

```text
N = number of daily bars from the first to the last DailyEquity row, inclusive, minus 1
    (i.e. the number of elapsed trading-day periods)

if N <= 0:
    Annualized Return = null
elif Total Return <= -1:
    Annualized Return = null
else:
    Annualized Return = (1 + Total Return) ** (252 / N) - 1
```

`Total Return < -1` cannot occur ([21.1](#211-basic-metrics): `Final Equity >= 0` and `Initial Equity > 0`, so `Total Return >= -1` always), so this branch's only reachable case is `Total Return == -1` exactly — a total wipeout ([21.11](#2111-zero-equity-and-division-safety)). At that exact boundary, `(1 + Total Return) ** (252 / N)` is `0 ** (252/N)`, which is mathematically well-defined (`0`, since `N > 0` here) rather than undefined — this branch returns `null` anyway, by deliberate convention rather than mathematical necessity: annualizing "lost everything" the same way regardless of whether the wipeout happened on day 2 or day 300 of the backtest would misrepresent very different situations with the same number, so this metric is intentionally left unreported (`null`) for a total wipeout rather than computed as a technically-valid but misleading `-100%/year`.

### 21.3 Sharpe Ratio

(ED-6, BLUEPRINT.md 12.1)

`annual_risk_free_rate > -1` is required (validated as `422 INVALID_RISK_FREE_RATE`, [17.5](#175-numeric-and-zero-equity-validation)) — `(1 + rate)` must be strictly positive for the fractional-exponent conversion below to be real-valued.

`DailyEquity.equity` can legitimately equal exactly `0` ([21.11](#2111-zero-equity-and-division-safety)) — it can never go negative, but zero is reachable without short selling or negative cash. `daily_returns[i] = DailyEquity[i].equity / DailyEquity[i-1].equity - 1` divides by `DailyEquity[i-1].equity`, so this denominator must be checked **before** any division is attempted:

```text
if any(DailyEquity[i-1].equity <= 0 for i in 1..N):
    Sharpe Ratio = null     # a required daily-return denominator is <= 0 -- never divide by zero
else:
    daily_returns[i] = DailyEquity[i].equity / DailyEquity[i-1].equity - 1   for i = 1..N
    rf_daily = (1 + annual_risk_free_rate) ** (1/252) - 1    # if annual_risk_free_rate == 0, rf_daily = 0
    excess[i] = daily_returns[i] - rf_daily

    mean_excess = mean(excess)
    std_excess  = population_or_sample_stdev(excess)   # sample stdev (ddof=1), standard for finance metrics

    if len(excess) < 2:
        Sharpe Ratio = null                       # "too few returns"
    elif std_excess == 0:
        Sharpe Ratio = 0 if mean_excess == 0 else null   # flat equity => 0; nonzero mean with zero
                                                           # variance is a degenerate/undefined case => null
    else:
        Sharpe Ratio = (mean_excess / std_excess) * sqrt(252)
```

Once past the denominator guard above, `DailyEquity[i].equity` (the numerator, for `i = 1..N`) may still be `0` — that is fine and requires no special case, since `0 / positive - 1 = -1` is an ordinary, finite `daily_returns[i]` value (a `-100%` day), not a division-by-zero. Only a **denominator** of `0` (or, since equity is never negative, an impossible-but-checked-anyway negative one) is a division hazard, which is exactly what the guard above rules out before `daily_returns` is computed at all.

### 21.4 Maximum Drawdown

(ED-8) Computed from Daily Close Equity:

```text
running_peak[t] = max(Initial Equity, equity[0..t])   # seeded with Initial Equity (17.1)
drawdown[t] = equity[t] / running_peak[t] - 1        # always <= 0
Maximum Drawdown = min(drawdown[0..T])                # most negative value, stored as a non-positive Decimal
```

The running peak is **seeded with `Initial Equity`** ([17.1](#171-initial-portfolio)) before the first daily equity is folded in. `equity[0]` is day-one **close** equity after day-one trading, which is not in general equal to `Initial Equity` and can even be exactly `0` ([21.11](#2111-zero-equity-and-division-safety)) — so seeding from `equity[0]` would both misreport a day-one loss as a fresh peak (`drawdown[0] = 0` even when day one closed below starting capital) and divide by zero in the day-one-wipeout case. With the `Initial Equity` seed, the division by `running_peak[t]` never divides by zero: `running_peak[t] >= Initial Equity > 0` for every `t`, since `Initial Equity > 0` is enforced at request-validation time ([21.1](#211-basic-metrics), `ZERO_INITIAL_EQUITY`) and `running_peak` is a running maximum that can only stay at or above that seed. This holds regardless of what `equity[t]` itself does later.

`equity[t]` (the numerator) can still be `0` on some day `t` ([21.11](#2111-zero-equity-and-division-safety)) — when it is, `drawdown[t] = 0 / running_peak[t] - 1 = -1` exactly, a `-100%` drawdown from peak, which is an ordinary, well-defined value, not an error. Consequently `Maximum Drawdown` can legitimately equal `-1` (a full wipeout from the peak at some point in the backtest) — this is a valid, representable metric value, not a `null`/`N/A` case.

`DailyEquity.drawdown` stores `drawdown[t]` for every day (per BLUEPRINT.md's `DailyEquity` table), and `Maximum Drawdown` (the summary metric) is the minimum of that column.

### 21.5 Commission, Slippage, Trade Counts

```text
Total Commission     = sum(commission for all EXECUTED trades)
Total Slippage Cost  = sum(slippage_cost for all EXECUTED trades)      (18.4)
Executed Trades      = count(trades where status == EXECUTED)
Skipped Trades       = count(trades where status == SKIPPED)
Buy Count             = count(EXECUTED trades where side == BUY)
Sell Count            = count(EXECUTED trades where side == SELL)
```

### 21.6 Zone-Day Counts

(BLUEPRINT.md 12.2) Using each day's **Close** to classify zone, over the Daily Close Equity / DailyEquity series:

```text
Days Closed in A Zone            = count(days where zone_at_close == IN_A)
Days Closed in C Zone            = count(days where zone_at_close == IN_C)
Days Closed Outside C Boundary   = count(days where zone_at_close == OUTSIDE_C)
```

### 21.7 A/C Zone Entry Counts

```text
A/C zone entry counts = { "ENTER_C_ZONE": count, "EXIT_C_ZONE": count,
                           "OUTSIDE_C_BOUNDARY": count, "RETURN_INSIDE_C_BOUNDARY": count }
```

Counted directly from `ZoneEvent` rows for the backtest run, grouped by `event_type`.

### 21.8 Buy-and-Hold Benchmark Metrics

Each benchmark reuses the same formulas in [21.1](#211-basic-metrics)–[21.4](#214-maximum-drawdown) applied to its own equity series (`equity_b1[t]` / `equity_b2[t]`), with no commission/slippage/trade counts (Benchmark 1 has none; Benchmark 2 has exactly one day-one buy's worth, reported separately as `benchmark2_day_one_commission` / `benchmark2_day_one_slippage_cost`).

### 21.9 Total Return / Net Profit for Benchmarks

Same formulas as [21.1](#211-basic-metrics), substituting each benchmark's own equity series.

### 21.10 First Return to Initial Share Position

(ED-9) Uses **executed trade events** (`Trade.shares_after` on rows with `status == EXECUTED`, in `event_sequence` order), not end-of-day daily shares. A "return" only means something once the position has actually moved away from `initial_shares` — a backtest that never trades (or whose shares happen to net back to `initial_shares` at end-of-day without ever having been away from it, which cannot happen for an `EXECUTED` trade sequence since every fill changes `shares_after` by a nonzero whole lot) has no "return" to report, only a state that was never disturbed. The previous end-of-day formulation could not express this distinction, and additionally mismatched BLUEPRINT.md's naming and the finer, event-level granularity `Trade`/`EventEquity` already provide elsewhere.

```text
target = initial_shares
has_deviated = false
result = null

for trade in Trades where status == EXECUTED, ordered by trade.event_id.event_sequence:
    if not has_deviated:
        if trade.shares_after != target:
            has_deviated = true
        # the fill that causes the first deviation is never itself a "return"
        continue
    if trade.shares_after == target:
        result = {
            equity: trade.equity_after,   # 16.4's exact formula: cash_after + shares_after *
                                           # canonical_grid_price -- never execution_price
            days: elapsed_trading_days(trade.event_id.date),
        }
        break

if result is null:
    First Return to Initial Share Position Equity = null
    Days Until First Return to Initial Share Position = null
else:
    First Return to Initial Share Position Equity = result.equity
    Days Until First Return to Initial Share Position = result.days
```

`First Return to Initial Share Position Equity` is therefore always `trade.equity_after` for the qualifying trade — the exact value defined in [16.4](#164-tradeequity_after-and-eventequityequity-exactly): `cash_after + shares_after * canonical_grid_price`, marked at that trade's canonical grid price, not its execution price.

`elapsed_trading_days(date)` = the 0-indexed position of `date` within the backtest's sorted Bar dates (the same trading-day index used for `Days Closed in A Zone` and its siblings, [21.6](#216-zone-day-counts)), i.e. the number of trading days between the backtest start date and the trade's date. Two return values are `null` together, in exactly two cases:
- **Never deviates**: no `EXECUTED` trade ever changes `shares_after` away from `initial_shares` (includes the zero-trade case).
- **Never returns**: the position deviates at least once but no later `EXECUTED` trade brings `shares_after` back to exactly `initial_shares` before the backtest ends.

### 21.11 Zero-Equity and Division Safety

`cash` can never go negative ([17.3](#173-constraints), [17.5](#175-numeric-and-zero-equity-validation)) and there is no short selling, so `shares >= 0` and `cash >= 0` always, and therefore `equity = cash + shares * price >= 0` always (`price > 0` is guaranteed by [5.2](#52-row-validity-rules)'s cleaning-time validation). **Equity can never go negative — but it is not true that equity can never reach exactly zero**, and no earlier section should be read as claiming otherwise.

`equity == 0` requires `cash == 0` **and** `shares == 0` simultaneously (if `shares > 0`, `shares * price > 0` since `price > 0`, so `equity > 0` regardless of `cash`; if `shares == 0`, `equity == cash`, so `equity == 0` iff `cash == 0` too). This is reachable without short selling or negative cash — for example: `initial_cash = 0`, `initial_shares > 0` (a valid configuration, since `Initial Equity = initial_shares * mark_price[0] > 0`), and a sequence of `SELL` fills that liquidates the entire position, where the last fill's `notional` happens to exactly equal its `commission` (e.g. a `fixed_fee` commission component configured to match that trade's notional) — `cash += (notional - commission)` adds exactly `0`, leaving `cash == 0` and `shares == 0` together. From that point on, no further trade can execute (a `BUY` needs `cash > 0` to afford even a fractional cost above `0`; a `SELL` needs `shares > 0`), so `equity` stays at exactly `0` for the remainder of the backtest.

This is a real, constructible case (not just a theoretical one — combinatorial optimization sweeps and property-based tests routinely produce fee configurations at exactly this kind of boundary), so every metric formula that divides using an equity value **must** treat `0` correctly rather than assume it cannot occur:

| Formula | Divides by | Zero-safety |
|---|---|---|
| Total Return ([21.1](#211-basic-metrics)) | `Initial Equity` | `Initial Equity > 0` is enforced at validation time (`ZERO_INITIAL_EQUITY`) — this denominator is never zero. `Final Equity == 0` is allowed and yields `Total Return == -1` exactly. |
| Annualized Return ([21.2](#212-annualized-return)) | — (exponentiation, not division) | No division; the `Total Return <= -1` branch returns `null` by convention, not because the underlying arithmetic is unsafe. |
| Sharpe Ratio ([21.3](#213-sharpe-ratio)) | `DailyEquity[i-1].equity`, `std_excess` | Guarded explicitly: `null` if any required `DailyEquity[i-1].equity <= 0` before any division is attempted; separately guarded for `std_excess == 0`. |
| Maximum Drawdown ([21.4](#214-maximum-drawdown)) | `running_peak[t]` | `running_peak[t] >= Initial Equity > 0` always (a running max starting from a positive value) — this denominator is never zero, regardless of what `equity[t]` does. |
| Benchmark 1/2 equivalents ([21.9](#219-total-return-net-profit-for-benchmarks)) | Same formulas, applied to `equity_b1[t]`/`equity_b2[t]` | Both benchmark equity series share the same `initial_cash`/`initial_shares` as the strategy and either never trade again (Benchmark 1) or trade exactly once, on day one (Benchmark 2, [20.2](#202-benchmark-2-invest-available-cash-on-day-one)) — under those constraints `equity_b1[t]`/`equity_b2[t]` can be shown to stay strictly positive for every `t` (unlike the actively-traded strategy series, which can reach exactly zero as shown above), but the same guards apply uniformly regardless; no formula special-cases "benchmark" vs. "strategy" equity. |

No metric function in this document divides by a quantity without either a validation-time guarantee that it is positive, or an explicit runtime check immediately before the division. Any future metric added to this list must extend this table with its own zero-safety argument, not assume equity positivity by default.

---

## 22. Event-Level and Daily Equity

### 22.1 Two Series (BLUEPRINT.md 12.3)

| Series | Granularity | Purpose |
|---|---|---|
| **Daily Close Equity** (`DailyEquity`) | One row per Bar (date) | Canonical metrics (Sharpe, Max DD, Annualized Return, zone-day counts), dashboard default view. |
| **Event-Level Equity** (`EventEquity`) | One row per Trade or ZoneEvent | Fine-grained equity curve for the event/trade-level chart. |

### 22.2 Daily Equity Calculation

`capture_daily_equity` is called inline, during path processing, at exactly the points [11.6](#116-event-date-attribution-and-daily-equity-capture-point) defines — not reconstructed after the fact from a separately-built `(date -> cash, shares)` lookup. This is what guarantees each `DailyEquityRow` reflects `state.cash`/`state.shares` as they stood the instant that `Bar`'s own final point was reached, strictly before any later segment (including the overnight gap leading into the next `Bar`) could change them further:

```python
def capture_daily_equity(bar_date: date, bar_close: Decimal, state: EngineState) -> None:
    cash, shares = state.cash, state.shares   # as of right now -- the caller in 11.3 guarantees
                                               # this is exactly after bar_date's final segment
    equity = cash + shares * bar_close
    state.running_peak = max(state.running_peak, equity)   # initialized to initial_equity
                                                            # (17.1/21.4) at run start, never to
                                                            # the first captured equity
    drawdown = equity / state.running_peak - 1        # 21.4 -- running_peak >= initial_equity > 0
    zone_at_close = classify(bar_close)                # 7.5
    state.daily_equity_rows.append(DailyEquityRow(date=bar_date, close=bar_close, cash=cash,
                                                    shares=shares, equity=equity, drawdown=drawdown,
                                                    zone_at_close=zone_at_close))
```

`state.daily_equity_rows` accumulates exactly one row per `Bar`, in date order, because [11.3](#113-segment-processing-algorithm)'s loop calls this exactly once per `Bar` — either from the one-time check before the loop (`CLOSE_ONLY` mode's `Bar 0` only) or from the `if end.is_bar_final` check inside it (every other case, both modes) — never zero times, never more than once.

### 22.3 Event Equity Calculation

One `EventEquity` row is emitted immediately after every `Trade` (executed or skipped — skipped trades still get a row since cash/shares didn't change, for a continuous timeline) and every `ZoneEvent`, using `backtest_event.market_price` and the engine state (`cash`/`shares`) immediately after that event — the exact formula, `equity = cash + shares * backtest_event.market_price`, is defined once in [16.4](#164-tradeequity_after-and-eventequityequity-exactly), which also covers the parallel `Trade.equity_after` formula and why the two always agree for a `Trade`-linked event. Concretely, emitting any of these three rows for a given occurrence is a single transaction: insert one `backtest_events` row (allocating the next `event_sequence` for the run — [23.5](#235-backtest_events)), then insert the `Trade` or `ZoneEvent` row referencing that event's `id`, then insert the `EventEquity` row referencing the **same** `id`. This is what makes `event_sequence` a genuine single global order across `Trade`, `ZoneEvent`, and `EventEquity` together, enforced by `backtest_events`'s `UNIQUE (backtest_run_id, event_sequence)` constraint rather than by convention.

---

## 23. Database Schema

PostgreSQL. All monetary/price columns `NUMERIC(20,8)`. All timestamps `TIMESTAMPTZ`; all pure calendar dates `DATE`. All tables have `id BIGSERIAL PRIMARY KEY` unless noted.

**Delete behavior is `ON DELETE CASCADE` by default, with exactly two `ON DELETE RESTRICT` exceptions:**

- `price_bars.dataset_id → datasets.id`: `CASCADE` — deleting a `Dataset` deletes its `PriceBar` rows.
- `backtest_events.backtest_run_id → backtest_runs.id`: `CASCADE`, and `trades.event_id` / `zone_events.event_id` / `event_equity.event_id → backtest_events.id`: `CASCADE` — deleting a `BacktestRun` deletes its `backtest_events` rows, which in turn deletes each one's single `Trade`/`ZoneEvent`/`EventEquity` child.
- `daily_equity.backtest_run_id → backtest_runs.id`: `CASCADE` — deleting a `BacktestRun` deletes its `DailyEquity` rows.
- `optimization_results.optimization_job_id → optimization_jobs.id`: `CASCADE` — deleting an `OptimizationJob` deletes its `OptimizationResult` rows.
- `datasets.user_id`, `backtest_runs.user_id`, `optimization_jobs.user_id → users.id`: `CASCADE` — deleting a `User` deletes everything they own, since BLUEPRINT.md defines no soft-delete/retention requirement.
- **`backtest_runs.dataset_id → datasets.id`: `RESTRICT`** — a `Dataset` cannot be deleted while any `BacktestRun` references it.
- **`optimization_jobs.dataset_id → datasets.id`: `RESTRICT`** — a `Dataset` cannot be deleted while any `OptimizationJob` references it.

These two `RESTRICT` constraints are what `DELETE /api/datasets/{dataset_id}` ([25.2](#252-datasets)) relies on for `409 DATASET_IN_USE` — the database itself refuses the delete; the API layer either pre-checks for referencing rows to return a clean `409` before attempting the delete, or catches the resulting foreign-key-violation and translates it to the same `409`. **Deleting a `Dataset` never deletes, and never cascades into deleting, any `BacktestRun` or `OptimizationJob` row** (nor, transitively, their `Trade`/`ZoneEvent`/`EventEquity`/`DailyEquity`/`OptimizationResult` rows) — those are only ever removed by deleting the `BacktestRun`/`OptimizationJob` itself (which cascades independently, as listed above) or the owning `User`. A `Dataset` can only be deleted once it has zero referencing `BacktestRun` and `OptimizationJob` rows.

### 23.1 `users`

| Column | Type | Constraints |
|---|---|---|
| id | BIGSERIAL | PK |
| email | TEXT | UNIQUE NOT NULL |
| password_hash | TEXT | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

Index: unique on `lower(email)`.

### 23.2 `datasets`

| Column | Type | Constraints |
|---|---|---|
| id | BIGSERIAL | PK |
| user_id | BIGINT | FK → users.id, NOT NULL, indexed |
| name | TEXT | NOT NULL |
| source_type | TEXT | NOT NULL, CHECK IN ('TDX_XLS','CSV') |
| original_filename | TEXT | NOT NULL |
| security_name | TEXT | NULL |
| security_code | TEXT | NULL |
| data_mode | TEXT | NOT NULL, CHECK IN ('OHLCV','CLOSE_ONLY') |
| start_date | DATE | NOT NULL |
| end_date | DATE | NOT NULL |
| row_count | INTEGER | NOT NULL |
| column_mapping | JSONB | NOT NULL |
| cleaning_summary | JSONB | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

Index: `(user_id, created_at DESC)`.

### 23.3 `price_bars`

| Column | Type | Constraints |
|---|---|---|
| id | BIGSERIAL | PK |
| dataset_id | BIGINT | FK → datasets.id, NOT NULL, indexed |
| date | DATE | NOT NULL |
| open | NUMERIC(20,8) | NULL |
| high | NUMERIC(20,8) | NULL |
| low | NUMERIC(20,8) | NULL |
| close | NUMERIC(20,8) | NOT NULL, CHECK (close > 0) |
| volume | NUMERIC(20,8) | NULL, CHECK (volume IS NULL OR volume >= 0) |

Constraints: `UNIQUE (dataset_id, date)`. Index: `(dataset_id, date)`.

### 23.4 `backtest_runs`

| Column | Type | Constraints |
|---|---|---|
| id | BIGSERIAL | PK |
| user_id | BIGINT | FK → users.id, NOT NULL, indexed |
| dataset_id | BIGINT | FK → datasets.id, NOT NULL, indexed |
| name | TEXT | NOT NULL |
| status | TEXT | NOT NULL, CHECK IN ('PENDING','RUNNING','COMPLETED','FAILED'), DEFAULT 'PENDING' |
| configuration | JSONB | NOT NULL — full strategy config (baseline, A/C, grid, fees, slippage, tick, OHLC path mode, lot size, initial cash/shares) |
| ohlc_path_mode | TEXT | NULL, CHECK IN ('HIGH_FIRST','LOW_FIRST','AUTO') |
| start_date | DATE | NOT NULL |
| end_date | DATE | NOT NULL |
| result_metrics | JSONB | NULL — populated on COMPLETED |
| error_message | TEXT | NULL — populated on FAILED |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| completed_at | TIMESTAMPTZ | NULL |

Index: `(user_id, created_at DESC)`, `(dataset_id)`.

### 23.5 `backtest_events`

The single, database-enforced global ordering backbone for everything that happens during a `BacktestRun`. Every `Trade` and every `ZoneEvent` — and, in turn, every `EventEquity` row — is created by first inserting exactly one `backtest_events` row (which allocates the next `event_sequence` for that `backtest_run_id`) and then inserting its one corresponding child row referencing that event's `id`. Both inserts happen in the same transaction, so the pair is atomic; there is no window where an event row exists without its child, or vice versa.

| Column | Type | Constraints |
|---|---|---|
| id | BIGSERIAL | PK |
| backtest_run_id | BIGINT | FK → backtest_runs.id, NOT NULL, indexed |
| event_sequence | INTEGER | NOT NULL |
| event_type | TEXT | NOT NULL, CHECK IN ('TRADE','ZONE_EVENT') — coarse kind; the specific side/status or zone-transition type lives on the child row (`trades`/`zone_events`), reached via that child's `event_id` |
| date | DATE | NOT NULL |
| market_price | NUMERIC(20,8) | NOT NULL — the market price at the instant of this event (grid price for a trade attempt, boundary price for a zone event) |

Constraints: `UNIQUE (backtest_run_id, event_sequence)`. Index: `(backtest_run_id, date)`.

**Why this replaces the previous per-table unique constraints:** `trades` and `zone_events` previously each had their own `UNIQUE (backtest_run_id, event_sequence)`, which only guarantees uniqueness *within* each table — nothing stopped a `Trade` and a `ZoneEvent` from independently being assigned the same `event_sequence` value for the same `backtest_run_id`, silently breaking the "one global chronological order across both tables" invariant that `event_sequence` is defined to provide ([1](#1-terminology-and-domain-definitions)). Routing every event through one `backtest_events` row with a single `UNIQUE (backtest_run_id, event_sequence)` constraint makes cross-table uniqueness a database guarantee rather than an application-level convention.

### 23.6 `trades`

`trades` has no `backtest_run_id` or `date` column of its own. Both are already on the row's parent `backtest_events` ([23.5](#235-backtest_events)), reached through `event_id`; duplicating them here would create two copies of the same fact that could disagree, and "written in the same transaction" is an application-level habit, not something the database enforces — it does not stop a future bug (a bad migration, a manual `UPDATE`, an ORM misconfiguration) from writing a `trades.backtest_run_id` that no longer matches `backtest_events.backtest_run_id` for the same `event_id`. Every query that needs a `Trade`'s run or date joins to `backtest_events` via `event_id`:

```sql
SELECT t.*, be.backtest_run_id, be.date, be.event_sequence
FROM trades t
JOIN backtest_events be ON be.id = t.event_id
WHERE be.backtest_run_id = :backtest_run_id
ORDER BY be.event_sequence
```

This is efficient without a denormalized column: `backtest_events` already has an index on `(backtest_run_id, date)` ([23.5](#235-backtest_events)) to drive the `WHERE`/`ORDER BY` above, and `trades.event_id` is itself uniquely indexed for the join's other side.

| Column | Type | Constraints |
|---|---|---|
| id | BIGSERIAL | PK |
| event_id | BIGINT | FK → backtest_events.id, NOT NULL, UNIQUE, indexed |
| side | TEXT | NOT NULL, CHECK IN ('BUY','SELL') |
| grid_price | NUMERIC(20,8) | NOT NULL — the canonical grid price ([9.4](#94-canonical-grid-levels-tick-size-enabled)) |
| execution_price | NUMERIC(20,8) | NULL — null when SKIPPED |
| shares | BIGINT | NOT NULL |
| notional | NUMERIC(20,8) | NULL |
| commission | NUMERIC(20,8) | NULL |
| slippage_cost | NUMERIC(20,8) | NULL |
| cash_after | NUMERIC(20,8) | NOT NULL |
| shares_after | BIGINT | NOT NULL |
| equity_after | NUMERIC(20,8) | NOT NULL — `cash_after + shares_after * canonical_grid_price`, see [16.4](#164-tradeequity_after-and-eventequityequity-exactly) |
| status | TEXT | NOT NULL, CHECK IN ('EXECUTED','SKIPPED') |
| skip_reason | TEXT | NULL, CHECK IN ('INSUFFICIENT_CASH','INSUFFICIENT_SHARES','INSUFFICIENT_CASH_FOR_COMMISSION') |

Constraints: `UNIQUE (event_id)`.

### 23.7 `zone_events`

Same reasoning as [23.6](#236-trades): no `backtest_run_id` or `date` column here either — both come from `backtest_events` via `event_id`, joined the same way.

| Column | Type | Constraints |
|---|---|---|
| id | BIGSERIAL | PK |
| event_id | BIGINT | FK → backtest_events.id, NOT NULL, UNIQUE, indexed |
| event_type | TEXT | NOT NULL, CHECK IN ('ENTER_C_ZONE','EXIT_C_ZONE','OUTSIDE_C_BOUNDARY','RETURN_INSIDE_C_BOUNDARY') |
| price | NUMERIC(20,8) | NOT NULL |

Constraints: `UNIQUE (event_id)`.

### 23.8 `daily_equity`

| Column | Type | Constraints |
|---|---|---|
| id | BIGSERIAL | PK |
| backtest_run_id | BIGINT | FK → backtest_runs.id, NOT NULL, indexed |
| date | DATE | NOT NULL |
| close | NUMERIC(20,8) | NOT NULL |
| cash | NUMERIC(20,8) | NOT NULL |
| shares | BIGINT | NOT NULL |
| equity | NUMERIC(20,8) | NOT NULL |
| drawdown | NUMERIC(20,8) | NOT NULL |
| zone_at_close | TEXT | NOT NULL, CHECK IN ('IN_A','IN_C','OUTSIDE_C') |

Constraints: `UNIQUE (backtest_run_id, date)`. `daily_equity` has no `event_id` — it is one row per Bar/date, not one row per event ([22.1](#221-two-series-blueprintmd-123)), so it is intentionally outside the `backtest_events` sequencing model; `backtest_run_id`/`date` are this table's own primary facts, not a copy of something owned elsewhere, so there is no denormalization concern here.

### 23.9 `event_equity`

Same reasoning as [23.6](#236-trades): no `backtest_run_id`, `date`, or `market_price` column here — `market_price` in particular is the price recorded on the parent `backtest_events` row at the instant of the event ([23.5](#235-backtest_events)), and duplicating it onto `event_equity` would be the same two-copies-that-could-disagree problem for a third field, not just `backtest_run_id`/`date`.

| Column | Type | Constraints |
|---|---|---|
| id | BIGSERIAL | PK |
| event_id | BIGINT | FK → backtest_events.id, NOT NULL, UNIQUE, indexed |
| cash | NUMERIC(20,8) | NOT NULL |
| shares | BIGINT | NOT NULL |
| equity | NUMERIC(20,8) | NOT NULL — `cash + shares * backtest_event.market_price`, see [16.4](#164-tradeequity_after-and-eventequityequity-exactly) |

Constraints: `UNIQUE (event_id)`.

### 23.10 `optimization_jobs`

| Column | Type | Constraints |
|---|---|---|
| id | BIGSERIAL | PK |
| user_id | BIGINT | FK → users.id, NOT NULL, indexed |
| dataset_id | BIGINT | FK → datasets.id, NOT NULL, indexed |
| status | TEXT | NOT NULL, CHECK IN ('PENDING','RUNNING','COMPLETED','CANCELLED','FAILED'), DEFAULT 'PENDING' |
| search_configuration | JSONB | NOT NULL |
| train_test_configuration | JSONB | NOT NULL |
| rank_metric | TEXT | NOT NULL — one of [35](#35-ranking-directions-and-missing-value-behavior)'s metric keys |
| rank_direction | TEXT | NOT NULL, CHECK IN ('ASC','DESC') — resolved at creation time from the request or from [35](#35-ranking-directions-and-missing-value-behavior)'s default for `rank_metric` |
| generated_count | INTEGER | NOT NULL — raw Cartesian-product size, before validation ([33.8](#338-invalid-combination-handling)) |
| valid_count | INTEGER | NOT NULL — combinations that passed per-combination validation |
| excluded_count | INTEGER | NOT NULL — `generated_count - valid_count` |
| total_combinations | INTEGER | NOT NULL — equals `valid_count`; the progress denominator |
| progress | INTEGER | NOT NULL DEFAULT 0 — valid combinations completed |
| current_combination | JSONB | NULL |
| current_best | JSONB | NULL |
| estimated_remaining_seconds | INTEGER | NULL |
| cancel_requested | BOOLEAN | NOT NULL DEFAULT false |
| error_message | TEXT | NULL |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| started_at | TIMESTAMPTZ | NULL |
| completed_at | TIMESTAMPTZ | NULL |

### 23.11 `optimization_results`

| Column | Type | Constraints |
|---|---|---|
| id | BIGSERIAL | PK |
| optimization_job_id | BIGINT | FK → optimization_jobs.id, NOT NULL, indexed |
| combination_key | TEXT | NOT NULL — deterministic hash of the normalized `parameter_combination`, [33.9](#339-celery-retry-and-result-idempotency) |
| parameter_combination | JSONB | NOT NULL |
| training_metrics | JSONB | NOT NULL |
| testing_metrics | JSONB | NOT NULL |
| training_rank | INTEGER | NULL |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

Constraints: `UNIQUE (optimization_job_id, combination_key)` — this is what makes a duplicate `save(result)` for the same combination (e.g. from a retried Celery task, [33.9](#339-celery-retry-and-result-idempotency)) a database-rejected write rather than a silent duplicate row. Index: `(optimization_job_id, training_rank)`.

Migrations are managed with Alembic from the first database milestone (BLUEPRINT.md 15), one migration per schema change, never hand-edited after being applied to a shared environment.

---

## 24. Authentication and Ownership

### 24.1 Mechanism

JWT, `HS256`, signed with a server-side secret from environment variables ([37](#37-security-and-environment-variables)). Access token delivered via a `Secure` (in production; omitted only for local `http://localhost` development), `HttpOnly` cookie scoped to `Path=/api`. `SameSite=Lax` is only correct under the same-origin deployment architecture in [24.5](#245-production-cookie-and-csrf-architecture) — see that section for the cross-site alternative and why the two require different `SameSite`/CORS/CSRF settings.

### 24.2 Registration Rules

(ED-17) Email: must pass a standard email-format check; must be unique (case-insensitive, enforced by the `lower(email)` unique index). Password: minimum 8 characters; hashed with Argon2id before storage; plaintext is never logged or persisted. No additional complexity rules in V2 (scope-appropriate for a portfolio project, not a production consumer product).

### 24.3 Token and Cookie Rules

(ED-16) Access-token expiry: 24 hours by default, configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`. No refresh-token flow in V2 — on expiry, the user must log in again (BLUEPRINT.md does not request refresh tokens; adding one would be scope beyond what's specified). Token payload: `{ "sub": user_id, "exp": ..., "iat": ... }` — no email or other PII in the token body.

### 24.4 Ownership Enforcement

Every request to a dataset-, backtest-, export-, or optimization-scoped endpoint resolves the resource, then checks `resource.user_id == current_user.id`; a mismatch returns `404 NOT_FOUND` (not `403`), so resource existence is never leaked to non-owners.

### 24.5 Production Cookie and CSRF Architecture

The Next.js frontend and the FastAPI backend can be deployed either **same-origin** (frontend proxies API calls) or **cross-site** (browser talks to the API's own domain directly). These require materially different cookie/CORS/CSRF settings, and using the wrong combination is a real vulnerability (e.g. `SameSite=Lax` on a cookie the browser must actually send cross-site simply fails silently — the user appears logged out on every request — while `SameSite=None` without CSRF protection is exploitable). Exactly one of the two architectures below is used per deployment; they are not mixed.

**Preferred: same-origin via a Next.js `/api` proxy.** The browser only ever talks to the Next.js origin (e.g. `https://app.example.com`). Next.js (API routes or middleware, running server-side) forwards every `/api/*` request to the actual FastAPI backend (e.g. an internal service URL or a separate `https://api.example.com` the browser never sees directly), passing the cookie through on the server-to-server hop and relaying the response back to the browser unchanged.

- The auth cookie is set with no explicit `Domain` (defaults to the Next.js origin) and `SameSite=Lax` ([24.1](#241-mechanism)) — correct and sufficient, because every browser-initiated request carrying the cookie is same-origin by construction; there is no cross-site cookie-sending case to fail.
- CORS is not needed at all for browser traffic (same-origin requests don't trigger CORS); the FastAPI backend can restrict itself to accepting requests only from the Next.js server's own IP/network if it wants defense-in-depth, since the browser never reaches it directly.
- CSRF exposure is reduced to the standard same-site baseline that `SameSite=Lax` already mitigates (blocks cookie-bearing cross-site `POST`s); no additional CSRF token is required for V2, consistent with `SameSite=Lax`'s guarantees for a portfolio-scope project ([24.2](#242-registration-rules)'s stated scope precedent).
- This is the default architecture this document assumes unless a deployment explicitly opts into the alternative below, and is the one [37](#37-security-and-environment-variables)'s `CORS_ALLOWED_ORIGINS` variable is largely moot for (it still guards any direct, non-browser access to the FastAPI origin).

**Alternative: genuinely cross-site (browser calls the API domain directly).** If the frontend and backend are deployed as separate origins the browser talks to directly (no proxy hop), the cookie must be sent cross-site, which requires:

- `SameSite=None; Secure` on the access-token cookie (`SameSite=None` is mandatory for the browser to attach the cookie to a cross-site request at all; `Secure` is mandatory alongside `SameSite=None` per the cookie spec — this combination is not optional in this architecture, unlike the local-development exception noted in [24.1](#241-mechanism), which does not apply once `SameSite=None` is in use).
- **Credentialed CORS**: `Access-Control-Allow-Origin` echoing the specific frontend origin (never `*`, which is incompatible with credentials) and `Access-Control-Allow-Credentials: true`, sourced from `CORS_ALLOWED_ORIGINS` ([37](#37-security-and-environment-variables)) — an explicit allowlist, not a wildcard.
- **Mandatory CSRF protection**, because `SameSite=None` deliberately gives up the cross-site request blocking that `Lax`/`Strict` provide, reopening the classic cookie-based CSRF vector. This uses the double-submit cookie pattern: a second cookie, `csrf_token` (readable by JavaScript, i.e. **not** `HttpOnly`, `SameSite=None`, `Secure`), holding a random value issued alongside the access token at login; every state-changing request (`POST`/`PATCH`/`DELETE`) must echo that value back in an `X-CSRF-Token` request header, and the backend rejects the request with `403` unless the header matches the cookie. Because a cross-site attacker page cannot read the victim's cookies (only the browser can attach them), it cannot produce a matching header value, so the forged request fails the check even though the browser still attaches the (now cross-site) auth cookie.
- This architecture is only chosen if same-origin proxying is genuinely not viable for the deployment target; it carries strictly more moving parts (CORS allowlist, a second cookie, a header the frontend must remember to set on every mutating call) than the preferred architecture above, for no functional benefit to this product.

---

## 25. API Endpoints and Schemas

All request/response bodies are JSON except file upload (`multipart/form-data`) and CSV/PDF export downloads (binary/`text/csv`/`application/pdf`). All authenticated endpoints require the access-token cookie; missing/invalid → `401 UNAUTHENTICATED`.

### 25.1 Authentication

**`POST /api/auth/register`**
```json
// request
{ "email": "user@example.com", "password": "min-8-chars" }
// response 201
{ "id": 1, "email": "user@example.com", "created_at": "2026-07-15T00:00:00Z" }
```
Errors: `422 VALIDATION_ERROR` (bad email/short password), `409 EMAIL_ALREADY_REGISTERED`.

**`POST /api/auth/login`**
```json
// request
{ "email": "user@example.com", "password": "..." }
// response 200 (+ sets access-token cookie)
{ "id": 1, "email": "user@example.com" }
```
Errors: `401 INVALID_CREDENTIALS`.

**`POST /api/auth/logout`** → `204 No Content` (clears cookie).

**`GET /api/auth/me`** → `200 { "id": 1, "email": "..." }` or `401 UNAUTHENTICATED`.

### 25.2 Datasets

**`POST /api/datasets/preview`** — `multipart/form-data`: `file`, optional `manual_mapping` (JSON string), optional `ohlc_path_hint` (unused at preview time, reserved). Does **not** persist the raw file or any rows.
```json
// response 200
{
  "detected_format": "TDX_XLS",
  "detected_encoding": "gb18030",
  "auto_column_mapping": { "date": "时间", "open": "开盘", "high": "最高", "low": "最低", "close": "收盘", "volume": "成交量" },
  "security_name": "某ETF",
  "security_code": "159825",
  "data_mode": "OHLCV",
  "preview_rows": [ { "date": "2020-01-02", "open": "1.234", "...": "..." } ],
  "bad_rows": [ { "row_number": 12, "reason": "NON_POSITIVE_PRICE", "raw": {"...": "..."} } ],
  "duplicate_rows": [ { "date": "2020-03-05", "kept": {"...":"..."}, "discarded": [{"...":"..."}] } ],
  "cleaning_summary": { "...": "see 5.4" },
  "column_mapping_used": { "date": "时间", "open": "开盘", "...": "..." },
  "preview_token": "opaque-server-side-token-referencing-cached-cleaned-rows"
}
```

**`preview_token` binding.** The server-side cache entry a `preview_token` points to (short-lived, 30 min TTL) is keyed to the exact triple that produced it: the decoded source content (hash of the decoded text, not just the filename), the column mapping actually applied (`auto_column_mapping`, or `manual_mapping` if supplied — this is echoed back verbatim as `column_mapping_used` so the frontend always knows exactly which mapping a given token represents), and the resulting cleaned-row set / `cleaning_summary`. A `preview_token` is therefore valid for **one** mapping only — it is never reinterpreted against a different mapping later. If the user edits the column mapping after the wizard's `MAPPING` step has already called this endpoint once (e.g. correcting an auto-detected field), the frontend **must** call `POST /api/datasets/preview` again with the corrected `manual_mapping` before advancing past `MAPPING`; the response is a fresh `preview_token` (and a fresh cleaning result, since re-mapping can change which rows are bad/duplicate). The stale token from the first call is simply left to expire — it is never "patched" or re-cleaned in place. See [28](#28-upload-wizard-states)'s updated `MAPPING` transition.

Errors: `400 UNSUPPORTED_FILE_TYPE`, `400 ENCODING_DETECTION_FAILED`, `400 HEADER_NOT_FOUND`, `400 MISSING_REQUIRED_COLUMN`.

**`POST /api/datasets`**
```json
// request
{ "name": "My Dataset", "preview_token": "opaque-..." }
// response 201
{ "id": 42, "name": "My Dataset", "data_mode": "OHLCV", "start_date": "2020-01-02",
  "end_date": "2021-12-31", "row_count": 475, "created_at": "..." }
```
This endpoint takes **only** `name` and `preview_token` — it does **not** accept a separate `column_mapping` field. The `column_mapping` persisted onto the new `Dataset` row, and the rows persisted as `PriceBar`, are exactly the mapping and cleaned rows already baked into the `preview_token`'s cache entry, verbatim — there is no "apply this different mapping to the already-cleaned cached rows" code path, because that mapping/cleaning pairing is exactly what the token is bound to (see above). If the mapping shown in the wizard at confirmation time doesn't match what's cached under the token the client is holding, the client is holding a stale token from before the last mapping edit — the fix is a fresh `POST /api/datasets/preview` call, not a parameter on this endpoint.

Errors: `404 PREVIEW_TOKEN_NOT_FOUND` (expired, invalid, or already consumed), `422 VALIDATION_ERROR`.

**`GET /api/datasets`** → `200 { "items": [ {dataset summary}, ... ] }`, owned by current user only.

**`GET /api/datasets/{dataset_id}`** → `200 { full dataset detail incl. cleaning_summary, column_mapping }`; `404` if not found or not owned.

**`DELETE /api/datasets/{dataset_id}`** → `204`; `409 DATASET_IN_USE` if any `BacktestRun` **or** `OptimizationJob` references it (a dataset cannot be deleted while either depends on it — deleting the dataset would silently corrupt reruns, and an `OptimizationJob` re-derives its train/test bars from the dataset on every entry, including a retry, [33.9](#339-celery-retry-and-result-idempotency)). This is the API-level expression of the `ON DELETE RESTRICT` constraints on `backtest_runs.dataset_id` and `optimization_jobs.dataset_id` ([23](#23-database-schema)) — deleting the dataset itself never cascades into deleting either.

### 25.3 Backtests

**`POST /api/backtests`**
```json
// request
{
  "dataset_id": 42,
  "name": "159825 — A Grid 2% — 2026-07-15",      // optional, auto-generated if omitted
  "configuration": {
    "initial_cash": "100000.00", "initial_shares": 0, "lot_size": 100, "trade_lots": 1,
    "baseline": null,                              // null = default (first Close)
    "a_distance": { "mode": "PERCENT", "value": "0.05" },
    "c_distance": { "mode": "PERCENT", "value": "0.15" },
    "grid_step":  { "mode": "PERCENT", "value": "0.01" },
    "tick_size": { "enabled": false, "value": null },
    "ohlc_path_mode": "AUTO",
    "buy_commission":  { "rate_enabled": true, "rate": "0.0003", "minimum_enabled": true, "minimum": "5.00", "fixed_enabled": false, "fixed": "0" },
    "sell_commission": { "rate_enabled": true, "rate": "0.0003", "minimum_enabled": true, "minimum": "5.00", "fixed_enabled": false, "fixed": "0" },
    "slippage": { "shared": true, "mode": "FIXED", "value": "0.001",
                   "buy": null, "sell": null },
    "risk_free_rate_annual": "0.0"
  }
}
// response 201 (success)
{ "id": 501, "status": "COMPLETED", "name": "159825 — A Grid 2% — 2026-07-15",
  "created_at": "...", "completed_at": "...",
  "result_metrics": { "...": "see 21, populated because status is COMPLETED" } }
```
Validation errors (`422 VALIDATION_ERROR`, with `details` naming the field): `C Distance > A Distance` violated ([7.4](#74-validation)), `INVALID_TRADE_LOTS`, `INVALID_LOT_SIZE`, `NEGATIVE_INITIAL_CASH`, `NEGATIVE_INITIAL_SHARES`, `ZERO_INITIAL_EQUITY`, `NEGATIVE_COMMISSION_COMPONENT`, `NEGATIVE_SLIPPAGE`, `NON_POSITIVE_TICK_SIZE`, `INVALID_RISK_FREE_RATE` (all per [17.5](#175-numeric-and-zero-equity-validation)), grid too dense ([8.5](#85-grid-level-count-safety-cap)), grid collapses after tick rounding ([9.4](#94-canonical-grid-levels-tick-size-enabled)). These are all request-validation failures: no `BacktestRun` row is created at all, and the endpoint returns `422` with the standard error envelope ([26](#26-standard-api-error-format)), not a `201` with a `FAILED` run.

Backtests run **synchronously** within the request in V2 (the engine is fast enough for daily-bar data; only *optimization* jobs use the background worker, per BLUEPRINT.md 4.4's stated development order of "synchronous first"). This has two consequences that earlier examples in this document did not consistently reflect, now fixed everywhere:

- **A successful request never returns `PENDING`.** The `BacktestRun` row is created and the engine runs to completion (or fails) inside the same request/transaction, so by the time `POST /api/backtests` returns `201`, `status` is always `COMPLETED` or `FAILED` — never `PENDING`/`RUNNING`. `PENDING`/`RUNNING` remain in the `BacktestRun.status` enum only for schema symmetry with `OptimizationJob.status` and to leave room for a future async path without a migration; they are not reachable via any response from this endpoint.
- **Engine failure (a runtime error inside the backtest engine itself, e.g. [`NON_POSITIVE_EXECUTION_PRICE`](#175-numeric-and-zero-equity-validation) — as opposed to a request-validation failure, which never creates a row at all) still returns `201`**, because the `BacktestRun` resource itself *was* created — it just didn't complete successfully:
  ```json
  // response 201 (engine failure — the row exists, at status FAILED)
  { "id": 501, "status": "FAILED", "name": "159825 — A Grid 2% — 2026-07-15",
    "created_at": "...", "completed_at": "...",
    "error_message": "Sanitized description of the engine failure; full detail logged server-side.",
    "result_metrics": null }
  ```
  The stored `BacktestRun` row matches this exactly: `status = "FAILED"`, `error_message` populated, `result_metrics = null`, `completed_at` set (the run did finish attempting — it just didn't produce a result). This is the same shape [28](#28-upload-wizard-states)'s `RUNNING → FAILED` wizard transition already assumes; that section was correct, the request/response examples here were the ones that needed to catch up.

**`GET /api/backtests`** → paginated list, query params `?search=&limit=&offset=`, owned by current user only.

**`GET /api/backtests/{backtest_id}`** → full detail: configuration, result_metrics, and (if `?include=trades,zone_events,daily_equity,event_equity` query params are given) the associated series, to avoid always shipping potentially thousands of rows. The `trades`, `zone_events`, and `event_equity` entries in the response are each the table's own columns ([23.6](#236-trades)/[23.7](#237-zone_events)/[23.9](#239-event_equity)) plus `date`/`event_sequence` (and, for `event_equity`, `market_price`) joined in from the row's parent `backtest_events` ([23.5](#235-backtest_events)) — the API response is a convenience projection for the frontend; the underlying tables themselves do not store those fields redundantly.

**`PATCH /api/backtests/{backtest_id}`** — rename only: `{ "name": "new name" }` → `200`. Any other field is `422 IMMUTABLE_FIELD`.

**`DELETE /api/backtests/{backtest_id}`** → `204`.

**`POST /api/backtests/{backtest_id}/rerun`** — re-executes the exact same `configuration` against the (possibly updated) dataset, creating a **new** `BacktestRun` row. Like `POST /api/backtests`, this executes synchronously within the request — `201` with the new run at `status: "COMPLETED"` or `status: "FAILED"`, using the same two response shapes shown above.

**`POST /api/backtests/{backtest_id}/duplicate`** — executes immediately and synchronously, exactly like `POST /api/backtests` with a merged configuration; it does **not** create an unexecuted, "saved for later" `BacktestRun`, because nothing else in this API can trigger a saved-but-not-yet-run `BacktestRun` (there is no `POST /api/backtests/{id}/execute` endpoint, and introducing a persisted "configured but not run" state would need one). "Duplicate" means "copy this configuration, apply overrides, and run it as a new backtest" — not "clone the row."
```json
// request (all fields optional overrides)
{ "configuration_overrides": { "a_distance": { "mode": "PERCENT", "value": "0.06" } } }
// response 201: new BacktestRun, already executed — status: "COMPLETED" or "FAILED",
// same two shapes as POST /api/backtests above
```

**`POST /api/backtests/compare`**
```json
// request
{ "backtest_ids": [501, 502, 503] }
// response 200
{ "runs": [ { "id": 501, "name": "...", "result_metrics": {...} }, ... ] }
```
Errors: `404` if any id is not found or not owned (all-or-nothing).

### 25.4 Exports

```text
GET /api/backtests/{backtest_id}/exports/trades.csv    -> text/csv
GET /api/backtests/{backtest_id}/exports/equity.csv    -> text/csv   (Daily Close Equity series)
GET /api/backtests/{backtest_id}/exports/result.json   -> application/json (config + all metrics + benchmarks)
GET /api/backtests/{backtest_id}/exports/report.pdf    -> application/pdf (generated on demand, not cached/stored)
```
All require ownership; `404` otherwise. `trades.csv`/`equity.csv` column headers exactly match the corresponding table's column names from [23](#23-database-schema) (minus `id`), except that `trades.csv` replaces the internal `event_id` foreign key with two columns joined from the parent `backtest_events` row ([23.5](#235-backtest_events), [23.6](#236-trades)): `date` and `event_sequence` (human-meaningful, ordering-relevant columns; the raw internal `event_id`/`backtest_events.id` is not exported).

### 25.5 Optimizations

**`POST /api/optimizations`**
```json
// request
{
  "dataset_id": 42,
  "base_configuration": { "...": "same shape as backtest configuration, minus the optimized fields" },
  "search": {
    "parameters": [
      { "name": "a_distance", "mode": "PERCENT", "start": "0.03", "end": "0.08", "increment": "0.01" },
      { "name": "grid_step",  "mode": "PERCENT", "start": "0.005", "end": "0.02", "increment": "0.005" }
    ]
  },
  "train_test": { "mode": "AUTO_70_30" },   // or { "mode": "MANUAL", "split_date": "2021-06-01" }
  "rank_metric": "sharpe_ratio",            // required; must be one of 35's metric keys
  "rank_direction": "DESC"                  // optional; defaults to 35's canonical direction for rank_metric if omitted
}
// response 201
{ "id": 9001, "status": "PENDING",
  "generated_count": 24, "valid_count": 22, "excluded_count": 2,
  "total_combinations": 22,                 // == valid_count; the denominator for progress ("33.8")
  "rank_metric": "sharpe_ratio", "rank_direction": "DESC",
  "created_at": "..." }
```
`rank_metric`/`rank_direction` drive both `current_best` (live, during the run) and the final `training_rank` assignment ([33.5](#335-optimization-algorithm)) — they are stored on the `OptimizationJob` row ([23.10](#2310-optimization_jobs)) so a page refresh or a different browser tab can still interpret `current_best`/`training_rank` correctly without re-deriving them. `rank_direction`, when explicitly supplied, overrides [35](#35-ranking-directions-and-missing-value-behavior)'s default "better direction" for that metric (e.g. to deliberately rank by the worst-performing combination); when omitted, the job stores whatever [35](#35-ranking-directions-and-missing-value-behavior)'s table resolves to for `rank_metric`, so it is never left implicit at read time.

Errors: `422 EMPTY_PARAMETER_RANGE`, `422 TOO_MANY_COMBINATIONS` (over the cap, checked against `generated_count`, [33.2](#332-combination-count-safety-cap)), `422 NO_VALID_COMBINATIONS` (`generated_count > 0` but `valid_count == 0` after per-combination validation, [33.8](#338-invalid-combination-handling)), `422 VALIDATION_ERROR` (missing/unrecognized `rank_metric`). The response always includes `generated_count`/`valid_count`/`excluded_count` (even on success with zero exclusions) so the frontend can show BLUEPRINT.md 17.3's pre-submit warning by calling this endpoint in a dry-run mode via `?dry_run=true` (returns `200` with the same three counts plus `total_combinations`, and no job created).

**`GET /api/optimizations`** → list, owned by current user.

**`GET /api/optimizations/{job_id}`** → full status incl. `progress`, `current_combination`, `current_best`, `estimated_remaining_seconds`.

**`POST /api/optimizations/{job_id}/cancel`** → sets `cancel_requested=true`, → `202 Accepted` (actual stop happens at the next Celery cancellation checkpoint, [33.6](#336-cancellation-checkpoints)).

**`GET /api/optimizations/{job_id}/results`**
```text
GET /api/optimizations/{job_id}/results?limit=20&offset=0&sort_by=sharpe_ratio&direction=desc
```
Paginated, sorted per [35](#35-ranking-directions-and-missing-value-behavior). `sort_by` takes one of [35](#35-ranking-directions-and-missing-value-behavior)'s plain snake_case metric keys (`final_equity`, `total_return`, `sharpe_ratio`, `max_drawdown`, `net_profit`, `first_return_equity`, `days_until_first_return`) — never a dotted `training_metrics.*`/`testing_metrics.*` path. The endpoint always sorts by that field **inside `training_metrics`** (never `testing_metrics` — ranking is training-only, [33.4](#334-training-vs-testing-evaluation-scope)), so which of the two metric blocks is being sorted is implicit in the endpoint's purpose, not spelled out in the parameter value.

---

## 26. Standard API Error Format

(ED-18) Every non-2xx JSON response uses this envelope:

```json
{
  "error": {
    "code": "INSUFFICIENT_CASH",
    "message": "Human-readable description safe to show in the UI.",
    "details": { "field": "trade_lots", "reason": "must be >= 1" }
  }
}
```

`details` is optional and omitted when there is nothing structured to add. HTTP status mapping:

| Status | Used for |
|---|---|
| 400 | Malformed request body/file, unparseable upload |
| 401 | `UNAUTHENTICATED` — missing/invalid/expired token |
| 403 | Reserved, unused in V2 (ownership failures use 404, [24.4](#244-ownership-enforcement)) |
| 404 | Resource not found or not owned |
| 409 | Conflict (`EMAIL_ALREADY_REGISTERED`, `DATASET_IN_USE`) |
| 422 | Validation error on an otherwise well-formed request |
| 500 | Unhandled server error (never exposes internals in `message`; details logged server-side only) |

---

## 27. Frontend Routes and Page States

| Route | Purpose | Auth required |
|---|---|---|
| `/` | Landing page | No |
| `/register` | Registration form | No (redirects to `/history` if already logged in) |
| `/login` | Login form | No (redirects to `/history` if already logged in) |
| `/backtest/new` | Upload/config wizard | Yes |
| `/backtest/[id]` | Result dashboard | Yes (ownership-checked) |
| `/history` | Saved backtests | Yes |
| `/optimization` | New/existing optimization jobs | Yes |
| `/optimization/[id]` | One optimization job's live status + results table | Yes |
| `/datasets` | Dataset management | Yes |

Unauthenticated access to a `Yes`-marked route redirects to `/login?next=<original path>`.

---

## 28. Upload Wizard States

`/backtest/new` step machine (BLUEPRINT.md 18.1):

```text
UPLOAD -> DETECTING -> MAPPING -> CLEANING_REVIEW -> PREVIEW -> DATASET_SAVED
       -> STRATEGY_CONFIG -> RUNNING -> DONE (redirect to /backtest/[id])
```

| State | Entry condition | Exit action |
|---|---|---|
| `UPLOAD` | Initial | File selected → `DETECTING` |
| `DETECTING` | File posted to `/api/datasets/preview` | Response received (holds `preview_token` A, bound to the auto-detected mapping) → `MAPPING`; error → back to `UPLOAD` with error banner |
| `MAPPING` | Preview response shown, mapping editable | If the user edits any field, exiting `MAPPING` first re-calls `POST /api/datasets/preview` with `manual_mapping` set to the edited mapping, replacing the held token with a new one (`preview_token` B, bound to the edited mapping) before advancing; if the user made no edits, the existing token from `DETECTING` is still valid and is reused. Either way → `CLEANING_REVIEW`, showing the bad-row/duplicate-row data for whichever token is now held. |
| `CLEANING_REVIEW` | Bad-row table + duplicate-row table shown, sourced from the currently-held token's cleaning result | User acknowledges → `PREVIEW` |
| `PREVIEW` | Cleaned-row preview grid shown, sourced from the currently-held token | User confirms → `DATASET_SAVED` (calls `POST /api/datasets` with the currently-held `preview_token` and `name` only, [25.2](#252-datasets)); user may go back to `MAPPING` — doing so and editing again repeats the re-preview step above, discarding the previously-held token in favor of a new one |
| `DATASET_SAVED` | Dataset persisted | Auto-advance → `STRATEGY_CONFIG` |
| `STRATEGY_CONFIG` | Portfolio/strategy form (also reachable directly for an already-saved dataset from `/datasets`) | Form valid + submit → `RUNNING` |
| `RUNNING` | `POST /api/backtests` in flight | Response `COMPLETED` → `DONE`; `FAILED` → error state, user may retry `STRATEGY_CONFIG` |
| `DONE` | — | Redirect to `/backtest/{id}` |

Reusing an existing dataset (from `/datasets`) enters the flow directly at `STRATEGY_CONFIG`, skipping `UPLOAD`…`DATASET_SAVED`.

---

## 29. Backtest Dashboard

`/backtest/[id]` must render (BLUEPRINT.md 18.2), all sourced from `GET /api/backtests/{id}?include=trades,zone_events,daily_equity,event_equity`:

- Core metrics panel ([21](#21-metrics)).
- Benchmark comparison panel (Benchmark 1 & 2 side-by-side with strategy).
- Candlestick chart (OHLCV datasets) or Close-price line (Close-only datasets), with Baseline, A/C boundary lines, and buy/sell markers overlaid.
- Grid-line display control: `Hide` / `Show all` / `Show near visible range` (client-side viewport filter over the fixed grid-level list — no extra API call needed since grid levels are part of `result_metrics.grid_levels`).
- Equity curve (Daily Close Equity by default; a toggle switches to Event-Level Equity, per BLUEPRINT.md 12.3 "main dashboard displays daily equity by default").
- Drawdown chart (from `DailyEquity.drawdown`).
- Trade distribution (histogram of trade sizes/prices — derived client-side from the `trades` payload, no new backend computation).
- Trade table (paginated client-side, all columns from [23.6](#236-trades)).
- Zone/risk events table (from `zone_events`).
- Export buttons for all four formats ([25.4](#254-exports)).

---

## 30. History and Comparison Behavior

- List (`GET /api/backtests`): search by name substring (`?search=`), filter by dataset/status.
- Rename: `PATCH /api/backtests/{id}` ([25.3](#253-backtests)).
- Delete: `DELETE /api/backtests/{id}`, with a confirmation dialog client-side (irreversible).
- Rerun / Duplicate: per [25.3](#253-backtests).
- Compare: select 2+ runs client-side, call `POST /api/backtests/compare`, render metrics side-by-side plus overlaid equity curves.
- Auto-generated name format (BLUEPRINT.md 16): `{security_code or dataset name} — {short strategy label} — {creation date YYYY-MM-DD}`, e.g. `159825 — A Grid 2% — 2026-07-15`, where `{short strategy label}` is `"A Grid {grid_step_pct or grid_step_fixed}{% or currency-less number}"`. User may edit the name at any time via `PATCH`.

---

## 31. Exports

| Export | Format | Content |
|---|---|---|
| Trade Log CSV | `trades.csv` | One row per `Trade`, columns per [23.6](#236-trades) |
| Daily Equity CSV | `equity.csv` | One row per `DailyEquity`, columns per [23.8](#238-daily_equity) |
| Complete Result JSON | `result.json` | `{ configuration, result_metrics, benchmark_1, benchmark_2, dataset_summary }` |
| PDF Report | `report.pdf` | Per [32](#32-pdf-report) |

CSV files use `,` delimiter, UTF-8 encoding, header row, `Decimal` values serialized as plain decimal strings (no scientific notation, no thousands separators).

---

## 32. PDF Report

Generated on request, never persisted server-side (BLUEPRINT.md 13). Sections, in order (BLUEPRINT.md 13, verbatim list, each mapped to its data source):

1. Project/backtest name — `BacktestRun.name`
2. Security information — `Dataset.security_name`/`security_code`
3. Data range — `Dataset.start_date`/`end_date`
4. Data-cleaning summary — `Dataset.cleaning_summary`
5. Strategy parameters — `BacktestRun.configuration`
6. Fee/slippage assumptions — `configuration.buy_commission`/`sell_commission`/`slippage`
7. OHLC-path assumption — `configuration.ohlc_path_mode`
8. Core metrics — `result_metrics` ([21](#21-metrics))
9. Both Buy-and-Hold benchmarks — `result_metrics.benchmark_1`/`benchmark_2`
10. Price chart — static render of the candlestick/close-line + baseline/A/C/grid overlay
11. Equity curve — static render of Daily Close Equity
12. Drawdown chart — static render of `DailyEquity.drawdown`
13. First 20 trades — first 20 `Trade` rows ordered by their `backtest_events.event_sequence` ([23.5](#235-backtest_events))
14. Cost summary — `Total Commission`, `Total Slippage Cost`
15. Risk disclaimer — fixed static text: *"This report is generated by a research and educational backtesting tool. It does not constitute investment advice. Past performance, whether real or simulated, does not guarantee future results."*

Implementation library (e.g. WeasyPrint, ReportLab) is deliberately left unspecified here — it is a Phase-3 implementation detail with no product-behavior consequence, decided when that phase starts.

---

## 33. Parameter Optimization

### 33.1 Optimizable Parameters and Ranges (BLUEPRINT.md 17.1/17.2, restated exactly)

| Parameter | Range shape |
|---|---|
| A Distance | Percent or Fixed range: `{start, end, increment}` |
| A Grid Step | Percent or Fixed range: `{start, end, increment}` |
| A Trade Lots | Integer range: `{start, end, increment}` |
| C Distance | Percent or Fixed range: `{start, end, increment}` |

Not optimizable: Commission, Slippage, OHLC path assumption (BLUEPRINT.md 17.1 — these remain fixed at `base_configuration`'s values for every combination).

### 33.2 Combination Count Safety Cap

(ED-12) `generated_count = product(len(values) for each ranged parameter)`, where `len(values)` for a range is:

```python
def range_values(start: Decimal, end: Decimal, increment: Decimal) -> list[Decimal]:
    assert increment > 0 and end >= start
    n = int((end - start) / increment)   # floor
    values = [start + i * increment for i in range(n + 1)]
    if values[-1] < end:
        # ED: always include the explicit end value even if not an exact multiple of increment,
        # per BLUEPRINT.md 17.2 "include valid endpoints"
        values.append(end)
    return values
```

If `generated_count > MAX_OPTIMIZATION_COMBINATIONS` (default **5,000**), `POST /api/optimizations` returns `422 TOO_MANY_COMBINATIONS` with `details.generated_count` and `details.limit`, before any job is created and **before** per-combination validation ([33.8](#338-invalid-combination-handling)) runs — the cap exists to bound the cost of generating and validating the Cartesian product in the first place, so it is checked against the raw count, not the post-validation `valid_count`. `total_combinations` (the job's progress denominator) is a distinct, smaller-or-equal quantity — see [33.8](#338-invalid-combination-handling).

### 33.3 Search Modes

- One-parameter scan: `search.parameters` has length 1.
- Multi-parameter Cartesian-product scan: `search.parameters` has length > 1; the job iterates the full Cartesian product of all listed parameters' `range_values`.

### 33.4 Training vs. Testing Evaluation Scope

(ED-11) BLUEPRINT.md 17.5 describes "search on training data, rank, then evaluate selected/top combinations on testing data." This SPEC computes **both** training-period and testing-period backtests for **every valid** combination ([33.8](#338-invalid-combination-handling)) in the Cartesian product, not just a post-hoc top-N subset. Rationale: it removes an unspecified "how many is top?" parameter, keeps the job's total work deterministic and easy to reason about (`2 × total_combinations` backtests, where `total_combinations == valid_count`, bounded by the cap in [33.2](#332-combination-count-safety-cap)), and the daily-bar engine is fast enough that this is not a meaningful performance concern. Ranking is still computed **only** from `training_metrics` (BLUEPRINT.md 17.5 rule 5, "never silently rank using testing results") — `testing_metrics` are informational, displayed alongside, never used for `training_rank`.

### 33.5 Optimization Algorithm

Each `OptimizationResult` is persisted **immediately, in its own transaction**, the instant its combination's train+test backtests finish — never held only in an in-memory list or an unflushed batch. `job.progress`, `job.current_best`, and `job.estimated_remaining_seconds` are computed and saved **only after** that commit succeeds, never before and never concurrently with it. This ordering is what makes cancellation *and* failure actually preserve completed work: an earlier design accumulated results into a `pending` batch (flushed every `RESULT_BATCH_SIZE` combinations) and advanced `job.progress`/`job.current_best` for each combination as soon as it was appended to the batch, not once it was durably committed — so a crash between "appended to `pending`" and "batch flushed" lost up to `RESULT_BATCH_SIZE - 1` completed results outright, and even short of a crash, `job.progress` could legitimately claim more completed combinations than `OptimizationResult` rows actually existed in the database at that instant. Committing per-result and sequencing progress strictly after the commit removes both problems: at every point during the run, the number of persisted `OptimizationResult` rows for this job is always `>= job.progress` never `<`, and there is no multi-combination window of unpersisted work for cancellation or a crash to lose.

```python
def run_optimization(job: OptimizationJob):
    # Idempotent-safe re-entry: this function may run more than once for the
    # same job.id if the Celery task is redelivered after a worker restart
    # (36.3's acks_late=True), so nothing below may assume it is starting
    # from a clean slate. See 33.9 for the full retry/idempotency contract.

    # --- Entry guard: terminal and FAILED states are never silently resumed ---
    fresh = reload_from_db(job.id)   # always the current persisted status, not whatever
                                      # status the caller's `job` object happened to hold --
                                      # a redelivered task must see reality, not a stale copy
    if fresh.status in ("COMPLETED", "CANCELLED"):
        return   # terminal -- a redelivered task arriving after the job already reached
                  # a terminal state must not touch it at all, not even to re-save the
                  # same values
    if fresh.status == "FAILED":
        return   # never auto-resumed. Only a distinct, explicit retry operation (not this
                  # function) may reset a FAILED job's status to PENDING; this function
                  # only ever proceeds past this guard when status is PENDING or RUNNING
    job = fresh

    job.status = "RUNNING"
    if job.started_at is None:
        job.started_at = now()

    train_bars, test_bars = split_dataset(job.dataset, job.train_test_configuration)  # 34
    # job.total_combinations, job.generated_count, job.valid_count, job.excluded_count
    # were already computed and persisted at job-creation time (33.8); valid_combos is
    # recomputed deterministically from job.search_configuration + job.base_configuration,
    # so it is identical on every entry, including a retry.
    valid_combos = valid_combinations(job)   # 33.8, same validation as at creation time
    keyed_combos = [(combination_key(c), c) for c in valid_combos]   # 33.9

    # --- Reconciliation pass: runs on every entry, fresh run or retry alike ---
    # Every value below is (re)computed from the database, never carried over
    # from job's prior in-memory/stored state, and the reconciled result is
    # made durable before any remaining combination is processed.
    done_count = count_persisted_results(job.id)                                  # 33.9
    job.progress = done_count
    job.current_best = best_so_far(job.id, job.rank_metric, job.rank_direction)    # 35 --
                                                                                     # recomputed from
                                                                                     # persisted rows now
    job.current_combination = last_persisted_combination(job.id)   # parameter_combination of the
                                                                      # most recently committed
                                                                      # OptimizationResult for this
                                                                      # job (created_at DESC LIMIT 1),
                                                                      # or None if done_count == 0
    job.estimated_remaining_seconds = estimate_remaining(job, done_count - 1) if done_count else None
    save(job)   # reconciled state is durable BEFORE any remaining combination is touched

    if done_count >= len(keyed_combos):
        # Every combination was already committed by a prior attempt -- the
        # case where all results landed before a worker crash, but that
        # crash happened before the job's own progress/current_best/status
        # update was committed. There is no remaining work; finalize
        # directly instead of entering a loop that would find nothing to do.
        assign_training_ranks(job.id, job.rank_metric, job.rank_direction)   # 35
        job.status = "COMPLETED"; job.completed_at = now(); save(job)
        return

    for combo in [c for _, c in keyed_combos]:
        key = combination_key(combo)   # 33.9 -- recomputed per iteration rather than reused
                                        # from keyed_combos, so this loop never depends on
                                        # any value computed before the reconciliation pass
        if result_already_persisted(job.id, key):    # 33.9 -- a direct, per-combination database
                                                        # lookup, never a process-local set; this is
                                                        # what makes the resume check itself immune
                                                        # to the same staleness the reconciliation
                                                        # pass above exists to fix
            continue

        if check_cancelled(job):                          # 33.6
            job.status = "CANCELLED"; job.completed_at = now(); save(job)
            return   # every combination completed before this point was already committed
                      # individually below -- there is nothing pending to flush or lose

        config = merge(job.base_configuration, combo)
        train_result = run_backtest_engine(train_bars, config)
        test_result  = run_backtest_engine(test_bars, config)

        result = OptimizationResult(
            optimization_job_id=job.id,
            combination_key=key,
            parameter_combination=combo,
            training_metrics=train_result.metrics,
            testing_metrics=test_result.metrics,
        )
        try:
            save(result)   # its own transaction; UNIQUE (optimization_job_id, combination_key)
                            # is the actual guard against a duplicate row -- 33.9
        except UniqueConstraintViolation:
            # A concurrent or retried execution of this exact combination
            # committed first. That commit is authoritative; this attempt's
            # in-memory train_result/test_result are discarded, not retried
            # again and not treated as a job failure -- 33.9.
            pass

        # After EVERY commit attempt -- whether save(result) just succeeded or
        # hit a uniqueness conflict -- progress and current_best are queried
        # fresh from the database, never incremented in memory and never read
        # from a process-local set. This is what keeps them correct even if
        # another attempt (a second worker on a redelivered task, or a
        # genuinely concurrent run) committed a different combination's result
        # in between this iteration's steps.
        job.progress = count_persisted_results(job.id)      # denominator is job.total_combinations == valid_count
        job.current_combination = combo
        job.current_best = best_so_far(job.id, job.rank_metric, job.rank_direction)   # 35
        job.estimated_remaining_seconds = estimate_remaining(job, job.progress - 1)
        save(job)   # every iteration -- job.progress must never lag behind what GET .../{job_id} can see

    assign_training_ranks(job.id, job.rank_metric, job.rank_direction)   # 35, UPDATEs persisted rows in place
    job.status = "COMPLETED"; job.completed_at = now(); save(job)
```

`best_so_far`, `assign_training_ranks`, `count_persisted_results`, `result_already_persisted`, and `last_persisted_combination` all read (or write) the **persisted** `OptimizationResult` rows for `job.id` directly — plain, cheap, indexed queries against `UNIQUE (optimization_job_id, combination_key)` and `(optimization_job_id, training_rank)` ([23.11](#2311-optimization_results)), never an in-memory list or set. This is a direct consequence of per-result persistence, and also what makes `progress`/`current_best`/`current_combination` correct after a page refresh mid-run, after a retry, and after the specific crash sequence described above.

There is no `RESULT_BATCH_SIZE` in this design — batching completed results before persisting them is exactly the mechanism that let `job.progress`/`job.current_best` outrun what was actually durable. A batch-style optimization would only be legitimate for something that cannot affect durability or `current_best` correctness at all (e.g. coalescing multiple *raw* engine-internal metric-array writes into one `OptimizationResult` row before that row's single `save()` call — still one commit per combination, no partial-batch loss window); nothing at the `run_optimization` level qualifies, so none is introduced here.

### 33.6 Cancellation Checkpoints

```python
def check_cancelled(job: OptimizationJob) -> bool:
    fresh = reload_from_db(job.id, fields=["cancel_requested"])
    return fresh.cancel_requested
```

Checked once per combination, **before** starting that combination's two backtests (never mid-backtest — a single train+test backtest pair is treated as an atomic unit of work, since daily-bar backtests are fast and mid-backtest cancellation would add complexity for negligible latency benefit). This satisfies BLUEPRINT.md 17.7 "Check cancellation between combinations."

### 33.7 Failure Handling

Any unhandled exception during a combination's backtest sets `job.status = "FAILED"`, `job.error_message = str(exception)` (sanitized — no stack trace exposed via the API, full trace logged server-side), `job.completed_at = now()`; already-committed `OptimizationResult` rows for prior combinations (per [33.5](#335-optimization-algorithm)'s per-result immediate persistence — every one of them was already durably saved, individually, before this combination even started) are kept — partial results remain inspectable, the same guarantee cancellation gets. A `FAILED` job stays `FAILED`: per [33.9](#339-celery-retry-and-result-idempotency)'s entry guard, `run_optimization` never auto-resumes it, including on task redelivery — only an explicit retry operation that first resets `status` to `PENDING` causes it to run again.

### 33.8 Invalid-Combination Handling

Each raw combination in the Cartesian product ([33.2](#332-combination-count-safety-cap)) is validated **before** the job is created, using the same per-configuration validation rules `POST /api/backtests` applies to a single backtest (zone-distance ordering, [7.4](#74-validation); grid density, [8.5](#85-grid-level-count-safety-cap); tick-rounding collapse, [9.4](#94-canonical-grid-levels-tick-size-enabled); numeric bounds, [17.5](#175-numeric-and-zero-equity-validation)) against `merge(base_configuration, combo)`:

```python
def valid_combinations(job_or_request) -> tuple[list[dict], int]:
    """Returns (valid_combos, excluded_count)."""
    all_combos = cartesian_product(job_or_request.search.parameters)   # generated_count = len(all_combos)
    valid = []
    excluded = 0
    for combo in all_combos:
        config = merge(job_or_request.base_configuration, combo)
        try:
            validate_backtest_configuration(config)   # the same checks 25.3 runs, raised as exceptions here
        except ConfigurationValidationError:
            excluded += 1
            continue
        valid.append(combo)
    return valid, excluded
```

- **Transparency**: excluded combinations are never silently dropped from the response — `generated_count`, `valid_count`, and `excluded_count` are always returned together on both the real `POST /api/optimizations` call and its `?dry_run=true` variant ([25.5](#255-optimizations)), so the user always sees how many combinations were requested versus how many will actually run.
- **Rejection threshold**: the request is rejected outright, with `422 NO_VALID_COMBINATIONS`, only when `valid_count == 0` (every generated combination failed validation). Any `valid_count >= 1` proceeds — the job simply runs on the valid subset.
- **Progress denominator**: `job.total_combinations = valid_count`, not `generated_count`. `job.progress`, `job.estimated_remaining_seconds`, and the frontend's progress bar are all expressed against `valid_count` — an excluded combination was never scheduled to run, so it must not appear to inflate "total work."
- Invalid combinations are **not** persisted as `OptimizationResult` rows (there is no meaningful `training_metrics`/`testing_metrics` for a configuration that was never backtested) and are not counted in `job.progress`.

### 33.9 Celery Retry and Result Idempotency

`acks_late=True` ([36.3](#363-retry-policy)) means a Celery worker only acknowledges the optimization task *after* it finishes — so a worker that crashes or is killed mid-run, after already committing one or more `OptimizationResult` rows but before the task is acknowledged, causes the broker to redeliver the same task. The redelivered task re-invokes `run_optimization(job)` from the top ([33.5](#335-optimization-algorithm)), for the same `job.id`, potentially processing combinations that a previous (crashed) attempt already completed and committed. Without an explicit guard, this would either duplicate `OptimizationResult` rows or, at best, redundantly re-run already-finished backtests. Two mechanisms close this:

**`combination_key`** — a deterministic hash of the *normalized* parameter combination, stored on each `OptimizationResult` row ([23.11](#2311-optimization_results)):

```python
def combination_key(combo: dict) -> str:
    # Normalize first so the same logical combination always produces the
    # same key regardless of dict insertion order or how a Decimal happens
    # to be formatted (e.g. "0.0300" vs "0.03") -- both matter, since combo
    # values originate from range_values (33.2), which always produces exact
    # Decimals, but two code paths constructing "the same" combination could
    # still differ in string form without this normalization step.
    normalized = {k: str(Decimal(v)) for k, v in sorted(combo.items())}
    return hashlib.sha256(json.dumps(normalized).encode("utf-8")).hexdigest()
```

`combination_key` is recomputed the same way on every entry to `run_optimization` (fresh run or retry) from the same deterministic `valid_combos` list ([33.8](#338-invalid-combination-handling)) — it is never itself persisted as job state or passed between attempts; it is derived, not stored, wherever it's needed for lookups.

**`UNIQUE (optimization_job_id, combination_key)`** on `optimization_results` ([23.11](#2311-optimization_results)) — the database-enforced guarantee that at most one `OptimizationResult` row can ever exist per combination per job, regardless of how many times `save(result)` is attempted for it.

**Entry guard — terminal and `FAILED` states are never silently resumed.** The very first thing `run_optimization` does ([33.5](#335-optimization-algorithm)) is reload the job's current persisted `status` (never trust the `status` on whatever `job` object the caller was invoked with, since that may be stale on a redelivered task):
- `status in ("COMPLETED", "CANCELLED")` → return immediately, without writing anything. A redelivered task arriving after the job already reached a terminal state must be a complete no-op.
- `status == "FAILED"` → also return immediately, without writing anything. A failed job is **never** automatically resumed by task redelivery — the only way a `FAILED` job runs again is a distinct, explicit retry operation (outside `run_optimization` itself) that resets `status` to `PENDING` first. `run_optimization` only ever proceeds past this guard when `status` is `PENDING` (a fresh or explicitly-reset job) or `RUNNING` (a genuine mid-run redelivery).

**Reconciliation pass — runs on every entry that gets past the guard, before any remaining combination is touched.** Three helper queries, all against `optimization_results` for this `job.id`:

```python
def count_persisted_results(job_id) -> int:
    return db.scalar("SELECT COUNT(*) FROM optimization_results WHERE optimization_job_id = %s", job_id)

def result_already_persisted(job_id, key) -> bool:
    return db.scalar(
        "SELECT EXISTS(SELECT 1 FROM optimization_results "
        "WHERE optimization_job_id = %s AND combination_key = %s)", job_id, key)

def last_persisted_combination(job_id) -> dict | None:
    row = db.fetchone(
        "SELECT parameter_combination FROM optimization_results "
        "WHERE optimization_job_id = %s ORDER BY created_at DESC LIMIT 1", job_id)
    return row.parameter_combination if row else None
```

`run_optimization` uses these to set `job.progress = count_persisted_results(job.id)`, `job.current_best = best_so_far(...)`, and `job.current_combination = last_persisted_combination(job.id)` — all recomputed from the database, never carried over from the job's own prior state — and commits that reconciled snapshot with one `save(job)` **before** looking at a single remaining combination. If `count_persisted_results(job.id)` already equals the number of valid combinations at this point, the job is finalized right there (`assign_training_ranks` + `status = "COMPLETED"`) instead of entering a loop with nothing left to do — this is exactly the case where every combination's result committed successfully but the worker crashed before the job's own `progress`/`current_best`/`status` update was committed; without this check, a naive resume would loop over every combination, find each one already persisted via `result_already_persisted`, and only reach the finalization step at the natural end of the loop — functionally equivalent, but the explicit check makes the "everything's already done, this is purely a state-catch-up run" case visible rather than incidental.

**Per-combination resume check is a live query, not a process-local set.** `result_already_persisted(job.id, key)` is called fresh for each combination inside the loop, rather than checking membership in a set snapshotted once at the top of the function — so a combination committed by a concurrently-running second attempt (racing on the same redelivered task) is correctly skipped even if it wasn't yet committed when this attempt started.

**After every commit attempt — success or a caught uniqueness conflict — `job.progress` and `job.current_best` are re-queried from the database, never incremented or read from memory.** `job.progress = count_persisted_results(job.id)` and `job.current_best = best_so_far(...)` run again after every `save(result)` attempt in the loop, whether that attempt just committed a new row or hit the `UNIQUE (optimization_job_id, combination_key)` constraint. This is what keeps both values correct even when a concurrent or retried execution commits a *different* combination's result in the narrow window between this iteration's own steps — a process-local counter or set could drift from the database in that scenario; a fresh query cannot.

**Uniqueness-conflict behavior**: when `save(result)` violates `UNIQUE (optimization_job_id, combination_key)` — meaning another attempt's commit for this exact combination landed first — the violation is caught, the in-memory `train_result`/`test_result` this attempt just computed are discarded (never retried, never logged as an error), and execution proceeds exactly as if `result_already_persisted` had found this combination already done: `job.progress`/`current_best` are recomputed from the persisted rows (per the point above) and the loop continues to the next combination. This is not a job failure — a uniqueness conflict here means the work was already done, correctly, by someone else, which is precisely the outcome idempotent resumption is supposed to produce.

---

## 34. Training/Testing Split

(ED-13) `train_test_configuration`:

```json
{ "mode": "AUTO_70_30" }
// or
{ "mode": "MANUAL", "split_date": "2021-06-01" }
```

```python
def split_dataset(bars: list[Bar], config: dict) -> tuple[list[Bar], list[Bar]]:
    if config["mode"] == "AUTO_70_30":
        n_train = ceil(0.70 * len(bars))     # split by row ordinal, not calendar-time proportion
        return bars[:n_train], bars[n_train:]
    else:  # MANUAL
        split_date = config["split_date"]
        train = [b for b in bars if b.date < split_date]
        test  = [b for b in bars if b.date >= split_date]
        return train, test
```

- `AUTO_70_30` splits by **row count**, not by elapsed calendar time — a dataset with irregular trading-day gaps (holidays, etc.) still gets a clean 70/30 row split rather than a proportionally-skewed one.
- `MANUAL`: the split date belongs to the **testing** set (`train < split_date <= test`).
- Both `train` and `test` must have `>= 2` bars after splitting (needed for Sharpe/return calculations, [21.3](#213-sharpe-ratio)); otherwise `422 INSUFFICIENT_SPLIT_DATA` at job-creation time.
- Each sub-period backtest re-derives its own `Baseline` under the same rule as a full backtest (first bar's Close of *that sub-period*, unless the user's `base_configuration` supplies an explicit baseline override, which applies identically to both sub-periods) — this keeps the split faithful to "what would this configuration have done starting fresh on this sub-period," which is the entire point of an out-of-sample test.

---

## 35. Ranking Directions and Missing-Value Behavior

(ED-10) Applies to `GET /api/optimizations/{job_id}/results?sort_by=&direction=` and to `job.current_best`/`training_rank` computation ([33.5](#335-optimization-algorithm)). The metric keys accepted by `rank_metric` (request field, [25.5](#255-optimizations)) and `sort_by` are the snake_case forms of the "Metric" column below (`final_equity`, `total_return`, `sharpe_ratio`, `max_drawdown`, `net_profit`, `first_return_equity`, `days_until_first_return`).

| Metric | Default direction (`rank_direction`/`direction` if omitted) | Missing-value handling |
|---|---|---|
| Final Equity | Higher (descending) | N/A only if the sub-period backtest itself failed — sorts last |
| Total Return | Higher (descending) | Same as above |
| Sharpe Ratio | Higher (descending) | `null` per [21.3](#213-sharpe-ratio) — sorts last |
| Maximum Drawdown | Closer to zero (descending, since stored as a non-positive value) | N/A only on backtest failure — sorts last |
| Net Profit | Higher (descending) | N/A only on backtest failure — sorts last |
| First Return to Initial Share Position Equity | Higher (descending) | `null` if never returned ([21.10](#2110-first-return-to-initial-share-position)) — sorts last |
| Days Until First Return to Initial Share Position | Lower (ascending) | `null` if never returned — sorts last |

This "Default direction" column is exactly what `POST /api/optimizations` uses to resolve `job.rank_direction` when the request omits `rank_direction` ([25.5](#255-optimizations)); a request that supplies `rank_direction` explicitly overrides it for that job only, and does not change this table for other jobs or for `GET .../results?sort_by=`.

**Universal rule:** regardless of which `direction` (`asc`/`desc`) the user requests, rows with a `null` value for the active `sort_by` metric always appear **after** every row with a non-null value — toggling direction never moves nulls to the top. Within the null group, secondary order is `training_rank` ascending (i.e. insertion/combination order) for stability.

`job.current_best` during a running job is the best-so-far row by this same rule, recomputed after each combination.

---

## 36. Celery Job Lifecycle

### 36.1 States

`PENDING → RUNNING → {COMPLETED | CANCELLED | FAILED}`. Terminal states never transition further. A `BacktestRun` uses only `{PENDING, RUNNING, COMPLETED, FAILED}` (no cancellation, since it runs synchronously per [25.3](#253-backtests)); an `OptimizationJob` uses all five states.

### 36.2 Progress Reporting

`OptimizationJob.progress`/`current_combination`/`current_best`/`estimated_remaining_seconds` are persisted to PostgreSQL (not just Celery/Redis task state) so that a page refresh or a different browser tab shows correct status without depending on Celery result-backend retention (BLUEPRINT.md 17.7 "Persist enough state to display status after page refresh").

`estimated_remaining_seconds` calculation:

```python
def estimate_remaining(job, completed_index: int) -> int | None:
    elapsed = (now() - job.started_at).total_seconds()
    completed = completed_index + 1
    if completed == 0:
        return None
    avg_per_combo = elapsed / completed
    remaining = job.total_combinations - completed
    return int(avg_per_combo * remaining)
```

### 36.3 Retry Policy

Celery task-level retry is **not** used for optimization combinations — a failing combination fails the whole job ([33.7](#337-failure-handling)), because a partially-successful parameter sweep with silently-skipped combinations would misrepresent the search space to the user (violates BLUEPRINT.md principle #4, "No hidden assumptions"). Celery's own transient-infrastructure retry (broker reconnect, worker restart) is configured at the task-invocation level (`acks_late=True`, `max_retries` for *infrastructure* failures only, not for backtest-logic exceptions) — a `BacktestEngineError` raised by the engine is never retried, only re-raised into `job.error_message`.

`acks_late=True` specifically means the broker may redeliver — and a worker may therefore re-invoke `run_optimization` for — a job that already committed some `OptimizationResult` rows before its previous attempt died. [33.9](#339-celery-retry-and-result-idempotency) defines exactly how re-entry stays safe: a deterministic `combination_key` per combination, a database-enforced `UNIQUE (optimization_job_id, combination_key)` constraint, and a resume step that skips already-committed combinations rather than reprocessing them.

### 36.4 Cancellation

`POST /api/optimizations/{job_id}/cancel` sets `cancel_requested=true` synchronously in the API request (fast, no Celery round-trip needed for the flag itself); the worker observes it at the next checkpoint ([33.6](#336-cancellation-checkpoints)). There is no forced task-kill — the current in-flight train+test backtest pair always finishes before the job stops, keeping `OptimizationResult` rows internally consistent (never a half-written training-only row).

---

## 37. Security and Environment Variables

Required environment variables (never committed, per BLUEPRINT.md 23):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Celery broker/result backend |
| `JWT_SECRET_KEY` | HS256 signing secret |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Default `1440` (24h) |
| `CORS_ALLOWED_ORIGINS` | Comma-separated list, frontend origin(s) only |
| `COOKIE_SECURE` | `true` in production, `false` for local `http://localhost` |
| `ENVIRONMENT` | `development` \| `production`, gates `COOKIE_SECURE` default and debug error detail |
| `MAX_OPTIMIZATION_COMBINATIONS` | Default `5000` (ED-12) |
| `MAX_GRID_LEVELS` | Default `10000` (ED-12) |

Additional requirements:
- Password hashes use Argon2id with library-recommended default work factors; never logged.
- `result_metrics`/`configuration` JSONB never contains password hashes or tokens (no cross-contamination risk since these tables never reference user credentials).
- All SQL access goes through SQLAlchemy's parameterized query construction — no raw string-interpolated SQL anywhere in the codebase.
- File uploads are size-capped (`MAX_UPLOAD_SIZE_MB`, default `20`) and the raw file is discarded immediately after parsing into the preview cache (BLUEPRINT.md 3.2 "Raw uploaded-file storage" is explicitly deferred/excluded).

---

## 38. Acceptance Criteria

Each item is independently verifiable and maps to at least one row in [39](#39-requirement-to-test-traceability-table).

| Feature | Acceptance Criteria |
|---|---|
| TongdaXin parsing | Sample GBK/GB18030 `.xls` with title line, blank lines, extra indicator columns, and a footer line parses to the correct row count with zero data-integrity errors; Chinese headers map automatically. |
| CSV parsing | UTF-8 and GBK CSVs with English or Chinese headers parse identically to the TongdaXin equivalents for the same underlying data. |
| Data cleaning | Every injected bad-row type ([5.2](#52-row-validity-rules)) is caught, shown with its exact reason code, and excluded from the saved dataset; duplicate dates keep the last-in-file-order row only after confirmation. |
| Grid generation | For a non-divisible A-distance/step combination, the generated level set exactly matches manual calculation via [8.4](#84-non-divisible-a-distance); boundaries are never forced onto the grid. |
| Engine determinism | Re-running the identical configuration against the identical dataset produces byte-identical `Trade`/`ZoneEvent`/`DailyEquity` rows. |
| Anchor rules | The BLUEPRINT.md 8.6 worked example (anchor 0.95, path 0.95→0.85→0.92→1.00) produces exactly the described trade sequence. |
| Fees/slippage | Each of the 8 fee-configuration combinations (`rate_enabled`/`minimum_enabled`/`fixed_enabled` toggled independently, [19.1](#191-commission-formula)) produces hand-computed commission values to the cent; see the "Buy/sell separate fees, all fee-component combinations" and "Slippage percent/fixed, separate buy/sell" rows of [39](#39-requirement-to-test-traceability-table) for the governing sections these tests assert against. |
| Benchmarks | Benchmark 1 equity equals `initial_cash + initial_shares*close[t]` for every `t`; Benchmark 2's day-one share count is the largest integer number of lots affordable under the exact fee/slippage rules. |
| Metrics | Sharpe/Max-DD/Annualized-Return match an independent spreadsheet recomputation on a fixed 30-day fixture to 6 decimal places. |
| Auth | A logged-out request to any owned resource returns `401`; a logged-in request to another user's resource returns `404`. |
| Exports | All four export formats download successfully for a completed backtest and open/parse without error in a standard CSV/JSON/PDF viewer. |
| Optimization | A 2-parameter, 24-combination job completes with 24 `OptimizationResult` rows, each with both training and testing metrics; cancelling mid-job leaves prior results intact and sets status `CANCELLED`. |
| Ranking | Sorting by Sharpe Ratio with some `null` values always shows nulls last in both `asc` and `desc`. |

---

## 39. Requirement-to-Test Traceability Table

Maps BLUEPRINT.md §21 (Testing Blueprint) categories to the SPEC sections that define the exact expected behavior each test must assert against.

| Test area (BLUEPRINT.md §21) | Governing SPEC section(s) |
|---|---|
| TongdaXin GBK/GB18030 `.xls` | [3](#3-tongdaxin-xls-parsing-rules) |
| Normal UTF-8 CSV | [4](#4-csv-parsing-and-column-mapping-rules) |
| Chinese/English column detection, manual mapping | [2.3](#23-column-name-recognition-table), [4](#4-csv-parsing-and-column-mapping-rules) |
| Extra indicator columns, blank lines, footer line | [3.2](#32-header-and-footer-detection), [3.3](#33-extra-indicator-columns) |
| Invalid numeric rows, missing required values | [5.2](#52-row-validity-rules) |
| Duplicate dates, descending dates | [5.1](#51-cleaning-pipeline-order), [5.3](#53-duplicate-date-policy) |
| Close-only data, missing Volume | [6.2](#62-close-only-mode), [2.2](#22-required-fields-by-data-mode) |
| Percent/Fixed A/C distance, grid step | [7.2](#72-a-zone-boundaries)–[7.3](#73-c-zone-boundaries), [8.2](#82-grid-step-fixed-mode)–[8.3](#83-grid-step-percent-mode-formulas) |
| Baseline as grid, non-divisible distance/step | [8.1](#81-grid-anchoring), [8.4](#84-non-divisible-a-distance) |
| Decimal precision, optional tick size | [9](#9-decimal-precision-and-tick-size) |
| One downward/upward crossing, exact-touch triggering | [12](#12-crossing-inclusivity-rules) |
| Multi-grid crossings | [13](#13-multi-grid-crossing) |
| Same-day buy then sell / sell then buy | [11.5](#115-same-day-and-repeated-crossings) |
| Repeated crossing of same grid | [11.5](#115-same-day-and-repeated-crossings), [15](#15-trade-anchor-preservation-and-no-backfill-rule) |
| Cash/shares insufficient, no partial fill | [16](#16-order-execution-rules), [17.3](#173-constraints) |
| Anchor unchanged on skip, later levels attempted after skip | [15](#15-trade-anchor-preservation-and-no-backfill-rule), [13.2](#132-algorithm) |
| A-to-C / C-to-A transition, anchor preserved, no C backfill | [14](#14-ac-state-transitions), [15](#15-trade-anchor-preservation-and-no-backfill-rule) |
| Outside-C events | [14.2](#142-boundary-crossing-transition-table)–[14.4](#144-worked-examples) |
| First-day OHLC processing, all 3 path modes, Close-only | [11.2](#112-path-mode-selection)–[11.4](#114-first-day-processing) |
| Buy/sell separate fees, all fee-component combinations | [19](#19-commission) |
| Slippage percent/fixed, separate buy/sell | [18](#18-slippage) |
| Tick rounding order | [9.3](#93-tick-rounding-order-frozen) |
| Final equity, return, annualized return | [21.1](#211-basic-metrics)–[21.2](#212-annualized-return) |
| Max drawdown | [21.4](#214-maximum-drawdown) |
| Sharpe, zero-volatility Sharpe case | [21.3](#213-sharpe-ratio) |
| Commission/slippage totals, zone day counts | [21.5](#215-commission-slippage-trade-counts)–[21.6](#216-zone-day-counts) |
| Benchmark calculations | [20](#20-buy-and-hold-benchmarks) |
| First return to initial share position | [21.10](#2110-first-return-to-initial-share-position) |
| Authentication, ownership isolation | [24](#24-authentication-and-ownership) |
| Dataset preview/save | [25.2](#252-datasets) |
| Backtest create/read/delete, history operations | [25.3](#253-backtests), [30](#30-history-and-comparison-behavior) |
| Export endpoints | [25.4](#254-exports), [31](#31-exports) |
| Optimization lifecycle | [33](#33-parameter-optimization), [36](#36-celery-job-lifecycle) |
| Upload wizard, column mapping, cleaning confirmation (frontend/E2E) | [28](#28-upload-wizard-states) |
| Strategy validation, run backtest, result dashboard (frontend/E2E) | [29](#29-backtest-dashboard) |
| History operations, login protection (frontend/E2E) | [27](#27-frontend-routes-and-page-states), [30](#30-history-and-comparison-behavior) |
| Optimization progress/cancel, downloads (frontend/E2E) | [36.2](#362-progress-reporting), [36.4](#364-cancellation), [31](#31-exports) |

---

## 40. Implementation Phases and Dependency Order

Mirrors BLUEPRINT.md §22's three-day plan, expanded into explicit dependency-ordered tasks. No phase begins until the previous phase's tests pass.

### Phase 1 — Pure Engine (no FastAPI/DB/frontend dependency)
1. Domain models/enums (`Bar`, `Dataset` value object, `EngineConfig`, `TradeResult`, zone enums) — [1](#1-terminology-and-domain-definitions), [23](#23-database-schema) field shapes as plain dataclasses.
2. TongdaXin + CSV parsers — [3](#3-tongdaxin-xls-parsing-rules), [4](#4-csv-parsing-and-column-mapping-rules).
3. Data cleaning pipeline — [5](#5-data-cleaning-and-duplicate-date-behavior).
4. Grid generation — [8](#8-grid-generation).
5. OHLC path segmentation — [11](#11-ohlc-path-processing).
6. Crossing/multi-grid/A↔C engine core — [12](#12-crossing-inclusivity-rules)–[15](#15-trade-anchor-preservation-and-no-backfill-rule).
7. Order execution, fees, slippage, tick rounding — [16](#16-order-execution-rules)–[19](#19-commission).
8. Benchmarks — [20](#20-buy-and-hold-benchmarks).
9. Metrics — [21](#21-metrics).
10. Daily/event equity — [22](#22-event-level-and-daily-equity).

*Dependency note:* 1→2,3 (parsers need domain models); 3→4,5 (grid/path need clean bars); 4,5→6 (crossing engine needs both); 6→7 (execution needs crossing detection); 7→8,9,10 (all downstream calculations need executed trades and cash/share state).

### Phase 2 — Persistence, API, Auth
1. SQLAlchemy models + Alembic migrations — [23](#23-database-schema).
2. Auth (register/login/logout/me, JWT cookie) — [24](#24-authentication-and-ownership), [25.1](#251-authentication).
3. Dataset preview/save endpoints (wraps Phase 1 parsers/cleaning) — [25.2](#252-datasets).
4. Backtest create/read/list/delete/rerun/duplicate/compare endpoints (wraps Phase 1 engine, synchronous) — [25.3](#253-backtests).
5. Export endpoints — [25.4](#254-exports).

*Dependency note:* 1 is required by everything else in this phase; 2 gates ownership checks needed by 3–5; 3→4 (backtests reference datasets).

### Phase 3 — Frontend Core
1. Next.js app shell, auth pages, theme — [27](#27-frontend-routes-and-page-states).
2. Upload/cleaning/strategy wizard — [28](#28-upload-wizard-states).
3. Result dashboard (charts, tables, exports) — [29](#29-backtest-dashboard).
4. History + dataset management pages — [30](#30-history-and-comparison-behavior).

### Phase 4 — Optimization
1. Synchronous optimizer function (reuses Phase 1 engine directly, no Celery yet) — [33.1](#331-optimizable-parameters-and-ranges-blueprintmd-171172-restated-exactly)–[33.5](#335-optimization-algorithm), tested in isolation.
2. Optimization API endpoints (still calling the synchronous optimizer inline for early testing) — [25.5](#255-optimizations).
3. Celery + Redis wrapper around the same optimizer function — [36](#36-celery-job-lifecycle).
4. Optimization frontend (progress, cancel, results table) — [27](#27-frontend-routes-and-page-states), [35](#35-ranking-directions-and-missing-value-behavior).

*Dependency note:* This phase is deliberately last because it composes Phase 1's engine + Phase 2's persistence patterns + Phase 3's frontend patterns — it introduces no new domain concepts, only orchestration.

### Phase 5 — Testing Completion, Docker, Deployment
1. Fill any remaining gaps in the traceability table ([39](#39-requirement-to-test-traceability-table)) across all phases.
2. Playwright E2E across the full user journey.
3. Docker Compose (frontend/backend/worker/Postgres/Redis containers).
4. Public deployment.

---

*End of specification. Approved for implementation. No application code has been written yet.*
