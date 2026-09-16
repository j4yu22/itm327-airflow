# Lab 3 (Weeks 6–8)
## Support Case Analytics, Organizational Hierarchies, and Advanced Dimensional Modeling

> Before starting, review `lab3_intro.md` for the concepts covered in lecture.

## Lab Overview

In this lab you will design and implement a **new business process — customer support** — while reusing and extending the dimensional infrastructure built in Labs 1 and 2. This lab tests end-to-end modeling competency: you choose the grain, design the dimensions, handle a ragged hierarchy, and load the data.

You will:
- Design a support case fact table with appropriate grain and measures
- Reuse the conformed `dim_account` and `dim_date` from prior labs
- Create new dimensions with different SCD strategies
- Model a **ragged organizational hierarchy** using a bridge table

This lab emphasizes **integration, historical accuracy, and modeling judgment** — not just mechanical schema translation.

---

## Learning Objectives

By the end of this lab you will be able to:

- Identify and model a new business process using the Kimball 4-step process
- Reuse conformed dimensions across multiple fact tables
- Apply multiple SCD strategies within the same model
- Design fact tables with appropriate grain, foreign keys, and measures
- Model and query a **ragged hierarchy** using a bridge table
- Demonstrate end-to-end dimensional modeling competency

---

## Business Scenario

Customer support leadership wants to analyze:

- Case volume and resolution trends over time
- Case resolution duration (how long cases stay open)
- Support workload by agent and organization
- Customer impact of unresolved or high-priority cases
- Escalation patterns across organizational contacts

Data is sourced from Salesforce **support case, contact, account, and user** tables located in `SNOWBEARAIR_DB.PUBLIC`. Build your notebook in the `MODELED` schema.

---

## Source Tables

Explore these tables in `SNOWBEARAIR_DB.PUBLIC` before designing anything:

- `support_case`
- `account` (reuse the conformed dimension from Labs 1 & 2)
- `contact`
- `salesforce_user`

---

## Required Tasks

---

### Task 1: Declare the Business Process and Grain

Review the source tables and write your grain statement before reading on.

1. What business process are we measuring?
2. What does one row in the fact table represent?

> **Grain:** One row per support case.

---

### Task 2: Create the Support Case Dimension (Type 1)

Create:

```
dim_support_case
```

**Requirements:**
- Surrogate key (`support_case_key`, AUTOINCREMENT)
- Natural key (`case_id`)
- Descriptive attributes: case type, case status, case priority
- **SCD Type 1** — case status and priority reflect the current operational state; no historical preservation needed for this dimension

**Business rationale:** Case status changes frequently (Open → In Progress → Closed) and analysts want to see the current state, not a historical record of every status transition.

---

### Task 3: Create the User Dimension (Type 2)

Create:

```
dim_user
```

**Requirements:**
- Surrogate key (`user_key`, AUTOINCREMENT)
- Natural key (`user_id`)
- Descriptive attributes: full name, title, department, role, active indicator
- **SCD Type 2**, including:
  - `effective_start_date`
  - `effective_end_date` (use `9999-12-31` for the current row)
  - `current_flag` BOOLEAN

**Business rationale:** Changes to an employee's role, department, or title must not overwrite history — they affect workload attribution and performance analysis. A case assigned to a user who was in the "Tier 1 Support" department at the time should still show that, even after the user moves departments.

---

### Task 4: Create the Contact Dimension (Type 2)

Create:

```
dim_contact
```

**Requirements:**
- Surrogate key (`contact_key`, AUTOINCREMENT)
- Natural key (`contact_id`)
- Descriptive attributes: first name, last name, email, title, department
- `manager_contact_id` — natural key of the contact's manager (used for hierarchy; see Task 5)
- **SCD Type 2**, including `effective_start_date`, `effective_end_date`, `current_flag`

**Business rationale:** Contacts change roles and reporting relationships. Preserving this history is essential for accurate escalation and organizational analysis.

---

### Task 5: Model the Ragged Organizational Hierarchy

Using the contact-manager relationship in `dim_contact`, model an organizational hierarchy that handles **variable depth** (some contacts report directly to the top; others are many levels down).

Create a bridge table:

```
dim_management_hierarchy_bridge
```

**Requirements:**
- `contact_key` — the subordinate (FK to `dim_contact`)
- `manager_contact_key` — the ancestor at any level (FK to `dim_contact`)
- `levels_between` — number of levels separating subordinate from ancestor (0 = self)
- `top_flag` — TRUE if the manager row is the top of the hierarchy
- `effective_start_date`, `effective_end_date`, `current_flag` — to handle hierarchy changes over time

**What makes this a ragged hierarchy?** The number of reporting levels is not fixed. A VP may have 2 levels below them in one region and 5 in another. Standard fixed-depth flattening breaks down — a bridge table handles this cleanly.

Include in your notebook:
- The DDL for the bridge table
- An example query that uses the bridge to roll up cases to any ancestor level

---

### Task 6: Create the Support Case Fact Table

Create:

```
fact_support_case
```

**Requirements:**
- Surrogate primary key (`case_fact_key`, AUTOINCREMENT)
- Foreign keys to:
  - `dim_account` (reused from Lab 2 — the conformed dimension)
  - `dim_support_case`
  - `dim_user`
  - `dim_contact`
  - `dim_date` for `opened_date_key`
  - `dim_date` for `closed_date_key` (role-playing — same dimension, two keys)
- Measures:
  - `resolution_days` — integer days from open to close (NULL if still open)

> The fact table must contain **only surrogate keys and measures** — no descriptive text, no natural identifiers.

---

### Task 7: Load All Tables

Populate each table from `SNOWBEARAIR_DB.PUBLIC`. Load in this order (dimensions before fact):

1. `dim_support_case` — INSERT from `support_case`
2. `dim_user` — INSERT from `salesforce_user`; set `effective_start_date = CURRENT_DATE`, `effective_end_date = '9999-12-31'`, `current_flag = TRUE`
3. `dim_contact` — INSERT from `contact`; same Type 2 initial-load defaults
4. `dim_management_hierarchy_bridge` — generate rows from contact self-join (see intro for pattern)
5. `fact_support_case` — INSERT with surrogate key joins; calculate `resolution_days` as `DATEDIFF(day, opened_date, closed_date)`

---

## Deliverables

1. Updated enterprise-level star schema diagram (MySQL Workbench → export → PNG), or omit if full DDL is written.

2. SQL DDL in a Snowflake Notebook saved as `LAST_FI_LAB3` in the `MODELED` schema (e.g., `CLARK_C_LAB3`).
   - All table names must include your `_LAST_FI` suffix.
   - List the notebook name in the Canvas text box before item 4.

3. SQL to populate all tables in the same notebook (Task 7).

4. Written explanation in the Canvas text box covering:
   - Fact grain justification
   - SCD strategy rationale for each dimension
   - Ragged hierarchy design: why a bridge table and how you'd query it
   - At least one modeling tradeoff you considered
