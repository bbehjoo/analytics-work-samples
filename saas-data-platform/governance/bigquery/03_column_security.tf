# ============================================================================
# Production reference (BigQuery + Terraform). Not run locally.
# Column-level security: the warehouse-native twin of the sensitivity tags in the
# dbt YAML. Each sensitivity class becomes a policy tag. A column carrying a tag
# can be read in full only by the groups granted "fine-grained reader" on that
# tag; everyone else gets the masking rule, or an access error.
#
# The tags are attached to columns from the same YAML: dbt-bigquery reads
# `policy_tags` on a column and applies them at build time, with
# `+persist_docs: {columns: true}` set on the people models.
# ============================================================================

resource "google_data_catalog_taxonomy" "sensitivity" {
  region                 = "us"
  display_name           = "sensitivity"
  description            = "Data classes, one per row of seeds/governance/access_policy.csv's sensitivity column"
  activated_policy_types = ["FINE_GRAINED_ACCESS_CONTROL"]
}

resource "google_data_catalog_policy_tag" "pii" {
  taxonomy     = google_data_catalog_taxonomy.sensitivity.id
  display_name = "pii"
  description  = "Identifies a person: name, email, birth date, home postal code"
}

resource "google_data_catalog_policy_tag" "restricted" {
  taxonomy     = google_data_catalog_taxonomy.sensitivity.id
  display_name = "restricted"
  description  = "Pay, health (leave) and demographics"
}

locals {
  full_readers = ["group:hr-partners@saasco.com",
                  "serviceAccount:dbt-people@saasco-analytics.iam.gserviceaccount.com"]
}

# Full read of PII and restricted columns: HR partners and the People Analytics pipeline.
resource "google_data_catalog_policy_tag_iam_member" "pii_readers" {
  for_each   = toset(local.full_readers)
  policy_tag = google_data_catalog_policy_tag.pii.name
  role       = "roles/datacatalog.categoryFineGrainedReader"
  member     = each.value
}

resource "google_data_catalog_policy_tag_iam_member" "restricted_readers" {
  for_each   = toset(local.full_readers)
  policy_tag = google_data_catalog_policy_tag.restricted.name
  role       = "roles/datacatalog.categoryFineGrainedReader"
  member     = each.value
}

# Everyone else who can see a PII column sees it masked, not raw.
resource "google_bigquery_datapolicy_data_policy" "pii_email_mask" {
  location         = "us"
  data_policy_id   = "pii_email_mask"
  policy_tag       = google_data_catalog_policy_tag.pii.name
  data_policy_type = "DATA_MASKING_POLICY"
  data_masking_policy {
    predefined_expression = "EMAIL_MASK"   # j.doe@saasco.com -> XXXXX@saasco.com
  }
}

resource "google_bigquery_datapolicy_data_policy_iam_member" "pii_masked_readers" {
  location       = "us"
  data_policy_id = google_bigquery_datapolicy_data_policy.pii_email_mask.data_policy_id
  role           = "roles/bigquerydatapolicy.maskedReader"
  member         = "group:analysts@saasco.com"
}
