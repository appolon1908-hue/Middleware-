BEGIN;

DROP TABLE IF EXISTS middleware_email_quota_buckets;
DROP TABLE IF EXISTS middleware_email_production_audit;
DROP TABLE IF EXISTS middleware_email_production_mutations;
DROP TABLE IF EXISTS middleware_email_production_policy;

COMMIT;
