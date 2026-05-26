-- Seeds default mappings for demo users.
-- Usage:
-- psql "$DATABASE_URL" -f web-app/scripts/bootstrap_default_mappings.sql

UPDATE app_users
SET cloud_user_id = user_id,
    tenant = COALESCE(NULLIF(tenant, ''), 'default'),
    status = COALESCE(NULLIF(status, ''), 'active')
WHERE email IN ('mary@dci.com', 'emily@dci.com');

SELECT user_id, email, cloud_user_id, tenant, status
FROM app_users
WHERE email IN ('mary@dci.com', 'emily@dci.com')
ORDER BY email;
