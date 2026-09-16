# Ragged Hierarchies and Bridge Tables in Snowflake

---

## Video Resources

If you prefer to watch before you read, search YouTube for these topics:

| Search Term | What to Look For |
|---|---|
| `ragged hierarchy data warehouse dimensional modeling` | Videos that show an org chart where branches have different depths — look for why fixed-depth columns break down |
| `bridge table hierarchy SQL` | Any video that shows the bridge table structure with `subordinate_key`, `ancestor_key`, and `levels_between` columns |
| `recursive hierarchy SQL self join` | Videos explaining how a self-referencing key (like `manager_id`) works before it gets flattened into a bridge |
| `closure table hierarchy database` | Alternative term for bridge/hierarchy tables — same concept, different name |

**Note:** Dedicated bridge table videos are rare — this is advanced Kimball territory. The written resources below are the authoritative references:

> **Authoritative reference:** [Ralph Kimball — "Building the Hierarchy Bridge Table" (PDF)](http://www.kimballgroup.com/wp-content/uploads/2014/11/Building-the-Hierarchy-Bridge-Table.pdf) — the original whitepaper from the textbook author with full diagrams.

> **Visual walkthrough:** [BigBear.ai — Ragged Hierarchical Dimensions](https://bigbear.ai/blog/data-warehouse-design-techniques-ragged-hierarchical-dimensions/) — compares all four modeling approaches (snowflaking, flatten, recursion, bridge) side by side.

---

## What Is a Ragged Hierarchy?

> **Textbook reference:** Chapter 7 — *Accounting*, "Ragged Variable Depth Hierarchies." The textbook distinguishes fixed-depth hierarchies (every path has the same number of levels) from ragged ones (depths vary by branch). Chapter 9 — *Human Resources Management* extends the pattern to recursive employee org charts as another canonical ragged-hierarchy example.

An organizational hierarchy is **ragged** when the number of reporting levels is not the same for every branch. One VP might have 2 levels of staff below them; another has 5. Some contacts report directly to the CEO; others are deep in the org chart.

```
CEO
├── VP of Sales          (1 level below CEO)
│   ├── Regional Mgr     (2 levels below CEO)
│   │   ├── Rep A        (3 levels below CEO)
│   │   └── Rep B        (3 levels below CEO)
│   └── Rep C            (2 levels below CEO)    ← uneven depth
└── VP of Support        (1 level below CEO)
    └── Agent D          (2 levels below CEO)
```

This unevenness is what makes it "ragged."

---

## Why Fixed-Depth Flattening Breaks Down

A common (but fragile) approach is to add a column for each level:

```sql
level_1_name, level_2_name, level_3_name, level_4_name ...
```

This breaks down because:
- You don't know in advance how many levels exist
- Shallower paths leave columns NULL
- Adding a new org level requires an ALTER TABLE
- Querying "all reports under any manager" requires complex COALESCE logic

---

## The Bridge Table Solution

> **Textbook reference:** Chapter 7 — *Accounting*, "Bridge Tables for Ragged Hierarchies." The textbook introduces the bridge table as the standard solution for variable-depth org hierarchies. Chapter 8 — *Customer Relationship Management* extends the pattern to customer contact networks where one contact can belong to multiple overlapping organizational structures.

A **bridge table** stores every subordinate-ancestor relationship explicitly — one row per pair, regardless of how many levels apart they are.

| contact_key | manager_contact_key | levels_between | top_flag |
|---|---|---|---|
| 5 (Rep A) | 5 (Rep A) | 0 | FALSE |
| 5 (Rep A) | 3 (Regional Mgr) | 1 | FALSE |
| 5 (Rep A) | 2 (VP of Sales) | 2 | FALSE |
| 5 (Rep A) | 1 (CEO) | 3 | TRUE |

Every contact has a row pointing to:
- **Themselves** (`levels_between = 0`) — this makes queries consistent; every contact is their own ancestor
- **Their direct manager** (`levels_between = 1`)
- **Their manager's manager** (`levels_between = 2`)
- And so on up to the top

To find all subordinates of any manager, you simply filter `manager_contact_key = X`.

---

## Building the Bridge: The Self-Join Pattern

> **Textbook reference:** Chapter 9 — *Human Resources Management*, "Recursive Employee Hierarchies." The self-referencing natural key pattern — where a `manager_id` column in an employee table points back to another row in the same table — is the canonical source structure for any org hierarchy before it is flattened into a bridge.

The source of truth is the `manager_contact_id` column in `dim_contact`. This is a **self-referencing natural key** — a contact's manager is another contact in the same table.

To populate the bridge, join `dim_contact` to itself:

```sql
-- The contact is the subordinate
-- The manager is found by matching manager_contact_id to contact_id

SELECT
    c.contact_key          AS contact_key,
    mgr.contact_key        AS manager_contact_key
FROM dim_contact_last_fi       c
JOIN dim_contact_last_fi       mgr
    ON mgr.contact_id = c.manager_contact_id
WHERE c.current_flag  = TRUE
  AND mgr.current_flag = TRUE;
```

---

## Two-Step Loading Approach

Load the bridge in two INSERT statements:

**Step 1 — Self rows** (`levels_between = 0`)

Every contact points to themselves. This ensures that queries against the bridge always return the contact themselves, even at level 0.

```sql
INSERT INTO dim_management_hierarchy_bridge_last_fi (...)
SELECT
    contact_key,       -- subordinate
    contact_key,       -- also the "ancestor" at level 0
    0                  -- levels_between
FROM dim_contact_last_fi
WHERE current_flag = TRUE;
```

**Step 2 — Direct manager rows** (`levels_between = 1`)

Join each contact to their manager using the self-join pattern above.

```sql
INSERT INTO dim_management_hierarchy_bridge_last_fi (...)
SELECT
    c.contact_key,
    mgr.contact_key,
    1
FROM dim_contact_last_fi  c
JOIN dim_contact_last_fi  mgr
    ON mgr.contact_id  = c.manager_contact_id
   AND mgr.current_flag = TRUE
WHERE c.current_flag = TRUE
  AND c.manager_contact_id IS NOT NULL;
```

> **`top_flag`:** Set this to `TRUE` when the manager row has no manager of their own (`manager_contact_id IS NULL`). That identifies the root of the hierarchy.

---

## For Deeper Hierarchies

If your org has more than 2 levels, you need additional INSERT steps — one for each additional level. Each step joins the previous level's results back to `dim_contact` to traverse one level higher.

For the scope of Lab 3, loading self rows and direct manager rows (levels 0 and 1) is sufficient. Real warehouses often use recursive CTEs or procedural logic to traverse all levels automatically.

---

## Querying the Bridge

> **Textbook reference:** Chapter 7 — *Accounting* and Chapter 8 — *CRM* both demonstrate the bridge table JOIN pattern. The key insight is that joining through the bridge expands each fact row to every ancestor of the associated contact, so a single `GROUP BY` rolls up counts and totals to every level of the org chart simultaneously — no recursive SQL needed at query time.

The power of the bridge table is that you can roll up cases (or any fact) to **any ancestor level** with a single JOIN pattern.

**Example: case count by manager, including all subordinates**

```sql
SELECT
    mgr.contact_key,
    COUNT(f.case_fact_key) AS total_cases
FROM fact_support_case_last_fi              f
JOIN dim_contact_last_fi                    c
    ON c.contact_key   = f.contact_key
   AND c.current_flag  = TRUE
JOIN dim_management_hierarchy_bridge_last_fi b
    ON b.contact_key   = c.contact_key
   AND b.current_flag  = TRUE
JOIN dim_contact_last_fi                    mgr
    ON mgr.contact_key = b.manager_contact_key
   AND mgr.current_flag = TRUE
GROUP BY mgr.contact_key;
```

The bridge JOIN `b.contact_key = c.contact_key` expands each case to every ancestor of the assigned contact. Grouping by `mgr.contact_key` rolls the count up to each level of the org chart automatically.
