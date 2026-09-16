# Lab 3 Introduction: Support Case Analytics, Conformed Dimensions, and Ragged Hierarchies
### Concepts from Chapters 8–10 | ITM 327

This document connects what you read in the textbook to what you will build in Lab 3. Labs 1 and 2 gave you a complete star schema for the sales opportunity process. Lab 3 adds a second business process — customer support — and shows what happens when you need to integrate two separate fact tables through shared dimensions.

---

## 1. Conformed Dimensions: The Glue of Integration

So far, every dimension you have built was designed for one specific business process. The real power of dimensional modeling emerges when a dimension is built so that **multiple fact tables can share it exactly as-is**.

> *"Conformed dimensions are the required glue for achieving integration across separate data sources."* — Kimball, Ch. 8

### What "conformed" means

Two dimensions are conformed when they share the same column names and data values for their common attributes. A `dim_account` built once — with the same `account_key`, `account_id`, `account_name`, and `industry_name` — can be joined to a sales fact table *and* a support case fact table. Every report that uses either fact table produces consistent row labels.

> *"Such a single comprehensive conformed dimension becomes a wonderful driver for creating integrated queries, analyses, and reports by making consistent row labels available for drill-across queries."* — Kimball, Ch. 8

### The enterprise bus matrix

Teams that build multiple fact tables use a planning tool called the **bus matrix**:

| Business Process | dim_date | dim_account | dim_product | dim_user | dim_contact |
|---|---|---|---|---|---|
| Opportunity Line Items | X | X | X | | |
| Support Cases | X | X | | X | X |

Each row is a fact table (business process). Each column is a dimension. An **X** means that fact table uses that dimension. Any column with two or more X marks is a conformed dimension — it is shared and must be built consistently across both processes.

In Lab 3, `dim_account` and `dim_date` carry X marks in both rows. That means the `dim_account` and `dim_date` tables you built in Labs 1 and 2 are reused unchanged in Lab 3. No duplication, no inconsistency.

### Drill-across queries

Because conformed dimensions share keys and labels, you can query two fact tables separately and join the results by the shared dimension attribute:

```sql
-- Cases and revenue by account — drilled across two fact tables
SELECT
    a.account_name,
    COUNT(sc.case_fact_key)      AS total_cases,
    SUM(oli.total_price)         AS total_revenue
FROM dim_account a
LEFT JOIN fact_support_case       sc  ON sc.account_key  = a.account_key AND a.current_flag = TRUE
LEFT JOIN fact_opportunity_line_item oli ON oli.account_key = a.account_key AND a.current_flag = TRUE
GROUP BY a.account_name;
```

This works precisely because both fact tables use the same `account_key` from the same `dim_account` table.

---

## 2. Ragged Organizational Hierarchies

In Lab 3, the `contact` table includes a `manager_contact_id` column — a self-referencing pointer. This creates an **organizational hierarchy**: every contact can have a manager, who can have a manager, and so on. The tricky part is that not all branches of the hierarchy have the same depth.

| Contact | Manager | Level |
|---|---|---|
| Maria (VP) | — | 0 |
| Jake (Director) | Maria | 1 |
| Priya (Manager) | Jake | 2 |
| Sam (Analyst) | Priya | 3 |
| Alex (Senior) | Maria | 1 |
| Dana (Analyst) | Alex | 2 |

Maria has 5 people below her through Jake's branch, but only 2 through Alex's branch. The depth is **variable** — that is what makes this a ragged hierarchy.

### Why you cannot just flatten it

The intuitive solution is to add columns like `level_1`, `level_2`, `level_3`, `level_4`. But the textbook is direct about why this fails:

> *"Avoid fixed position hierarchies with abstract names such as Level-1, Level-2, and so on. This is a cheap way to avoid correctly modeling a ragged hierarchy. When the levels have abstract names, the business user has no way of knowing where to place a constraint, or what the attribute values in a level mean in a report."* — Kimball, Ch. 7

The deeper problem is that the hierarchy is not the data — it is metadata about the data. Storing it inside the dimension itself also makes Type 2 nearly impossible to manage:

> *"It is impractical to maintain organizations as type 2 slowly changing dimension attributes because changing the key for a high-level node would ripple key changes down to the bottom of the tree."* — Kimball, Ch. 7

---

## 3. The Bridge Table Solution

The textbook's solution separates the hierarchy structure from the dimension itself:

> *"The solution to the problem of representing arbitrary rollup structures is to build a special kind of bridge table that is independent from the primary dimension table and contains all the information about the rollup."* — Kimball, Ch. 7

### Bridge table grain

> *"The grain of this bridge table is each path in the tree from a parent to all the children below that parent."* — Kimball, Ch. 7

For every ancestor-descendant pair that exists in the hierarchy, you insert **one row**. This includes a row connecting each node to itself (depth = 0). It also includes rows connecting every grandparent to every grandchild, great-grandchild, and so on.

### Bridge table structure

```
dim_management_hierarchy_bridge
  contact_key          — the subordinate (FK to dim_contact)
  manager_contact_key  — the ancestor at any level (FK to dim_contact)
  levels_between       — 0 = self, 1 = direct manager, 2 = skip-level, etc.
  top_flag             — TRUE if the manager row is the top of the hierarchy
  effective_start_date — when this path became valid
  effective_end_date   — 9999-12-31 if currently valid
  current_flag         — quick filter for current hierarchy state
```

A key rule from the textbook: **a row must be constructed from each possible parent to each possible child, including a row that connects the parent to itself.**

### How many rows?

Even a small hierarchy generates many bridge rows. For a 6-person team (Maria → 2 branches → 3 analysts), you would have:
- 6 self-rows (depth = 0)
- 5 direct-manager rows (depth = 1)
- Additional ancestor rows (depth ≥ 2)

This is normal and expected. The tradeoff is storage for simplicity of querying.

### Why this is better than recursive queries

With a bridge table, you never need to write recursive SQL to answer hierarchy questions. To roll up all cases for everyone below a given manager, you use a simple join:

```sql
-- All cases assigned to users who report to a specific manager (any level)
SELECT
    mgr.contact_id          AS manager_id,
    COUNT(f.case_fact_key)  AS total_cases_in_org
FROM dim_contact mgr
JOIN dim_management_hierarchy_bridge b
        ON b.manager_contact_key = mgr.contact_key
        AND b.current_flag = TRUE
JOIN fact_support_case f
        ON f.contact_key = b.contact_key
WHERE mgr.contact_id = '0036X00...'
GROUP BY mgr.contact_id;
```

> *"If you constrain the organization table to a single node and fetch an additive fact from the fact table, you get all hits that traverse the entire tree in a single query... this answer was computed without traversing the tree at query time!"* — Kimball, Ch. 7

This is the core benefit: the bridge table pre-computes all paths at load time, so queries are simple joins — not recursive traversals — at query time.

### Time-varying hierarchies

Reporting structures change when people move or reorganize. The bridge table handles this exactly like Type 2:

> *"The ragged hierarchy bridge table can accommodate slowly changing hierarchies with the addition of two date/time stamps. When a given node no longer is a child of another node, the end effective date/time of the old relationship must be set to the date/time of the change, and new path rows inserted into the bridge table with the correct begin effective date/time."* — Kimball, Ch. 7

**Important:** When querying a time-varying bridge table, always constrain to a single date (or use `current_flag = TRUE`) to avoid fetching multiple overlapping paths that produce double-counting.

---

## 4. Multiple SCD Strategies in One Model

Lab 3 introduces a schema where different dimensions use different SCD types — and that is intentional. The textbook is explicit that there is no universal right answer:

> *"We envision using the type 2 slowly changing dimension technique for tracking changed profile attributes within the employee dimension."* — Kimball, Ch. 10

But for other dimensions with high attribute volatility:

> *"It's unreasonable to rely on type 2 to track changes in the account dimension given the dimension row count and attribute volatility."* — Kimball, Ch. 10

### Choosing by business requirement

| Situation | Type |
|---|---|
| Case status changes constantly; analysts only care about current state | Type 1 |
| Agent changes department; historical workload analysis requires the old department | Type 2 |
| Contact changes manager; escalation patterns need the accurate org at case creation time | Type 2 |
| The date dimension — facts about dates never change | Type 0 |

In Lab 3, `dim_support_case` uses **Type 1** because case status is operational state — analysts want current. `dim_user` and `dim_contact` use **Type 2** because workload and escalation analysis depends on knowing who was where when the case was assigned.

---

## 5. The Fact Table Grain for Support Cases

Grain is still the first decision after identifying the business process.

> *"The grain of the fact table is one row per support case — the most granular, atomic level of the customer support process."* — Kimball pattern

Every case has a single lifecycle: opened, worked, closed (or still open). The fact table captures this with two role-playing date keys (`opened_date_key`, `closed_date_key`) — the same pattern from Lab 2 — and a calculated measure, `resolution_days`.

### Resolution days as a derived measure

`resolution_days` is calculated at load time: `DATEDIFF(day, opened_date, closed_date)`. It is NULL when the case is still open. This is the right approach — store the calculation once rather than recomputing it in every report.

---

## 6. Connecting to Lab 3

| Lab 3 concept | Where it appears |
|---|---|
| Conformed dim_account (reused from Lab 2) | Joins `fact_support_case` to `dim_account` |
| Conformed dim_date (reused from Lab 2) | `opened_date_key` and `closed_date_key` — role-playing |
| SCD Type 1 | `dim_support_case` — case status reflects current operational state |
| SCD Type 2 | `dim_user` and `dim_contact` — historical accuracy for attribution |
| Ragged hierarchy bridge table | `dim_management_hierarchy_bridge` — manager rollup for any level |
| Transaction grain | `fact_support_case` — one row per support case |
| Resolution days measure | Calculated at load time using DATEDIFF |

The single most important new idea in Lab 3 is the bridge table. Everything else builds on patterns you already know.
