# Data model — ERD & lineage

How the marts relate to each other (ERD), and how each one is built up from the
Salesforce + NetSuite sources (DAGs). All diagrams are Mermaid and render directly on
GitHub.

---

## Entity-relationship diagram (the star schema)

Three conformed dimensions fan out to four facts via surrogate keys
(`account_key`, `product_key`, `sales_rep_key`).

```mermaid
erDiagram
    DIM_ACCOUNT   ||--o{ FCT_ACV                        : account_key
    DIM_ACCOUNT   ||--o{ FCT_ARR                        : account_key
    DIM_ACCOUNT   ||--o{ FCT_USAGE                      : account_key
    DIM_ACCOUNT   ||--o{ RPT_CONTRACT_TO_NETSUITE_RECON : account_key
    DIM_PRODUCT   ||--o{ FCT_ACV                        : product_key
    DIM_PRODUCT   ||--o{ FCT_ARR                        : product_key
    DIM_PRODUCT   ||--o{ FCT_USAGE                      : product_key
    DIM_SALES_REP ||--o{ FCT_ACV                        : sales_rep_key

    DIM_ACCOUNT {
        string account_key PK
        string account_id
        string segment
        string geo_region
        string division
        string industry
        number current_arr
    }
    DIM_PRODUCT {
        string product_key PK
        string product_id
        string line_of_business
        string product_family
        boolean is_recurring
    }
    DIM_SALES_REP {
        string sales_rep_key PK
        string user_id
        string sales_region
        string sales_team
    }
    FCT_ACV {
        string acv_key PK
        string account_key FK
        string product_key FK
        string sales_rep_key FK
        date close_date
        string revenue_category
        number acv
        number tcv
    }
    FCT_ARR {
        string arr_key PK
        string account_key FK
        string product_key FK
        date measurement_month
        string revenue_category
        number beginning_arr
        number ending_arr
    }
    FCT_USAGE {
        string usage_key PK
        string account_key FK
        string product_key FK
        date usage_month
        number entitled_units
        number utilization_pct
    }
    RPT_CONTRACT_TO_NETSUITE_RECON {
        string recon_key PK
        string account_key FK
        string match_status
        string discrepancy_category
        number amount_variance
    }
```

**Grains:** `fct_acv` = one opportunity line · `fct_arr` = account × product × month-end ·
`fct_usage` = account × product × month · `rpt_contract_to_netsuite_recon` = contract ↔ order.

---

## End-to-end lineage

Sources → seeds → staging (views) → intermediate (views) → marts (tables) → semantic layer.

```mermaid
flowchart LR
    classDef src fill:#e8eef6,stroke:#5b7aa6,color:#16222e;
    classDef stg fill:#eaf4ee,stroke:#3f9d6d,color:#16222e;
    classDef int fill:#fdf1e0,stroke:#d99a2b,color:#16222e;
    classDef mart fill:#e9eefc,stroke:#3f57b0,color:#16222e;
    classDef sem fill:#f3e9f6,stroke:#9b59b6,color:#16222e;

    subgraph SRC["Sources (CSV seeds emulate landed tables)"]
        SF["Salesforce CRM"]:::src
        NS["NetSuite ERP"]:::src
        UZ["Usage telemetry"]:::src
    end
    subgraph STG["staging — views"]
        STGN["stg_salesforce__*<br/>stg_netsuite__*<br/>stg_usage__monthly"]:::stg
    end
    subgraph INT["intermediate — views"]
        IACV["int_opportunity_lines__acv"]:::int
        IARR["int_contract_lines__normalized<br/>int_arr__account_product_month<br/>int_arr__movements"]:::int
        IUSE["int_usage__monthly_rollup"]:::int
        IREC["int_recon__contract_order_match"]:::int
    end
    subgraph MART["marts — tables"]
        DIMS["dim_account · dim_product · dim_sales_rep"]:::mart
        FACTS["fct_acv · fct_arr · fct_usage · rpt_contract_to_netsuite_recon"]:::mart
    end
    SEM["MetricFlow semantic layer<br/>(~20 metrics: ARR, NRR/GRR, bookings, ASP…)"]:::sem

    SF --> STGN
    NS --> STGN
    UZ --> STGN
    STGN --> IACV --> FACTS
    STGN --> IARR --> FACTS
    STGN --> IUSE --> FACTS
    STGN --> IREC --> FACTS
    STGN --> DIMS
    IARR --> DIMS
    DIMS --> FACTS
    FACTS --> SEM
```

---

## How each mart is built

### `fct_arr` — the ARR waterfall

```mermaid
flowchart LR
    classDef seed fill:#e8eef6,stroke:#5b7aa6;
    classDef stg fill:#eaf4ee,stroke:#3f9d6d;
    classDef int fill:#fdf1e0,stroke:#d99a2b;
    classDef mart fill:#e9eefc,stroke:#3f57b0,stroke-width:2px;

    A["salesforce_subscriptions"]:::seed --> B["stg_salesforce__subscriptions"]:::stg
    C["salesforce_products"]:::seed --> D["stg_salesforce__products"]:::stg
    B --> E["int_contract_lines__normalized"]:::int
    D --> E
    E --> F["int_arr__account_product_month<br/>monthly spine, densified"]:::int
    F --> G["int_arr__movements<br/>MoM classification"]:::int
    G --> H["fct_arr"]:::mart
```

### `fct_acv` — bookings & pipeline

```mermaid
flowchart LR
    classDef seed fill:#e8eef6,stroke:#5b7aa6;
    classDef stg fill:#eaf4ee,stroke:#3f9d6d;
    classDef int fill:#fdf1e0,stroke:#d99a2b;
    classDef mart fill:#e9eefc,stroke:#3f57b0,stroke-width:2px;

    A["salesforce_opportunity_line_items"]:::seed --> SA["stg_salesforce__opportunity_line_items"]:::stg
    B["salesforce_opportunities"]:::seed --> SB["stg_salesforce__opportunities"]:::stg
    C["salesforce_products"]:::seed --> SC["stg_salesforce__products"]:::stg
    D["salesforce_users"]:::seed --> SD["stg_salesforce__users"]:::stg
    SA --> I["int_opportunity_lines__acv<br/>ACV/TCV + revenue category"]:::int
    SB --> I
    SC --> I
    SD --> I
    I --> M["fct_acv"]:::mart
```

### `fct_usage` — consumption vs entitlement

```mermaid
flowchart LR
    classDef seed fill:#e8eef6,stroke:#5b7aa6;
    classDef stg fill:#eaf4ee,stroke:#3f9d6d;
    classDef int fill:#fdf1e0,stroke:#d99a2b;
    classDef mart fill:#e9eefc,stroke:#3f57b0,stroke-width:2px;

    U["usage_monthly"]:::seed --> SU["stg_usage__monthly"]:::stg
    SU --> RU["int_usage__monthly_rollup<br/>consumption"]:::int
    E["int_arr__account_product_month<br/>entitlement"]:::int --> M["fct_usage"]:::mart
    RU --> M
```

### `rpt_contract_to_netsuite_recon` — Salesforce ↔ NetSuite

```mermaid
flowchart LR
    classDef seed fill:#e8eef6,stroke:#5b7aa6;
    classDef stg fill:#eaf4ee,stroke:#3f9d6d;
    classDef int fill:#fdf1e0,stroke:#d99a2b;
    classDef mart fill:#e9eefc,stroke:#3f57b0,stroke-width:2px;

    A["salesforce_contracts"]:::seed --> SA["stg_salesforce__contracts"]:::stg
    B["netsuite_sales_orders"]:::seed --> SB["stg_netsuite__sales_orders"]:::stg
    C["netsuite_customers"]:::seed --> SC["stg_netsuite__customers"]:::stg
    D["netsuite_invoices"]:::seed --> SD["stg_netsuite__invoices"]:::stg
    SA --> R["int_recon__contract_order_match<br/>FULL OUTER JOIN on external_order_ref"]:::int
    SB --> R
    SC --> R
    SD --> R
    R --> M["rpt_contract_to_netsuite_recon"]:::mart
```

### `dim_account` — conformed customer dimension

```mermaid
flowchart LR
    classDef seed fill:#e8eef6,stroke:#5b7aa6;
    classDef stg fill:#eaf4ee,stroke:#3f9d6d;
    classDef int fill:#fdf1e0,stroke:#d99a2b;
    classDef mart fill:#e9eefc,stroke:#3f57b0,stroke-width:2px;

    A["stg_salesforce__accounts"]:::stg --> M["dim_account"]:::mart
    B["stg_salesforce__users<br/>owner"]:::stg --> M
    C["stg_netsuite__customers<br/>NetSuite bridge"]:::stg --> M
    D["stg_salesforce__contracts<br/>first_contract_date"]:::stg --> M
    E["int_arr__account_product_month<br/>current_arr"]:::int --> M
```

> `dim_product` (stg_salesforce__products + stg_netsuite__items) and `dim_sales_rep`
> (stg_salesforce__users) are direct staging → dimension build-ups.
