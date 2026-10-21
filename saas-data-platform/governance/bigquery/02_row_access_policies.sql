-- ============================================================================
-- Production reference (BigQuery). Not run locally.
-- Row-level security, the warehouse-native twin of the row_filter column in
-- seeds/governance/roles.csv. Locally the filter is compiled into the
-- secure_sales_manager_emea view and tests/assert_row_filters_hold.sql proves it.
--
-- In BigQuery, once a table has any row access policy, a reader sees only the
-- rows some policy grants them. No policy, no rows: private by default.
-- ============================================================================

-- HR partners see every row.
CREATE OR REPLACE ROW ACCESS POLICY hr_all_rows
ON `saasco-analytics.people.dim_employee`
GRANT TO ("group:hr-partners@saasco.com", "serviceAccount:dbt-people@saasco-analytics.iam.gserviceaccount.com")
FILTER USING (TRUE);

-- The EMEA sales manager sees their own team.
CREATE OR REPLACE ROW ACCESS POLICY sales_manager_emea_team
ON `saasco-analytics.people.dim_employee`
GRANT TO ("group:sales-managers-emea@saasco.com")
FILTER USING (department = 'Sales' AND region = 'EMEA');

-- At scale, one policy per manager does not hold up. Keep an entitlements table
-- (manager email -> worker ids, rebuilt nightly from the org chart) and filter on it:
--
-- CREATE OR REPLACE ROW ACCESS POLICY managers_see_their_org
-- ON `saasco-analytics.people.dim_employee`
-- GRANT TO ("group:people-managers@saasco.com")
-- FILTER USING (worker_id IN (
--     SELECT worker_id FROM `saasco-analytics.people.manager_entitlements`
--     WHERE manager_email = SESSION_USER()
-- ));
