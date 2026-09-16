# Lab 2 (Weeks 5–6)
## Conformed Date & Time Dimensions and Slowly Changing Dimensions

> Before starting, review `lab2_intro.md` for the concepts covered in lecture.

## Lab Overview

In this lab you will extend the dimensional model built in Lab 1 by introducing **conformed date and time dimensions** and upgrading two dimensions to more advanced SCD strategies.

You will:
- Design and populate `dim_date` and `dim_time` as conformed, reusable dimensions
- Refactor the fact table to replace raw date values with surrogate date/time keys
- Upgrade `dim_account` from Type 1 to **Type 2** (full history)
- Upgrade `dim_product` from Type 1 to **Type 3** (prior + current value)
- Use **MERGE INTO** statements to load dimension tables — the production-grade pattern for incremental loads

This lab emphasizes **time-based analysis**, **historical accuracy**, and **modeling judgment**.

> **New in Lab 2:** Dimension loads must use `MERGE INTO` rather than plain `INSERT`. Review `merge_intro.md` before starting the load tasks. `dim_date` and `dim_time` are the only exceptions — they are generated from scratch and use `INSERT...SELECT`.

---

## Learning Objectives

By the end of this lab you will be able to:

1. Design and populate conformed date and time dimensions
2. Identify and model role-playing date relationships
3. Replace raw date/time values in a fact table with surrogate keys
4. Implement SCD Type 2 (full history with effective dates)
5. Implement SCD Type 3 (prior + current attribute tracking)
6. Write a `MERGE INTO` statement to load a dimension table incrementally
7. Justify SCD strategy choices in business terms

---

## Prerequisites

You must have completed **Lab 1**, including:

- A working `fact_opportunity_line_item` loaded with data
- `dim_product`, `dim_account`, and `dim_opportunity` using SCD Type 1
- All tables in `SNOWBEARAIR_DB.MODELED` using your `_LAST_FI` suffix

---

## Business Scenario

Sales and finance leadership now require:

- Analysis by **create date** and **close date** on opportunities
- Consistent time-based reporting that can be reused across future fact tables
- Full **historical tracking of account changes** (industry, size, classification must not overwrite history)
- Limited historical visibility into **product reclassification** (current and prior family only)

---

## Required Tasks

---

### Task 1: Create a Conformed Date Dimension

Create:

```
dim_date
```

**Requirements:**
- Surrogate primary key (`date_key`) — **do not use AUTOINCREMENT**; use the date formatted as an integer (e.g., `20240115` for Jan 15, 2024) so the key is human-readable and self-documenting
- One row per calendar date
- Cover at minimum the full date range present in the source data
- Include **at least 20 descriptive attributes**

**Required attributes (include all of these):**

| Attribute | Description |
|---|---|
| `calendar_date` | The actual DATE value |
| `day_number_in_month` | 1–31 |
| `day_name` | Monday, Tuesday… |
| `day_of_week_number` | 1 (Sun) – 7 (Sat) |
| `week_number` | ISO week of year |
| `month_number` | 1–12 |
| `month_name` | January, February… |
| `quarter` | 1–4 |
| `year` | Full 4-digit year |
| `fiscal_month` | Based on your org's fiscal calendar |
| `fiscal_quarter` | |
| `fiscal_year` | |
| `is_weekend_flag` | BOOLEAN |
| `is_weekday_flag` | BOOLEAN |
| `month_start_flag` | BOOLEAN |
| `month_end_flag` | BOOLEAN |
| `quarter_start_flag` | BOOLEAN |
| `quarter_end_flag` | BOOLEAN |
| `year_start_flag` | BOOLEAN |
| `year_end_flag` | BOOLEAN |

> **Key design note:** `dim_date` must be **independent of any source system** and reusable across all future fact tables. It is populated by generating rows — not by querying Salesforce.

---

### Task 2: Create a Conformed Time Dimension

Create:

```
dim_time
```

**Requirements:**
- Surrogate primary key (`time_key`) — use an integer formatted as `HHMM` (e.g., `1430` for 2:30 PM) for readability
- One row per unique minute of the day (1,440 rows total)
- Required attributes: `hour_value`, `minute_value`, `second_value`, `am_pm_indicator`, `business_hours_flag`

> Even if source data has limited time granularity now, design this dimension to be extensible for future use.

---

### Task 3: Upgrade dim_account to SCD Type 2

Rebuild `dim_account` to support **full historical tracking**.

**Add these columns to the existing structure:**

| Column | Type | Description |
|---|---|---|
| `effective_start_date` | DATE | Date this row became active |
| `effective_end_date` | DATE | Date this row expired (`9999-12-31` if current) |
| `current_flag` | BOOLEAN | `TRUE` for the active row only |

**Requirements:**
- Preserve all existing attributes from Lab 1
- Only one row per account should have `current_flag = TRUE`
- Historical rows are retained and queryable
- Use `CREATE OR REPLACE TABLE` to rebuild the table structure cleanly
- **Load data using a `MERGE INTO` statement** — match on `account_id`, insert new accounts as `WHEN NOT MATCHED`, and for changed accounts use the two-step expire + insert pattern (see `merge_intro.md`)

**Business rationale:** Changes to an account's industry, size, or classification must not overwrite history. Analysts need to ask "what industry was this account in *when the deal closed*?" — that question requires Type 2.

---

### Task 4: Upgrade dim_product to SCD Type 3

Rebuild `dim_product` to track the **current and prior product family**.

**Add this column to the existing structure:**

| Column | Type | Description |
|---|---|---|
| `prior_product_family_name` | VARCHAR(100) | The previous family before the most recent reclassification |

**Requirements:**
- All other attributes continue to use Type 1 behavior (overwrite on change)
- When a product moves to a new family: shift current family → prior, write new family → current
- Use `CREATE OR REPLACE TABLE` to rebuild the table structure cleanly
- **Load data using a `MERGE INTO` statement** — match on `product_id`, insert new products as `WHEN NOT MATCHED`, update changed names/flags as `WHEN MATCHED`

**Business rationale:** The business wants limited historical visibility — enough to compare before/after a reclassification — without the complexity of full Type 2 row versioning.

---

### Task 5: Refactor the Fact Table

Create a new version of `fact_opportunity_line_item` that replaces any raw date/timestamp columns with **foreign keys to `dim_date` and `dim_time`**.

**Requirements:**
- Use `CREATE OR REPLACE TABLE` — rebuild the table cleanly rather than ALTERing
- Add role-playing date keys (the same `dim_date` table used for multiple date relationships):
  - `created_date_key` → references `dim_date`
  - `close_date_key` → references `dim_date`
  - `created_time_key` → references `dim_time` (if source data has time-of-day)
- Keep all existing foreign keys from Lab 1 (`product_key`, `account_key`, `opportunity_key`)
- Keep all measures (`quantity`, `unit_price`, `total_price`)
- No raw DATE or TIMESTAMP columns should remain in the fact table

> **Role-playing reminder:** You do not create separate copies of `dim_date`. You reference it twice with different key column names (`created_date_key`, `close_date_key`). Both columns point to the same `dim_date` table.

---

## Deliverables

1. Updated star schema diagram (MySQL Workbench → export → PNG), or omit if you write full DDL.

2. SQL DDL in a new Snowflake Notebook saved as `LAST_FI_LAB2` in the `MODELED` schema (e.g., `CLARK_C_LAB2`).
   - All table names must include your `_LAST_FI` suffix.
   - Notebook name must be listed in the Canvas text box before item 4.

3. SQL to populate each table in the same notebook:
   - `dim_date` — generated from a date range using `INSERT...SELECT` with Snowflake's `GENERATOR` function (not queried from Salesforce)
   - `dim_time` — generated for all 1,440 minutes using `INSERT...SELECT`
   - `dim_account` — **`MERGE INTO`** for initial load (initial rows enter as `WHEN NOT MATCHED`; see `merge_intro.md` for the two-step Type 2 update pattern)
   - `dim_product` — **`MERGE INTO`** for initial load; `prior_product_family_name` as NULL on first insert
   - Refactored `fact_opportunity_line_item` — `INSERT...SELECT` from source, joining to new date keys

4. Short written explanation in the Canvas text box covering:
   - Why Type 2 was chosen for `dim_account` and not Type 1
   - Why Type 3 was chosen for `dim_product` and not Type 2 or Type 1
   - What role-playing dimensions are and how you used them
