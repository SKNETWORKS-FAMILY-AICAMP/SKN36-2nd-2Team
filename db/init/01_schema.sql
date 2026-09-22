-- Source columns only. No DROP/REPLACE. Select the database before execution.
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS plan (
	plan_id BIGINT NOT NULL, 
	plan_name VARCHAR(64) NOT NULL, 
	storage_limit_gb INTEGER NOT NULL, 
	monthly_price NUMERIC(18, 2) NOT NULL, 
	billing_cycle VARCHAR(64) NOT NULL, 
	is_paid BOOL NOT NULL, 
	is_active BOOL NOT NULL, 
	PRIMARY KEY (plan_id), 
	UNIQUE (plan_name)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS user (
	user_id BIGINT NOT NULL, 
	signup_date DATE NOT NULL, 
	age_group VARCHAR(64), 
	region VARCHAR(64), 
	signup_channel VARCHAR(64), 
	status VARCHAR(64) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	updated_at DATETIME(6) NOT NULL, 
	PRIMARY KEY (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_user_created_at ON user (created_at);

CREATE INDEX ix_user_signup_date ON user (signup_date);

CREATE INDEX ix_user_updated_at ON user (updated_at);

CREATE TABLE IF NOT EXISTS device (
	device_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	device_type VARCHAR(64) NOT NULL, 
	os_type VARCHAR(64), 
	sync_enabled BOOL NOT NULL, 
	last_sync_at DATETIME(6), 
	registered_at DATETIME(6) NOT NULL, 
	PRIMARY KEY (device_id), 
	FOREIGN KEY(user_id) REFERENCES user (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_device_last_sync_at ON device (last_sync_at);

CREATE INDEX ix_device_registered_at ON device (registered_at);

CREATE INDEX ix_device_user_id ON device (user_id);

CREATE TABLE IF NOT EXISTS storage_usage_monthly (
	usage_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	usage_month DATE NOT NULL, 
	storage_used_gb DOUBLE, 
	file_count INTEGER, 
	photo_count INTEGER, 
	video_count INTEGER, 
	upload_size_gb DOUBLE, 
	download_size_gb DOUBLE, 
	created_at DATETIME(6) NOT NULL, 
	PRIMARY KEY (usage_id), 
	FOREIGN KEY(user_id) REFERENCES user (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_storage_usage_monthly_created_at ON storage_usage_monthly (created_at);

CREATE INDEX ix_storage_usage_monthly_usage_month ON storage_usage_monthly (usage_month);

CREATE INDEX ix_storage_usage_monthly_user_id ON storage_usage_monthly (user_id);

CREATE TABLE IF NOT EXISTS subscription (
	subscription_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	plan_id BIGINT NOT NULL, 
	start_date DATE NOT NULL, 
	next_billing_date DATE, 
	end_date DATE, 
	auto_renewal BOOL NOT NULL, 
	subscription_status VARCHAR(64) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	updated_at DATETIME(6) NOT NULL, 
	PRIMARY KEY (subscription_id), 
	FOREIGN KEY(user_id) REFERENCES user (user_id), 
	FOREIGN KEY(plan_id) REFERENCES plan (plan_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_subscription_created_at ON subscription (created_at);

CREATE INDEX ix_subscription_end_date ON subscription (end_date);

CREATE INDEX ix_subscription_next_billing_date ON subscription (next_billing_date);

CREATE INDEX ix_subscription_plan_id ON subscription (plan_id);

CREATE INDEX ix_subscription_start_date ON subscription (start_date);

CREATE INDEX ix_subscription_updated_at ON subscription (updated_at);

CREATE INDEX ix_subscription_user_id ON subscription (user_id);

CREATE TABLE IF NOT EXISTS support_ticket (
	ticket_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	category VARCHAR(64), 
	priority VARCHAR(64) NOT NULL, 
	status VARCHAR(64) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	resolved_at DATETIME(6), 
	reopened BOOL NOT NULL, 
	PRIMARY KEY (ticket_id), 
	FOREIGN KEY(user_id) REFERENCES user (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_support_ticket_created_at ON support_ticket (created_at);

CREATE INDEX ix_support_ticket_resolved_at ON support_ticket (resolved_at);

CREATE INDEX ix_support_ticket_user_id ON support_ticket (user_id);

CREATE TABLE IF NOT EXISTS user_activity_daily (
	activity_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	activity_date DATE NOT NULL, 
	login_count INTEGER, 
	upload_count INTEGER, 
	download_count INTEGER, 
	share_count INTEGER, 
	preview_count INTEGER, 
	active_minutes INTEGER, 
	PRIMARY KEY (activity_id), 
	FOREIGN KEY(user_id) REFERENCES user (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_user_activity_daily_activity_date ON user_activity_daily (activity_date);

CREATE INDEX ix_user_activity_daily_user_id ON user_activity_daily (user_id);

CREATE TABLE IF NOT EXISTS payment_history (
	payment_id BIGINT NOT NULL, 
	subscription_id BIGINT NOT NULL, 
	payment_date DATETIME(6) NOT NULL, 
	amount NUMERIC(18, 2) NOT NULL, 
	payment_status VARCHAR(64) NOT NULL, 
	payment_method VARCHAR(64), 
	retry_count INTEGER NOT NULL, 
	PRIMARY KEY (payment_id), 
	FOREIGN KEY(subscription_id) REFERENCES subscription (subscription_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_payment_history_payment_date ON payment_history (payment_date);

CREATE INDEX ix_payment_history_subscription_id ON payment_history (subscription_id);

CREATE TABLE IF NOT EXISTS subscription_event (
	event_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	subscription_id BIGINT NOT NULL, 
	event_type VARCHAR(64) NOT NULL, 
	old_plan_id BIGINT NOT NULL, 
	new_plan_id BIGINT, 
	event_date DATETIME(6) NOT NULL, 
	PRIMARY KEY (event_id), 
	FOREIGN KEY(user_id) REFERENCES user (user_id), 
	FOREIGN KEY(subscription_id) REFERENCES subscription (subscription_id), 
	FOREIGN KEY(old_plan_id) REFERENCES plan (plan_id), 
	FOREIGN KEY(new_plan_id) REFERENCES plan (plan_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE INDEX ix_subscription_event_event_date ON subscription_event (event_date);

CREATE INDEX ix_subscription_event_new_plan_id ON subscription_event (new_plan_id);

CREATE INDEX ix_subscription_event_old_plan_id ON subscription_event (old_plan_id);

CREATE INDEX ix_subscription_event_subscription_id ON subscription_event (subscription_id);

CREATE INDEX ix_subscription_event_user_id ON subscription_event (user_id);
