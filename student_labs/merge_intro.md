# Lecture: MERGE vs. Standard INSERT
### Moving from Simple Loads to Production-Grade Upserts | ITM 327

---

## Video Resources

If you prefer to watch before you read, search YouTube for these topics:

| Search Term | What to Look For |
|---|---|
| `slowly changing dimensions SCD type 1 type 2` | Any video that shows a before/after table when a row changes — look for the row being overwritten (Type 1) vs. a new row being added (Type 2) |
| `SCD type 2 expire insert data warehouse` | Videos that walk through the expire + insert pattern step by step |
| `MERGE statement SQL tutorial` | Any SQL MERGE walkthrough showing the WHEN MATCHED / WHEN NOT MATCHED branching |

**Channels with strong SCD/MERGE content:** `techTFQ` · `Bryan Cafferky` · `RADACAD`

> **Visual reference:** [RADACAD — SCD: An Ultimate Guide](https://radacad.com/scd-slowly-changing-dimension-an-ultimate-guide/) has clean before/after diagrams for every SCD type (0–4) if you want a visual companion to this document.

---

## The Problem With INSERT

> **Textbook reference:** Chapter 5 — *Procurement*, "Slowly Changing Dimension Types." The textbook introduces the full SCD type catalog and explains why a simple overwrite strategy (plain INSERT with TRUNCATE) is insufficient for production dimension loads.

By now you have loaded dimension tables using `INSERT INTO ... SELECT`. It works perfectly the first time. But what happens the second time you run it?

```sql
-- First run: 200 accounts loaded ✓
INSERT INTO dim_product (product_id, product_name, product_family_name, is_active)
SELECT id, name, family, is_active
FROM SNOWBEARAIR_DB.PUBLIC.product;

-- Next day: source has 5 new products and 3 name corrections
-- Running this again gives you...
INSERT INTO dim_product (product_id, product_name, product_family_name, is_active)
SELECT id, name, family, is_active
FROM SNOWBEARAIR_DB.PUBLIC.product;
-- ...200 duplicate rows + 5 new rows = 405 rows, 200 of them wrong
```

A plain `INSERT` has no awareness of what already exists in the target. It inserts everything, every time. To avoid duplicates you would need to `TRUNCATE` and reload — which means dropping all your history on a Type 2 dimension.

**This is the problem MERGE solves.**

---

## What MERGE Does

`MERGE` is a single statement that compares a **source** (where new data comes from) against a **target** (your dimension table) using a join condition, then takes different actions depending on whether a match is found.

```
Source row matches a Target row?
    YES (WHEN MATCHED)     → UPDATE the target row
    NO  (WHEN NOT MATCHED) → INSERT a new row
```

One statement handles both cases. No duplicate rows. No full reload required.

---

## Anatomy of a MERGE Statement

```sql
MERGE INTO target_table tgt          -- the table you are loading INTO
USING source_table src               -- where the new data comes from
    ON tgt.natural_key = src.id      -- the join condition (natural key match)

WHEN MATCHED                         -- a row already exists in the target
    AND tgt.some_col != src.some_col -- optional: only update if something changed
THEN UPDATE SET
    tgt.some_col = src.some_col      -- overwrite the old value

WHEN NOT MATCHED                     -- no existing row found
THEN INSERT (col1, col2, ...)        -- insert a brand new row
VALUES (src.col1, src.col2, ...);
```

### The three key clauses

| Clause | When it fires | What it does |
|---|---|---|
| `MERGE INTO ... USING ... ON` | Always | Sets up the comparison — defines source, target, and the join key |
| `WHEN MATCHED` | Source row matches a target row | Runs an UPDATE on the existing target row |
| `WHEN NOT MATCHED` | Source row has no match in target | Runs an INSERT to add a new row |

---

## Side-by-Side: INSERT vs. MERGE

Let's load `dim_product` both ways.

### Scenario
- `dim_product` already has 200 rows from a previous load
- The source has 5 new products and 3 products with updated names
- You want new products added and updated names corrected (Type 1 overwrite)

---

**Option A — INSERT...SELECT (works on a clean slate only)**

```sql
-- Requires CREATE OR REPLACE TABLE first to avoid duplicates
CREATE OR REPLACE TABLE dim_product (
    product_key              INTEGER   AUTOINCREMENT PRIMARY KEY,
    product_id               VARCHAR(18) NOT NULL,
    product_name             VARCHAR(255),
    product_family_name      VARCHAR(100),
    prior_product_family_name VARCHAR(100),
    is_active                BOOLEAN
);

INSERT INTO dim_product (product_id, product_name, product_family_name,
                         prior_product_family_name, is_active)
SELECT id, name, family, NULL, is_active
FROM SNOWBEARAIR_DB.PUBLIC.product;
```

**What happens:** 205 rows inserted cleanly. But you recreated the table — any accumulated `prior_product_family_name` history from prior reclassifications is gone.

---

**Option B — MERGE (handles existing data)**

```sql
MERGE INTO dim_product tgt
USING SNOWBEARAIR_DB.PUBLIC.product src
    ON tgt.product_id = src.id

WHEN MATCHED
    AND tgt.product_name != src.name   -- only update rows that actually changed
THEN UPDATE SET
    tgt.product_name = src.name,
    tgt.is_active    = src.is_active

WHEN NOT MATCHED                       -- brand new products
THEN INSERT (product_id, product_name, product_family_name,
             prior_product_family_name, is_active)
VALUES (src.id, src.name, src.family, NULL, src.is_active);
```

**What happens:** 3 rows updated in place. 5 new rows inserted. The 200 unchanged rows are untouched. No history lost.

---

## Tracing Through a MERGE — Row by Row

Imagine the source has 3 rows and the target currently has 2:

| Source `product_id` | Source `product_name` | Exists in Target? |
|---|---|---|
| ABC-001 | IntelliKidz | YES — name unchanged |
| ABC-002 | IntelliKidz Pro | YES — name changed from "IK Pro" |
| ABC-003 | IntelliKidz Lite | NO — brand new |

After MERGE:

| Target row | Outcome | Why |
|---|---|---|
| ABC-001 | No change | WHEN MATCHED fired, but condition `tgt.product_name != src.name` was FALSE |
| ABC-002 | Updated to "IntelliKidz Pro" | WHEN MATCHED fired, condition was TRUE → UPDATE |
| ABC-003 | New row inserted | WHEN NOT MATCHED fired → INSERT |

---

## MERGE for Type 1 Dimensions

> **Textbook reference:** Chapter 5 — *Procurement*, "Type 1: Overwriting." Type 1 simply replaces the old attribute value with the new one — no history is preserved. MERGE `WHEN MATCHED THEN UPDATE` is the direct implementation of this strategy.

Type 1 is the simplest MERGE use case: match on natural key, update changed attributes, insert new rows.

```sql
-- dim_support_case: Type 1 — case status and priority always reflect current state
MERGE INTO dim_support_case tgt
USING SNOWBEARAIR_DB.PUBLIC.support_case src
    ON tgt.case_id = src.id

WHEN MATCHED
    AND (tgt.case_status   != src.status   OR
         tgt.case_priority != src.priority)
THEN UPDATE SET
    tgt.case_status   = src.status,
    tgt.case_priority = src.priority

WHEN NOT MATCHED
THEN INSERT (case_id, case_type, case_status, case_priority)
VALUES (src.id, src.type, src.status, src.priority);
```

> **Note:** The `AND (...)` condition in `WHEN MATCHED` is optional but recommended. Without it, Snowflake updates every matched row on every run — even rows that did not change. With it, only rows that actually changed are touched, making the load faster and the audit log cleaner.

---

## MERGE for Type 2 Dimensions — Why MERGE Alone Is Not Enough

> **Textbook reference:** Chapter 5 — *Procurement*, "Type 2: Adding a New Row." Type 2 preserves the full change history by inserting a new dimension row rather than overwriting the old one. The old row remains in the table — permanently linked to the fact rows that were loaded while it was current.

Type 2 is different. You do **not** want MERGE to update the existing row — that would overwrite history. Instead, when a tracked attribute changes, you need to:

1. **Expire** the existing row (set `effective_end_date`, flip `current_flag`)
2. **Insert** a brand new row with a new surrogate key

A standard MERGE `WHEN MATCHED THEN UPDATE` would silently overwrite the old values — exactly what Type 2 is designed to prevent.

**The correct Type 2 pattern is a two-step UPDATE + INSERT:**

```sql
-- Step 1: Expire rows where tracked attributes changed
UPDATE dim_account
SET effective_end_date = CURRENT_DATE - 1,
    current_flag       = FALSE
WHERE current_flag = TRUE
  AND account_id IN (
    SELECT id FROM SNOWBEARAIR_DB.PUBLIC.account src
    WHERE src.industry != dim_account.industry_name
       OR src.type     != dim_account.account_type
  );

-- Step 2: Insert new current rows for changed accounts and brand new accounts
INSERT INTO dim_account (
    account_id, account_name, account_type, industry_name,
    billing_state, billing_country, annual_revenue, employee_count,
    effective_start_date, effective_end_date, current_flag
)
SELECT
    src.id, src.name, src.type, src.industry,
    src.billing_state, src.billing_country, src.annual_revenue, src.number_of_employees,
    CURRENT_DATE, '9999-12-31', TRUE
FROM SNOWBEARAIR_DB.PUBLIC.account src
WHERE NOT EXISTS (
    SELECT 1 FROM dim_account tgt
    WHERE tgt.account_id = src.id AND tgt.current_flag = TRUE
);
```

**Why two steps instead of MERGE?**

| Question | MERGE answer | Type 2 requirement |
|---|---|---|
| What happens to the old row? | Updated in place | Expired (kept, but closed off) |
| Does the surrogate key change? | No | Yes — a new row with a new AUTOINCREMENT key |
| Is history preserved? | No — overwritten | Yes — old row remains with its original fact links |

> **Rule of thumb:** MERGE is ideal for Type 1 (overwrite is the goal). Type 2 requires explicit UPDATE + INSERT because you must preserve the old row and generate a new surrogate key.

---

## Common MERGE Mistakes

**Mistake: Joining on surrogate key instead of natural key**
```sql
-- WRONG — surrogate key is generated by Snowflake, the source doesn't have it
MERGE INTO dim_product tgt
USING SNOWBEARAIR_DB.PUBLIC.product src
    ON tgt.product_key = src.product_key   -- ← src has no product_key

-- RIGHT — join on the natural key shared between source and target
MERGE INTO dim_product tgt
USING SNOWBEARAIR_DB.PUBLIC.product src
    ON tgt.product_id = src.id             -- ← natural key match
```

**Mistake: Omitting the change condition in WHEN MATCHED**
```sql
-- This updates every matched row on every run — even unchanged rows
WHEN MATCHED THEN UPDATE SET tgt.product_name = src.name

-- Better — only update rows that actually changed
WHEN MATCHED AND tgt.product_name != src.name THEN UPDATE SET tgt.product_name = src.name
```

**Mistake: Using MERGE for Type 2 and wondering why history disappears**
MERGE `WHEN MATCHED THEN UPDATE` replaces the old values. For Type 2, you want the old row to stay exactly as it was. Use the two-step UPDATE + INSERT pattern instead.

**Mistake: Forgetting WHEN NOT MATCHED**
A MERGE with only `WHEN MATCHED` will update existing rows but silently ignore new ones. Almost always include both clauses.

---

## Quick Reference

```sql
-- Type 1 template — overwrite changed attributes, insert new rows
MERGE INTO dim_table tgt
USING source_table src
    ON tgt.natural_key = src.id
WHEN MATCHED
    AND (tgt.col1 != src.col1 OR tgt.col2 != src.col2)
THEN UPDATE SET
    tgt.col1 = src.col1,
    tgt.col2 = src.col2
WHEN NOT MATCHED
THEN INSERT (natural_key, col1, col2)
VALUES (src.id, src.col1, src.col2);


-- Type 2 template — expire changed rows, insert new current rows
-- Step 1: expire
UPDATE dim_table
SET effective_end_date = CURRENT_DATE - 1,
    current_flag = FALSE
WHERE current_flag = TRUE
  AND natural_key IN (
    SELECT id FROM source_table src
    WHERE src.tracked_col != dim_table.tracked_col
  );

-- Step 2: insert new current rows
INSERT INTO dim_table (natural_key, tracked_col, ...,
                       effective_start_date, effective_end_date, current_flag)
SELECT src.id, src.tracked_col, ...,
       CURRENT_DATE, '9999-12-31', TRUE
FROM source_table src
WHERE NOT EXISTS (
    SELECT 1 FROM dim_table tgt
    WHERE tgt.natural_key = src.id AND tgt.current_flag = TRUE
);
```

---

## Summary

| | INSERT...SELECT | MERGE | Type 2 UPDATE + INSERT |
|---|---|---|---|
| **Handles existing rows** | No — duplicates or requires truncate | Yes | Yes |
| **Preserves old row** | No | No | Yes |
| **New surrogate key on change** | N/A | No | Yes |
| **Best for** | Initial load / clean slate | Type 1 incremental loads | Type 2 incremental loads |
| **Complexity** | Lowest | Medium | Medium |
