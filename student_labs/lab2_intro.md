# Lab 2 Introduction: Date Dimensions, Role-Playing, and Advanced SCDs
### Concepts from Chapters 5–8 | ITM 327

This document connects what you read in the textbook to what you will build in Lab 2. Lab 1 gave you the skeleton of a star schema. Lab 2 makes it production-grade by handling time correctly and replacing the blunt Type 1 strategy with the right tool for each dimension.

---

## 1. The Date Dimension

The date dimension is the most universally present dimension in any data warehouse. Every business process happens *at a point in time*, and almost every analysis involves time — "sales this month vs. last month," "cases open for more than 30 days," "revenue by fiscal quarter."

### Why not just store the raw date?

You could store `close_date DATE` directly in the fact table. But then every query that filters or groups by week, quarter, fiscal year, or holiday status has to recalculate those values on the fly. The date dimension pre-computes all of this:

```
dim_date
  date_key       = 20240315       ← integer key, human-readable
  calendar_date  = 2024-03-15
  day_name       = Friday
  month_name     = March
  quarter        = 1
  fiscal_quarter = 2              ← if your fiscal year starts Feb 1
  is_weekend_flag = FALSE
  month_end_flag  = FALSE
  ...
```

Now a query grouping by fiscal quarter just joins to `dim_date` — no `CASE WHEN` logic in every report.

### The date key is not AUTOINCREMENT

Unlike other dimension surrogate keys, the date dimension key is **formatted as an integer** — the date itself expressed as `YYYYMMDD`. `20240315` for March 15, 2024. This makes the key human-readable in the fact table and allows range filtering with simple integer comparisons.

### SCD Type 0 — the date dimension never changes

Dates are historical facts. March 15, 2024 will always be a Friday in Q1. The date dimension uses **SCD Type 0** — rows are inserted once and never updated. This is why it is the easiest dimension to reason about.

> *"The date dimension is populated by calculating the attributes for every date in a defined range — not by querying source systems."* — Kimball, Ch. 3

### How to populate it

You generate rows using a recursive CTE or a calendar table generator — not by reading Salesforce. Snowflake makes this clean with a `GENERATOR` function:

```sql
INSERT INTO dim_date (date_key, calendar_date, day_name, month_name, quarter, year, ...)
WITH date_spine AS (
    SELECT DATEADD(day, seq4(), '2015-01-01')::DATE AS d
    FROM TABLE(GENERATOR(ROWCOUNT => 3653))  -- 10 years
)
SELECT
    TO_NUMBER(TO_CHAR(d, 'YYYYMMDD'))          AS date_key,
    d                                           AS calendar_date,
    DAYNAME(d)                                  AS day_name,
    MONTHNAME(d)                                AS month_name,
    QUARTER(d)                                  AS quarter,
    YEAR(d)                                     AS year,
    CASE WHEN DAYOFWEEK(d) IN (1,7) THEN TRUE ELSE FALSE END AS is_weekend_flag,
    -- ... other attributes
FROM date_spine;
```

---

## 2. Role-Playing Dimensions

An opportunity has two meaningful dates: when it was **created** and when it is expected to **close**. Both are dates. Both need the same rich set of attributes (day of week, quarter, fiscal year, etc.).

The solution is **not** to create two separate date dimension tables. Instead, the same `dim_date` table is **role-played** — referenced twice in the fact table with different foreign key column names:

```
fact_opportunity_line_item
  created_date_key  →  dim_date (role: "Created Date")
  close_date_key    →  dim_date (role: "Close Date")
```

Both columns point to the exact same `dim_date` table. When you join, you alias the table:

```sql
SELECT
    f.total_price,
    created.month_name   AS created_month,
    closed.quarter       AS close_quarter
FROM fact_opportunity_line_item f
JOIN dim_date created ON created.date_key = f.created_date_key
JOIN dim_date closed  ON closed.date_key  = f.close_date_key;
```

> *"Role-playing dimensions allow the same physical dimension table to be used multiple times in the same query with different meanings."* — Kimball, Ch. 3

This is one of the most elegant patterns in dimensional modeling: one table, maintained once, serves every time-based question across every fact table.

---

## 3. SCD Type 2 — Add a New Row

Type 1 (overwrite) was sufficient for Lab 1 because we didn't need to answer time-sensitive questions about the state of accounts at a historical point in time. Lab 2 changes that requirement.

### The problem Type 2 solves

Suppose Account "Acme Corp" was classified as `industry = Retail` when a deal closed in January. In March, Acme reorganizes and the industry changes to `Technology`. With Type 1, the January deal now shows `Technology` — the history is gone. An analyst trying to understand "how much revenue did we close with Retail accounts in Q1?" gets the wrong answer.

**Type 2** solves this by never updating the old row. Instead, it **adds a new row** with a new surrogate key:

| account_key | account_id | account_name | industry | eff_start | eff_end | current_flag |
|---|---|---|---|---|---|---|
| 101 | 0016X00... | Acme Corp | Retail | 2024-01-01 | 2024-03-14 | FALSE |
| 247 | 0016X00... | Acme Corp | Technology | 2024-03-15 | 9999-12-31 | TRUE |

The January fact rows still point to `account_key = 101` (Retail). March and later rows point to `account_key = 247` (Technology). Both are correct — history is partitioned automatically.

### The three required columns

Every Type 2 dimension needs exactly these three administrative columns:

| Column | Purpose |
|---|---|
| `effective_start_date` | First date this row's profile was valid |
| `effective_end_date` | Last date valid (`9999-12-31` for the current row — avoids NULLs in BETWEEN queries) |
| `current_flag` | Quick filter for current rows without date range logic |

### Initial load for Type 2

When you first load the dimension (no history exists yet), every row gets:
- `effective_start_date = CURRENT_DATE` (or the earliest known date)
- `effective_end_date = '9999-12-31'`
- `current_flag = TRUE`

> *"Type 2 is the safest response if the business is not absolutely certain about the change handling approach. It preserves complete history and does not require aggregate table rebuilding."* — Kimball, Ch. 5

### Querying Type 2 — two common patterns

```sql
-- Get only current accounts
SELECT * FROM dim_account WHERE current_flag = TRUE;

-- Get the account profile as of a specific date
SELECT * FROM dim_account
WHERE account_id = '0016X00...'
  AND effective_start_date <= '2024-01-31'
  AND effective_end_date   >= '2024-01-31';
```

---

## 4. SCD Type 3 — Add a Prior Attribute

Type 3 is a middle ground: you track **one level of history** for a specific attribute without creating new rows. Instead, you add a `prior_` column alongside the current column.

### When Type 3 is appropriate

Use Type 3 when:
- The business only needs "current vs. previous" — not full history
- The attribute changes infrequently (once or twice, not continuously)
- The business wants to report on **both the old and new classification simultaneously** (e.g., "show me revenue by both old and new product family")

For `dim_product` in Lab 2, the business wants to see the current family and be able to look back at the prior family — but doesn't need a complete version history. Type 3 delivers this with a single new column:

| product_key | product_id | product_name | product_family_name | prior_product_family_name |
|---|---|---|---|---|
| 12345 | ABC922-Z | IntelliKidz | Strategy | Education |

When a product gets reclassified again later, `prior_product_family_name` is overwritten with `Strategy`, and `product_family_name` is set to the new family. Only two levels of history are ever tracked.

> *"Type 3 enables both 'as-was' and 'as-is' analysis for the one attribute being tracked."* — Kimball, Ch. 5

### Type 3 limitations

- Only tracks **one prior value** — if the attribute changes three times, the first original value is lost
- Cannot be used for granular point-in-time queries like Type 2 can

This is exactly why the choice matters: Type 2 for attributes where complete history is essential (account industry), Type 3 for attributes where "current and prior" is enough (product family reclassification).

---

## 5. Choosing the Right SCD Type

| Situation | Use |
|---|---|
| Attribute should never change (dates, original scores) | Type 0 |
| Only current value matters; analysts accept rewritten history | Type 1 |
| Full point-in-time accuracy required | Type 2 |
| Current and prior values sufficient; full history not needed | Type 3 |

A single dimension can mix strategies. In Lab 2, `dim_product` will use Type 3 for `product_family_name` while continuing Type 1 behavior for all other attributes. `dim_account` uses Type 2 for everything — the entire row is versioned.

---

## 6. Connecting to Lab 2

| Lab 2 concept | Where it appears |
|---|---|
| Date dimension (SCD Type 0) | `dim_date` — Task 1 |
| Time dimension | `dim_time` — Task 2 |
| Role-playing dates | `created_date_key` + `close_date_key` in fact — Task 3 |
| SCD Type 2 | `dim_account` with effective dates and current flag — Task 4 |
| SCD Type 3 | `dim_product` with `prior_product_family_name` — Task 5 |

The fact table refactor in Task 3 is not a new fact table — it is the *same business process* from Lab 1, now modeled correctly with time handled through the date dimension instead of raw date columns.
