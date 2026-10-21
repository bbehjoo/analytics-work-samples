-- ============================================================================
-- Production reference (BigQuery). Not run locally.
-- Who can read which dataset. The local DuckDB build has no users, so the same
-- boundaries are enforced there by schema layout and proved by the dbt tests.
--
-- Each dbt schema is a BigQuery dataset. People data sits in its own datasets,
-- and each secure_<role> dataset is granted to exactly one group.
-- ============================================================================

-- Raw and core HR data: the People Analytics pipeline only. No human readers.
GRANT `roles/bigquery.dataViewer` ON SCHEMA `saasco-analytics.raw_hris`       TO "serviceAccount:dbt-people@saasco-analytics.iam.gserviceaccount.com";
GRANT `roles/bigquery.dataViewer` ON SCHEMA `saasco-analytics.people_staging` TO "serviceAccount:dbt-people@saasco-analytics.iam.gserviceaccount.com";
GRANT `roles/bigquery.dataViewer` ON SCHEMA `saasco-analytics.people`         TO "serviceAccount:dbt-people@saasco-analytics.iam.gserviceaccount.com";

-- One secure dataset per role. Members of a group see their view and nothing else.
GRANT `roles/bigquery.dataViewer` ON SCHEMA `saasco-analytics.secure_hr`                 TO "group:hr-partners@saasco.com";
GRANT `roles/bigquery.dataViewer` ON SCHEMA `saasco-analytics.secure_finance`            TO "group:finance@saasco.com";
GRANT `roles/bigquery.dataViewer` ON SCHEMA `saasco-analytics.secure_sales_manager_emea` TO "group:sales-managers-emea@saasco.com";
GRANT `roles/bigquery.dataViewer` ON SCHEMA `saasco-analytics.secure_analyst`            TO "group:analysts@saasco.com";
GRANT `roles/bigquery.dataViewer` ON SCHEMA `saasco-analytics.secure_ai_agent`           TO "serviceAccount:ai-agent@saasco-analytics.iam.gserviceaccount.com";

-- Suppressed aggregates: anyone in the company.
GRANT `roles/bigquery.dataViewer` ON SCHEMA `saasco-analytics.people_metrics` TO "domain:saasco.com";

-- Revenue marts: everyone who works on revenue.
GRANT `roles/bigquery.dataViewer` ON SCHEMA `saasco-analytics.marts` TO "group:revenue-readers@saasco.com";

-- The secure views read dim_employee, which their readers cannot. They work as
-- authorized views: in dbt-bigquery, set on models/secure/ in dbt_project.yml
--   +grant_access_to:
--     - project: saasco-analytics
--       dataset: people
-- so BigQuery lets the view, and only the view, read the restricted table.
