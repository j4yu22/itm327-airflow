# Lab 1 Introduction: Data Warehouse Foundations
### Concepts from Chapters 1–6 | ITM 327

This document connects what you read in the textbook to what you will build in Lab 1. Before jumping into Snowflake, make sure these ideas are solid. Lab 1 will make a lot more sense with them in hand.

---

## 1. Two Worlds of Data: OLTP vs. OLAP

Your textbook draws a sharp line between two types of systems:

| | Operational (OLTP) | Data Warehouse (OLAP) |
|---|---|---|
| **Purpose** | Run the business | Analyze the business |
| **Question** | "Did the order go through?" | "Which products sold best last quarter?" |
| **Unit of work** | One transaction at a time | Hundreds of thousands of rows at a time |
| **History** | Overwritten to reflect current state | Preserved to evaluate performance over time |
| **Structure** | Normalized (3NF) | Dimensional (star schema) |

Salesforce stores your opportunity and line item data in an operational system. Lab 1 asks you to take that normalized OLTP data and reshape it into a dimensional model that analysts can actually query. That reshape is the core skill of this course.

> *"The operational systems are where you put the data in, and the DW/BI system is where you get the data out."* — Kimball, Ch. 1

---

## 2. The Star Schema

With that distinction in mind, let's look at the structure that makes data warehouse queries so fast and intuitive — the star schema.

A dimensional model has two types of tables arranged in a **star schema**:

```
              dim_product
                  |
dim_account ── fact_opportunity_line_item ── (other dims)
                  |
              dim_date
```

### Fact Tables
The center of the star. A fact table stores **numeric measurements** from a business event — things you can count, sum, or average. In Lab 1, that means:

- Quantity sold
- Unit price
- Total price (quantity × unit price)

Every row in the fact table represents **one measurement event** at a specific level of detail. That level of detail is the **grain** (more on this in Section 3).

Fact tables are:
- **Deep** (many rows — potentially millions)
- **Narrow** (few columns — mostly foreign keys and measures)
- **Sparse** (only rows where activity actually occurred)

### Dimension Tables
The points of the star. Dimension tables provide **descriptive context** — the who, what, where, when, and why of each fact. In Lab 1, `dim_product` and `dim_account` describe what was sold and to whom.

Dimension tables are:
- **Wide** (many columns — 50 to 100 attributes is common)
- **Short** (fewer rows than fact tables)
- **Denormalized** (hierarchies are flattened into a single table, not split out)

That last point matters. You might be tempted to normalize `dim_product` — pulling `product_family` into its own table. Resist that urge. The textbook is explicit: dimension table space is small compared to the fact table, so you trade storage efficiency for simplicity and query speed.

---

## 3. The Four-Step Design Process (Kimball)

Now that you know what a star schema looks like, the question becomes: how do you design one? Kimball's four-step process gives you a repeatable approach — and the order matters.

Before writing any DDL, work through these four steps in order. Skipping them, especially Step 2, is where designs go wrong.

### Step 1: Select the Business Process
Identify the **business event** you are measuring — not a department, a process. In Lab 1 the process is: **a product being sold on a Salesforce opportunity**.

### Step 2: Declare the Grain
The grain specifies exactly what one row in your fact table represents. It must be stated precisely, in business terms.

Lab 1 grain: **One row per opportunity line item per product per opportunity.**

> *"The grain statement determines the primary dimensionality of the fact table. Every dimension and fact you add must be consistent with this grain."* — Kimball, Ch. 3

If you can't state the grain clearly before Step 3, stop. The rest of the design will drift.

### Step 3: Identify the Dimensions
Given your grain, ask: "How do business people describe this event?" Every noun that describes the event is a candidate dimension. From the Lab 1 grain you get:

- **Product** — what was sold → `dim_product`
- **Account** — who it was sold to → `dim_account`

### Step 4: Identify the Facts
Ask: "What is the process measuring?" All facts must be consistent with the declared grain. For Lab 1:

- Quantity (additive — can be summed across any dimension)
- Unit price (non-additive — do not sum; average it)
- Total price (additive — can be summed)

---

## 4. Surrogate Keys vs. Natural Keys

Once you've designed the schema, you need to think carefully about how dimension rows are identified — and this is where a lot of first-time warehouse designers make a costly mistake.

Your Salesforce tables have their own identifiers — `product_id`, `account_id`. These are **natural keys** (also called business keys or operational keys). Do **not** use them as the primary key of your dimension tables.

Instead, generate a **surrogate key**: a simple integer assigned by the warehouse, starting at 1, that has no business meaning on its own.

### Why Surrogate Keys?

1. **Buffer from operational changes** — Salesforce can change its key scheme without breaking your warehouse.
2. **Handle multiple sources** — If you later add a second CRM, you can map both sources to a single surrogate key.
3. **Performance** — A 4-byte integer is faster to join than a long alphanumeric string across millions of fact rows.
4. **Enable SCD tracking** — For Type 2 changes (Ch. 5), you may have multiple warehouse rows for the same `product_id`. Only surrogate keys can distinguish them.

In Lab 1 you will implement **Type 1 SCDs**, which use a single surrogate key per dimension member. Keep the `product_id` and `account_id` as **natural key attributes** in your dimension tables for traceability, but let the surrogate key be the primary key.

In Snowflake, the simplest surrogate key approach is `IDENTITY`:

```sql
product_key INTEGER AUTOINCREMENT PRIMARY KEY
```

---

## 5. Slowly Changing Dimensions (SCD)

Surrogate keys also enable something critical: handling dimension attributes that change over time. This is where the concept of Slowly Changing Dimensions comes in — and your choice of strategy determines what historical questions you can answer later.

Dimension attributes change over time — a product moves to a new department, a customer changes industry. How you handle those changes determines what historical questions you can answer later. The textbook names several strategies; Lab 1 uses the two simplest.

### SCD Type 0 — Retain Original

The attribute **never changes** in the warehouse. Whatever value was loaded first is the value forever.

**Use it when:** The original value is the meaningful one — it represents a baseline or a point-in-time fact about the record. Textbook examples include a customer's original credit score or a product's launch date.

> *"The dimension attribute value never changes, so facts are always grouped by this original value."* — Kimball, Ch. 5

**Implementation:** No logic needed. Just don't update it. If the source changes, you ignore the change.

**In Lab 1:** A product's introduction date is a good candidate — once a product launched, that date is historically meaningful and should not be overwritten.

---

### SCD Type 1 — Overwrite

The dimension row is **updated in place** with the new value. The old value is gone.

**Use it when:** History does not matter for this attribute. You only care about the current state, and old reports should reflect the current classification — even if that classification wasn't true at the time.

> *"You overwrite the old attribute value in the dimension row, replacing it with the current value; the attribute always reflects the most recent assignment."* — Kimball, Ch. 5

**Textbook example:**
A product called IntelliKidz originally belongs to the Education department. Later it moves to the Strategy department.

*Before the change:*
| product_key | product_id | product_name | department |
|---|---|---|---|
| 12345 | ABC922-Z | IntelliKidz | Education |

*After a Type 1 update:*
| product_key | product_id | product_name | department |
|---|---|---|---|
| 12345 | ABC922-Z | IntelliKidz | **Strategy** |

The surrogate key (`12345`) does not change. The fact table does not change. But every historical fact row that references `product_key = 12345` now reports under **Strategy** — including sales from before the move. History is rewritten.

**Implementation in Lab 1:** Use `CREATE OR REPLACE TABLE` to reset the table, then reload it with a simple `INSERT INTO ... SELECT`. This is the clean-slate approach — straightforward and sufficient when you're building the schema for the first time.

```sql
-- Type 1 load pattern for Lab 1 — INSERT...SELECT after CREATE OR REPLACE TABLE
INSERT INTO dim_product (product_id, product_name, product_family_name, is_active)
SELECT id, name, family, is_active
FROM SNOWBEARAIR_DB.PUBLIC.product;
```

> **Looking ahead:** In Lab 2 you will upgrade this to a `MERGE INTO` statement — a production-grade pattern that handles new rows and updates without dropping the table. For now, INSERT...SELECT is the right starting point. See `merge_intro.md` for the full picture when you get there.

**Key warning from the textbook:** Type 1 looks easy but invalidates any pre-built aggregate tables and OLAP cubes that included the changed attribute. If you ever build aggregations on top of your star schema, a Type 1 change forces you to recompute them.

---

### Why Not Type 2 Yet?

SCD **Type 2** (add a new row with a new surrogate key each time an attribute changes) is the "primary workhorse" for historical accuracy. It preserves full history and automatically partitions fact table records by the attribute values that were in effect at the time. Lab 1 doesn't require it, but it is covered in Chapter 5 and will appear in later labs. The reason Lab 1 starts with Type 1 is that it is sufficient for most product and account attributes where "current state" is all that's needed for analysis.

---

## 6. Connecting It All to Lab 1

With those concepts in hand, let's map them directly to what you'll build today.

Here is how these concepts map to what you will build:

| Concept | Lab 1 Application |
|---|---|
| Business process | A product sold on a Salesforce opportunity |
| Grain | One row per opportunity line item |
| Fact table | `fact_opportunity_line_item` (quantity, unit price, total price) |
| Dimensions | `dim_product`, `dim_account` |
| Surrogate key | `product_key AUTOINCREMENT`, `account_key AUTOINCREMENT` |
| Natural key | `product_id`, `account_id` kept as attributes |
| SCD Type 0 | Any attribute that reflects a permanent characteristic (e.g., product launch date) |
| SCD Type 1 | Product name, family, active flag, account industry, type — overwrite on change |

When you write the DDL for Task 2 (fact table), start with the dimensions first so the foreign keys you reference already exist. When you write the INSERT/MERGE statements to populate the tables, join the OLTP source tables through the dimension tables to look up surrogate keys — do not load natural keys into the fact table as foreign keys.

---

## Quick Reference: SCD Types 0 and 1

| | Type 0 | Type 1 |
|---|---|---|
| **What happens** | Nothing — original value is kept forever | Dimension row is updated in place |
| **History preserved?** | Yes — original is always there | No — old value is overwritten and lost |
| **New row created?** | No | No |
| **Surrogate key changes?** | No | No |
| **Fact table touched?** | No | No |
| **Aggregates affected?** | No | Yes — must be rebuilt |
| **Good for** | Baseline values, launch dates, durable identifiers | Current-state attributes, classifications, active flags |
