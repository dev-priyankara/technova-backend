CREATE TABLE IF NOT EXISTS admin_profile_extensions (
    user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    street VARCHAR(255) NULL,
    city VARCHAR(100) NULL,
    postal_code VARCHAR(20) NULL,
    avatar_url LONGTEXT NULL,
    CONSTRAINT fk_admin_profile_extensions_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS supplier_profile_extensions (
    supplier_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    city VARCHAR(100) NULL,
    postal_code VARCHAR(20) NULL,
    authorized_brands JSON NULL,
    avatar_url LONGTEXT NULL,
    CONSTRAINT fk_supplier_profile_extensions_supplier
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS admin_saved_reports (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    report_type VARCHAR(100) NOT NULL,
    period VARCHAR(100) NOT NULL,
    channel VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Finalized',
    notes TEXT NULL,
    gross_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
