# dim_date: Generating a Date Dimension in Snowflake

---

## Video Resources

If you prefer to watch before you read, search YouTube for these topics:

| Search Term | What to Look For |
|---|---|
| `date dimension data warehouse Kimball tutorial` | Videos that show how a date dimension is structured — look for the YYYYMMDD integer key and calendar attribute columns |
| `conformed dimensions star schema data warehouse` | Any video explaining why dim_date is shared across all fact tables rather than one per table |
| `role-playing dimensions data warehouse` | Videos showing two foreign keys in a fact table both pointing to the same date dimension — different names, same table |
| `Snowflake GENERATOR function date spine` | Snowflake-specific tutorials using `TABLE(GENERATOR(ROWCOUNT => n))` to generate rows |

**Channels with strong dimensional modeling content:** `Bryan Cafferky` · `Kahan Data Solutions` · `techTFQ`

> **Visual reference:** [InterWorks — Using Snowflake's Generator Function for Date/Time Scaffold Tables](https://interworks.com/blog/2022/08/02/using-snowflakes-generator-function-to-create-date-and-time-scaffold-tables/) walks through the exact Snowflake GENERATOR pattern with code examples.

---

## Why Generate Instead of Query?

> **Textbook reference:** Chapter 3 — *Retail Sales*, "Calendar Date Dimensions" introduces the date dimension as an independent, pre-populated table rather than one derived from transaction data. Chapter 4 — *Inventory* covers **conformed dimensions** — dimensions shared and reused across multiple fact tables — and the bus architecture that makes them possible.

`dim_date` is a **conformed dimension** — it is independent of any source system. Rather than pulling dates from Salesforce, you generate every calendar date you might ever need. This means:

- Analysts can filter by any date, even ones with no transactions yet
- `dim_date` can be reused across every fact table in your warehouse
- You control exactly which attributes exist and how they are calculated

---

## The Key Function: `GENERATOR`

Snowflake's `TABLE(GENERATOR(ROWCOUNT => n))` produces exactly `n` rows with no source table. Combined with `SEQ4()` — a sequential integer starting at 0 — you can produce any numbered series.

```sql
SELECT seq4() AS n
FROM TABLE(GENERATOR(ROWCOUNT => 5));
```

| n |
|---|
| 0 |
| 1 |
| 2 |
| 3 |
| 4 |

---

## Turning Row Numbers into Dates: `DATEADD`

Add each sequential integer as days to a start date:

```sql
SELECT DATEADD(day, seq4(), '2015-01-01')::DATE AS calendar_date
FROM TABLE(GENERATOR(ROWCOUNT => 10));
```

| calendar_date |
|---|
| 2015-01-01 |
| 2015-01-02 |
| 2015-01-03 |
| … |

> **Choosing ROWCOUNT:** To cover 2015-01-01 through 2024-12-31, count the days between those dates. 10 years ≈ 3,653 rows (accounting for leap years). Use `DATEDIFF(day, '2015-01-01', '2025-01-01')` in Snowflake to get an exact count.

---

## Building the date_key

The `date_key` for `dim_date` should be a human-readable integer in `YYYYMMDD` format — **not** AUTOINCREMENT. This makes keys self-documenting: `20240315` is obviously March 15, 2024.

```sql
TO_NUMBER(TO_CHAR(calendar_date, 'YYYYMMDD')) AS date_key
```

---

## A Minimal Working Example

This produces 10 rows with a few common attributes — use it as a starting point:

```sql
WITH date_spine AS (
    SELECT DATEADD(day, seq4(), '2015-01-01')::DATE AS d
    FROM TABLE(GENERATOR(ROWCOUNT => 3653))
)
SELECT
    TO_NUMBER(TO_CHAR(d, 'YYYYMMDD'))  AS date_key,
    d                                   AS calendar_date,
    DAY(d)                              AS day_number_in_month,
    DAYNAME(d)                          AS day_name,
    DAYOFWEEK(d)                        AS day_of_week_number,
    WEEKOFYEAR(d)                       AS week_number,
    MONTH(d)                            AS month_number,
    MONTHNAME(d)                        AS month_name,
    QUARTER(d)                          AS quarter,
    YEAR(d)                             AS year
FROM date_spine;
```

---

## Useful Snowflake Date Functions

| Attribute | Expression |
|---|---|
| Day of month (1–31) | `DAY(d)` |
| Day name | `DAYNAME(d)` → `'Monday'` |
| Day of week (0=Sun) | `DAYOFWEEK(d)` |
| Week of year | `WEEKOFYEAR(d)` |
| Month number | `MONTH(d)` |
| Month name | `MONTHNAME(d)` → `'January'` |
| Quarter (1–4) | `QUARTER(d)` |
| Year | `YEAR(d)` |
| Is weekend | `DAYOFWEEK(d) IN (0, 6)` |
| First day of month | `DAY(d) = 1` |
| Last day of month | `d = LAST_DAY(d)` |
| First day of quarter | `DAY(d) = 1 AND MONTH(d) IN (1, 4, 7, 10)` |

---

## Fiscal Calendar

> **Textbook reference:** Chapter 7 — *Accounting*, "Multiple Fiscal Accounting Calendars." Many organizations run a fiscal year that does not start in January. The textbook shows how to layer fiscal attributes (fiscal year, fiscal month, fiscal quarter) alongside standard calendar attributes within the same date dimension row.

If your organization's fiscal year starts in a month other than January, offset the calendar values. For example, a fiscal year starting in February:

```sql
-- Fiscal year: Feb 1 – Jan 31
-- Add 11 months so Feb becomes month 1 of the new fiscal year
YEAR(DATEADD(month, 11, d))   AS fiscal_year,
MONTH(DATEADD(month, 11, d))  AS fiscal_month
```

Adjust the offset to match the actual fiscal calendar for your scenario.

---

## Resolving Date Keys in Fact Table Loads

> **Textbook reference:** Chapter 6 — *Order Management*, "Role-Playing Dimensions." When the same dimension (like `dim_date`) is referenced multiple times in one fact table with different meanings — created date, close date, ship date — each reference is called a **role**. You JOIN the same physical table multiple times using different alias names; no duplicate physical table is needed.

When loading a fact table, convert a source date column to a `date_key` integer and join:

```sql
LEFT JOIN dim_date_last_fi d
    ON d.date_key = TO_NUMBER(TO_CHAR(source_table.some_date::DATE, 'YYYYMMDD'))
```

Use `LEFT JOIN` (not `INNER JOIN`) so that fact rows with NULL dates are not dropped.

---

## dim_time: Adapting the Pattern

`dim_time` uses the same `GENERATOR` approach but counts **minutes** instead of days:

- `ROWCOUNT => 1440` produces one row per minute of the day (24 × 60)
- `seq4()` counts from 0 (midnight) to 1439 (11:59 PM)
- Hour = `FLOOR(seq4() / 60)`
- Minute = `MOD(seq4(), 60)`
- `time_key` in HHMM format = `(hour * 100) + minute`
