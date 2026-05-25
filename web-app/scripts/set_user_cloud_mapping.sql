-- Usage example:
-- psql "$DATABASE_URL" -v app_email='mary@dci.com' -v cloud_user_id='000-002' -v tenant='default' -v status='active' -f web-app/scripts/set_user_cloud_mapping.sql

UPDATE app_users
SET
  cloud_user_id = :'cloud_user_id',
  tenant = COALESCE(NULLIF(:'tenant', ''), tenant),
  status = COALESCE(NULLIF(:'status', ''), status)
WHERE email = :'app_email';

SELECT user_id, email, cloud_user_id, tenant, status
FROM app_users
WHERE email = :'app_email';
