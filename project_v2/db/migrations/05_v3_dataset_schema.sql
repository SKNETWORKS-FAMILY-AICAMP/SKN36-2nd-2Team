-- DEPRECATED for legacy raw DB replacement.
--
-- This file attempts an in-place structure-only alignment and preserves
-- existing rows. It can fail with ERROR 1138 when legacy raw columns contain
-- NULL values that V3 defines as NOT NULL.
--
-- Preferred command for development raw data replacement:
--   uv run python scripts/load_raw_data.py --reset-v3
--
-- --reset-v3 recreates only dataset-owned raw tables and preserves
-- application tables such as admin/inquiry.

ALTER TABLE `user`
  MODIFY age_group VARCHAR(64) NOT NULL,
  MODIFY region VARCHAR(64) NOT NULL,
  MODIFY signup_channel VARCHAR(64) NOT NULL;

ALTER TABLE storage_usage_monthly
  MODIFY storage_used_gb DOUBLE NOT NULL,
  MODIFY file_count INTEGER NOT NULL,
  MODIFY photo_count INTEGER NOT NULL,
  MODIFY video_count INTEGER NOT NULL,
  MODIFY upload_size_gb DOUBLE NOT NULL,
  MODIFY download_size_gb DOUBLE NOT NULL;

ALTER TABLE user_activity_daily
  MODIFY login_count INTEGER NOT NULL,
  MODIFY upload_count INTEGER NOT NULL,
  MODIFY download_count INTEGER NOT NULL,
  MODIFY share_count INTEGER NOT NULL,
  MODIFY preview_count INTEGER NOT NULL,
  MODIFY active_minutes INTEGER NOT NULL;

ALTER TABLE device
  MODIFY os_type VARCHAR(64) NOT NULL;

ALTER TABLE payment_history
  MODIFY payment_method VARCHAR(64) NOT NULL,
  ADD COLUMN overdue_flag BOOL NOT NULL AFTER retry_count,
  ADD COLUMN status_changed_at DATETIME(6) NOT NULL AFTER overdue_flag;

CREATE INDEX ix_payment_history_status_changed_at ON payment_history (status_changed_at);

ALTER TABLE support_ticket
  MODIFY category VARCHAR(64) NOT NULL;

ALTER TABLE subscription_event
  ADD COLUMN auto_renewal_after BOOL NOT NULL AFTER event_date;

CREATE TABLE IF NOT EXISTS user_snapshot_target (
	snapshot_id BIGINT NOT NULL AUTO_INCREMENT,
	user_id BIGINT NOT NULL,
	snapshot_date DATE NOT NULL,
	label_window_end DATE NOT NULL,
	churn_date DATE,
	churn_60d TINYINT,
	active_subscription_count INTEGER NOT NULL,
	eligible TINYINT NOT NULL,
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (snapshot_id),
	CONSTRAINT uq_snapshot_user_date UNIQUE (user_id, snapshot_date),
	CONSTRAINT ck_snapshot_active CHECK (active_subscription_count > 0),
	CONSTRAINT ck_snapshot_label CHECK ((eligible = 0 AND churn_60d IS NULL) OR (eligible = 1 AND churn_60d IS NOT NULL AND churn_60d IN (0,1))),
	FOREIGN KEY(user_id) REFERENCES user (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;
