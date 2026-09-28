-- Derived target only; existing raw tables remain unchanged.

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
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci

;
