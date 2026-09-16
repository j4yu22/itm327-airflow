# SCD Quick Reference Guide
### Slowly Changing Dimensions — Types 0, 1, 2, and 3 | ITM 327

---

## What Is a Slowly Changing Dimension?

Most dimension attributes are not static. A customer moves. An employee gets promoted. A product gets reclassified. A **Slowly Changing Dimension (SCD)** strategy defines *how* the data warehouse responds when a dimension attribute changes.

Choosing the wrong strategy corrupts historical analysis. Choosing the right one depends on a single question: **does history matter for this attribute?**

---

## At a Glance

| Type | Name | What Happens When an Attribute Changes | Preserves History? |
|---|---|---|---|
| **0** | Retain Original | Nothing — the old value is locked forever | The original value only |
| **1** | Overwrite | Old value is replaced with the new value | No — history is lost |
| **2** | Add New Row | A new dimension row is inserted; the old row is expired | Yes — full history |
| **3** | Add Prior Column | The current value moves to a `prior_` column; the new value replaces it | One level only |

---

## Type 0 — Retain Original

### What it does
The value is set once at load time and **never updated**, regardless of what changes in the source system.

### When to use it
- The attribute is a historical fact that should never change
- The original value is what matters for business analysis
- Example: `date_key` in `dim_date` — March 15, 2024 will always be a Friday in Q1

### Lab examples
- `dim_date` — every attribute (day_name, quarter, fiscal_year) is calculated once and locked
- `dim_time` — hour and minute values are fixed facts

### DDL pattern
No special columns needed. Simply do not include this attribute in any UPDATE or MERGE statement.

```sql
-- dim_date is never updated — rows are inserted once for the full date range
CREATE OR REPLACE TABLE dim_date (
    date_key            INTEGER     PRIMARY KEY,  -- YYYYMMDD, e.g. 20240315
    calendar_date       DATE        NOT NULL,
    day_name            VARCHAR(30),
    quarter             INTEGER     NOT NULL,
    year                INTEGER     NOT NULL,
    is_weekend_flag     BOOLEAN     NOT NULL DEFAULT FALSE
    -- ... no effective dates, no current_flag — Type 0 needs no admin columns
);
```

### Key rule
> *"The date dimension is populated by calculating the attributes for every date in a defined range — not by querying source systems."* — Kimball

---

## Type 1 — Overwrite

### What it does
When an attribute changes in the source, the dimension row is **updated in place**. The old value is gone.

### When to use it
- Only the current value matters for analysis
- Historical accuracy is not needed for this attribute
- Example: correcting a typo in an account name, updating a case status (Open → Closed)

### What you lose
Any fact rows that pointed to this dimension row now reflect the new attribute value, even if they were loaded before the change. This is **intentional** for Type 1 — if you don't want this behavior, use Type 2.

### Lab examples
- `dim_support_case` — case status and priority reflect current operational state; analysts want to filter on where cases stand *now*
- `dim_product` for most attributes (product name, product code) — corrections are overwritten

### DDL pattern
No special columns needed.

```sql
CREATE OR REPLACE TABLE dim_support_case (
    support_case_key    INTEGER     AUTOINCREMENT PRIMARY KEY,
    case_id             VARCHAR(18) NOT NULL,
    case_type           VARCHAR(50),
    case_status         VARCHAR(50),   -- Type 1: overwritten when status changes
    case_priority       VARCHAR(20)    -- Type 1: overwritten when priority changes
    -- No effective_start_date, no current_flag
);
```

### Load / update pattern

**Option A — INSERT...SELECT (starting point)**
Works cleanly when the table was just created with `CREATE OR REPLACE TABLE` (clean slate). Simple to write and understand.

```sql
INSERT INTO dim_support_case (case_id, case_type, case_status, case_priority)
SELECT id, type, status, priority
FROM SNOWBEARAIR_DB.PUBLIC.support_case;
```

To re-sync current values after a `CREATE OR REPLACE TABLE`, simply re-run the INSERT. Because the table is dropped and recreated, there is no duplicate key risk.

**Option B — MERGE (best practice)**
Production-grade upsert that handles both new rows and in-place updates without recreating the table. This is the preferred pattern for incremental loads.

```sql
MERGE INTO dim_support_case tgt
USING SNOWBEARAIR_DB.PUBLIC.support_case src
    ON tgt.case_id = src.id
WHEN MATCHED AND (
    tgt.case_status   != src.status   OR
    tgt.case_priority != src.priority
) THEN UPDATE SET
    tgt.case_status   = src.status,
    tgt.case_priority = src.priority
WHEN NOT MATCHED THEN INSERT (
    case_id, case_type, case_status, case_priority
) VALUES (
    src.id, src.type, src.status, src.priority
);
```

---

## Type 2 — Add New Row

### What it does
When a tracked attribute changes, the old dimension row is **expired** (not deleted) and a **new row** is inserted with a new surrogate key. Fact rows loaded before the change still point to the old row. New fact rows point to the new row.

### When to use it
- Historical accuracy is required — you need to know the attribute's value *at the time* a fact was recorded
- Example: an account's industry at the time a deal closed, an employee's department when a case was assigned

### What you gain
Complete, unambiguous point-in-time history. A fact row is permanently linked to the dimension row that was current when the fact was created.

### Lab examples
- `dim_account` — if Acme Corp moves from Retail to Technology, January deals still show Retail
- `dim_user` — if an agent moves from Tier 1 to Tier 2, historical cases still show Tier 1
- `dim_contact` — if a contact changes manager, old escalation paths remain accurate

### The three required admin columns

| Column | Purpose |
|---|---|
| `effective_start_date` | First date this row's values were valid |
| `effective_end_date` | Last date valid; use `9999-12-31` for the current row |
| `current_flag` | Boolean shortcut for filtering to the current row |

### DDL pattern

```sql
CREATE OR REPLACE TABLE dim_user (
    user_key                INTEGER     AUTOINCREMENT PRIMARY KEY,
    user_id                 VARCHAR(18) NOT NULL,         -- natural key (not unique)
    full_name               VARCHAR(255),
    title                   VARCHAR(100),
    department              VARCHAR(100),                 -- Type 2: changes create new rows
    role                    VARCHAR(100),                 -- Type 2: changes create new rows
    is_active               BOOLEAN,
    -- Type 2 admin columns
    effective_start_date    DATE        NOT NULL,
    effective_end_date      DATE        NOT NULL DEFAULT '9999-12-31',
    current_flag            BOOLEAN     NOT NULL DEFAULT TRUE
);
```

### Initial load pattern

```sql
-- First time loading: every row is current
INSERT INTO dim_user (
    user_id, full_name, title, department, role, is_active,
    effective_start_date, effective_end_date, current_flag
)
SELECT
    id, name, title, department, user_role, is_active,
    CURRENT_DATE,   -- effective_start_date
    '9999-12-31',   -- effective_end_date
    TRUE            -- current_flag
FROM SNOWBEARAIR_DB.PUBLIC.salesforce_user;
```

### Incremental update pattern

**Option A — INSERT...SELECT (starting point)**
After a `CREATE OR REPLACE TABLE`, the initial INSERT doubles as a full load. Re-running it on a fresh table is the simplest way to reset and reload without managing update logic.

```sql
-- Re-run after CREATE OR REPLACE TABLE to reload all users as current rows
INSERT INTO dim_user (
    user_id, full_name, title, department, role, is_active,
    effective_start_date, effective_end_date, current_flag
)
SELECT
    id, name, title, department, user_role, is_active,
    CURRENT_DATE,
    '9999-12-31',
    TRUE
FROM SNOWBEARAIR_DB.PUBLIC.salesforce_user;
```

> **Limitation:** This approach only works on a clean slate. It does not preserve existing history rows because `CREATE OR REPLACE TABLE` drops everything. Once you have accumulated historical rows you care about, use Option B.

**Option B — Two-step UPDATE + INSERT (best practice)**
The production-grade Type 2 pattern. Never drops the table — it expires changed rows in place and inserts new current rows alongside the expired history.

```sql
-- Step 1: Expire rows where tracked attributes changed
UPDATE dim_user
SET effective_end_date = CURRENT_DATE - 1,
    current_flag       = FALSE
WHERE current_flag = TRUE
  AND user_id IN (
    SELECT id FROM SNOWBEARAIR_DB.PUBLIC.salesforce_user src
    WHERE src.department != dim_user.department
       OR src.user_role  != dim_user.role
  );

-- Step 2: Insert new current rows for changed and new users
INSERT INTO dim_user (
    user_id, full_name, title, department, role, is_active,
    effective_start_date, effective_end_date, current_flag
)
SELECT
    src.id, src.name, src.title, src.department, src.user_role, src.is_active,
    CURRENT_DATE, '9999-12-31', TRUE
FROM SNOWBEARAIR_DB.PUBLIC.salesforce_user src
WHERE NOT EXISTS (
    SELECT 1 FROM dim_user tgt
    WHERE tgt.user_id = src.id AND tgt.current_flag = TRUE
);
```

### Query patterns

```sql
-- Current rows only (most common)
SELECT * FROM dim_user WHERE current_flag = TRUE;

-- Point-in-time: what was this user's department on Jan 15, 2024?
SELECT * FROM dim_user
WHERE user_id = '0056X...'
  AND effective_start_date <= '2024-01-15'
  AND effective_end_date   >= '2024-01-15';

-- Join fact to dimension: always filter current_flag = TRUE for current analysis
SELECT u.department, COUNT(f.case_fact_key) AS case_count
FROM fact_support_case f
JOIN dim_user u ON u.user_key = f.user_key   -- surrogate key links to the right version
GROUP BY u.department;
-- Note: no current_flag filter needed when joining via surrogate key —
-- the surrogate key already pinpoints the exact historical row.
-- Only add current_flag = TRUE when joining on natural key (user_id).
```

---

## Type 3 — Add Prior Column

### What it does
When a specific attribute changes, the current value is **shifted to a `prior_` column** and the new value replaces the current column. Only one level of history is ever tracked.

### When to use it
- The business only needs "current vs. previous" — not full history
- The attribute changes infrequently
- Analysts need to report using *both* the old and new classification simultaneously

### What you lose
If the attribute changes a third time, the original (first) value is gone. Type 3 cannot answer "what was the value two changes ago?"

### Lab examples
- `dim_product` — the business tracks current and prior `product_family_name` to compare revenue across reclassifications. Full audit trail not required.

### DDL pattern

```sql
CREATE OR REPLACE TABLE dim_product (
    product_key                 INTEGER     AUTOINCREMENT PRIMARY KEY,
    product_id                  VARCHAR(18) NOT NULL,
    product_name                VARCHAR(255),
    product_code                VARCHAR(50),
    product_family_name         VARCHAR(100),              -- Type 3: current value
    prior_product_family_name   VARCHAR(100),              -- Type 3: one prior value
    is_active                   BOOLEAN
    -- No effective dates, no current_flag — Type 3 has no row versioning
);
```

### Initial load pattern

```sql
-- Initial load: prior column is NULL (no prior history yet)
INSERT INTO dim_product (
    product_id, product_name, product_code,
    product_family_name, prior_product_family_name, is_active
)
SELECT
    id, name, product_code,
    family,
    NULL    AS prior_product_family_name,
    is_active
FROM SNOWBEARAIR_DB.PUBLIC.product;
```

### Update pattern (when the attribute changes)

```sql
-- Shift current → prior, then set the new current value
UPDATE dim_product
SET
    prior_product_family_name = product_family_name,     -- archive current as prior
    product_family_name       = src.family               -- set new current
FROM SNOWBEARAIR_DB.PUBLIC.product src
WHERE dim_product.product_id = src.id
  AND dim_product.product_family_name != src.family;    -- only update changed rows
```

### Query patterns

```sql
-- Report using current family
SELECT product_family_name, SUM(total_price)
FROM fact_opportunity_line_item f
JOIN dim_product p ON p.product_key = f.product_key
GROUP BY product_family_name;

-- Report using prior family (for historical comparison)
SELECT prior_product_family_name AS old_family, SUM(total_price) AS revenue
FROM fact_opportunity_line_item f
JOIN dim_product p ON p.product_key = f.product_key
WHERE prior_product_family_name IS NOT NULL
GROUP BY prior_product_family_name;
```

---

## Decision Guide

Work through these questions in order:

```
Is this attribute a permanent historical fact (a date, an original score)?
    YES → Type 0 (retain original, never update)
    NO  ↓

Does the business need to analyze history for this attribute?
    NO  → Type 1 (overwrite — simplest, history not preserved)
    YES ↓

Does the business need full point-in-time accuracy (any historical date)?
    YES → Type 2 (add new row — full history, new surrogate key)
    NO  ↓

Does the business only need current vs. one prior value?
    YES → Type 3 (add prior column — lightweight, one level of history)
```

---

## Side-by-Side Comparison

|  | Type 0 | Type 1 | Type 2 | Type 3 |
|---|---|---|---|---|
| **Rows added on change** | 0 | 0 | 1 new row | 0 |
| **Old value preserved** | Always | Never | In expired row | In `prior_` column |
| **Surrogate key changes** | No | No | Yes (new key) | No |
| **Admin columns needed** | None | None | effective_start_date, effective_end_date, current_flag | None |
| **History depth** | Original only | None | Unlimited | One prior |
| **Complexity** | Lowest | Low | Moderate | Low |
| **Storage impact** | None | None | Row multiplies | One extra column |
| **Lab 1–3 examples** | dim_date, dim_time | dim_support_case | dim_account, dim_user, dim_contact | dim_product |

---

## Common Mistakes

**Mistake: Using Type 1 when analysts need historical accuracy**
A case status of "Closed" that overwrites "Open" is fine. But an account industry that overwrites the industry at the time a deal closed corrupts revenue-by-industry reports. Ask: "If someone queries this fact row one year from now, should the dimension attribute reflect what it was *then* or what it is *now*?"

**Mistake: Joining a Type 2 dimension on natural key without filtering `current_flag`**
```sql
-- WRONG — returns multiple rows per account (all historical versions)
SELECT a.industry_name, SUM(f.total_price)
FROM fact_opportunity_line_item f
JOIN dim_account a ON a.account_id = f.account_id   -- ← natural key join
GROUP BY a.industry_name;

-- RIGHT — join on surrogate key (fact table stores the right version already)
SELECT a.industry_name, SUM(f.total_price)
FROM fact_opportunity_line_item f
JOIN dim_account a ON a.account_key = f.account_key  -- ← surrogate key join
GROUP BY a.industry_name;
```

**Mistake: Forgetting `9999-12-31` for effective_end_date on current rows**
Using NULL for open-ended rows forces every query to handle `IS NULL` logic. Using `9999-12-31` allows clean `BETWEEN` queries and consistent behavior.

**Mistake: Applying Type 2 to everything "just to be safe"**
Type 2 multiplies rows and complexity. Use it where history is genuinely required. A product's `is_active` flag or a case's subject line probably does not need full row versioning.
