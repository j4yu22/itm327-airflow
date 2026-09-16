## Lab 1 (Weeks 2–4):
### Opportunity Line Item Dimensional Model (Foundations)

> Before starting, review `lab1_intro.md` for the concepts covered in lecture.

### Learning Objectives

By the end of this lab, students will be able to:

- Identify a business process and declare its grain
- Design a transaction fact table
- Create basic dimension tables
- Apply a **Slowly Changing Dimension Type 1** strategy
- Translate an OLTP schema into a star schema
- Transfer data into a star schema

---

## Business Scenario

Sales leadership wants to analyze **product-level revenue** by customer and product across sales opportunities. Data is sourced from Salesforce opportunity and opportunity line item data. The data is located in the `SNOWBEARAIR_DB.PUBLIC` schema, and you should create your notebook in the `MODELED` schema.

---

## Source Tables

Explore the following OLTP tables in `SNOWBEARAIR_DB.PUBLIC` before designing anything:

- `opportunity_line_item`
- `opportunity`
- `account`
- `product`

---

## Required Tasks

### Task 1: Declare the Business Process and Grain

Review the source tables and answer the following before reading on:

1. What business process are we measuring?
2. What does one row in your fact table represent?

Write your grain statement in plain English (e.g., "One row per...").

> **Grain:** One row per opportunity line item per product per opportunity.

---

### Task 2: Design the Product Dimension (Type 1)

Create:

```
dim_product
```

Requirements:

- Surrogate key (`product_key`)
- Natural key (`product_id`)
- Descriptive attributes (name, product code, family, active flag)
- **Type 1 SCD strategy** (overwrite on change — current values only)

---

### Task 3: Design the Account Dimension (Type 1)

Create:

```
dim_account
```

Requirements:

- Surrogate key (`account_key`)
- Natural key (`account_id`)
- Descriptive attributes (name, type, industry, billing state, annual revenue, number of employees)
- **Type 1 SCD strategy**

---

### Task 4: Design the Opportunity Dimension (Type 1)

Create:

```
dim_opportunity
```

Requirements:

- Surrogate key (`opportunity_key`)
- Natural key (`opportunity_id`)
- Descriptive attributes (name, stage, close date, type)
- **Type 1 SCD strategy**

---

### Task 5: Design the Fact Table

Create a **transaction fact table** named:

```
fact_opportunity_line_item
```

The fact table must include:

- A surrogate primary key
- Foreign keys to:
  - `dim_product`
  - `dim_account`
  - `dim_opportunity`
- Measures:
  - Quantity
  - Unit price
  - Total price

---

## Deliverables

1. Upload your star schema diagram (MySQL Workbench file --> export --> png). If you chose to write out the SQL DDL instead, you may omit this submission.

2. SQL DDL for all dimension and fact tables in a Snowflake Notebook saved as `LAST_FI_LAB1` in the `MODELED` schema (e.g., `CLARK_C_LAB1`).
   - Comment your notebook name in the Canvas text box before your write-up for item 4.
   - All table names must include your `_LAST_FI` suffix (e.g., `dim_product_clark_c`).

3. SQL to populate each table from the OLTP source tables in `SNOWBEARAIR_DB.PUBLIC`. Write this in the same notebook as item 2.

   Use `INSERT INTO ... SELECT` for each dimension load. For the fact table, join through the dimension tables to resolve surrogate keys — do not load natural keys as foreign keys into the fact table.

   Example pattern for the fact table load (resolve surrogate keys via joins):
   ```sql
   INSERT INTO fact_opportunity_line_item_last_fi (
     product_key, account_key, opportunity_key,
     quantity, unit_price, total_price
   )
   SELECT
     p.product_key,
     a.account_key,
     o.opportunity_key,
     oli.quantity,
     oli.unit_price,
     oli.total_price
   FROM SNOWBEARAIR_DB.PUBLIC.opportunity_line_item oli
   JOIN dim_product_last_fi     p ON p.product_id     = oli.product_id
   JOIN dim_opportunity_last_fi o ON o.opportunity_id = oli.opportunity_id
   JOIN dim_account_last_fi     a ON a.account_id     = (SELECT account_id FROM SNOWBEARAIR_DB.PUBLIC.opportunity WHERE id = oli.opportunity_id);
   ```

4. Short write-up in the Canvas text box explaining:
   - Your grain choice and why
   - Which SCD type you applied and why Type 1 is appropriate for each dimension in this lab
