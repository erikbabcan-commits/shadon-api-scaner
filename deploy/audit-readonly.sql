-- Run through an authorized private database connection; never print the URL.
BEGIN READ ONLY;
SELECT current_setting('server_version_num') AS postgres_version_num;
SELECT version_num AS alembic_revision FROM alembic_version;
SELECT count(*) AS orphan_app_count FROM apps WHERE organization_id IS NULL;
SELECT conname, convalidated
FROM pg_constraint
WHERE conrelid = 'audit_events'::regclass AND contype = 'f';
COMMIT;
