-- Apply once to existing MySQL databases after checking the indexes with SHOW INDEX.
-- These composite indexes support latest-row lookups in the customer list.
-- Each replaces its existing single-column index; its leftmost column keeps FK lookups indexed.
DROP INDEX ix_storage_usage_monthly_user_id ON storage_usage_monthly;
DROP INDEX ix_subscription_user_id ON subscription;
DROP INDEX ix_payment_history_subscription_id ON payment_history;

CREATE INDEX ix_storage_usage_monthly_user_month
  ON storage_usage_monthly (user_id, usage_month, usage_id);

CREATE INDEX ix_subscription_user_updated_id
  ON subscription (user_id, updated_at, subscription_id);

CREATE INDEX ix_payment_history_subscription_date_id
  ON payment_history (subscription_id, payment_date, payment_id);
