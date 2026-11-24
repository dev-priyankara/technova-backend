-- Supplier product submissions (for admin review/approval) and in-app notifications.
-- Safe to run on DBs created from older dumps; uses IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS supplier_product_submissions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    supplier_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(200) NOT NULL,
    brand VARCHAR(100) NOT NULL DEFAULT '',
    category_name VARCHAR(150) NOT NULL DEFAULT '',
    sku VARCHAR(100) NOT NULL DEFAULT '',
    description TEXT NULL,
    image_url VARCHAR(500) NULL,
    wholesale_price DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    available_stock INT UNSIGNED NOT NULL DEFAULT 0,
    warranty_period VARCHAR(150) NULL,
    submission_status ENUM('Pending','Approved','Rejected') NOT NULL DEFAULT 'Pending',
    rejection_reason TEXT NULL,
    admin_selling_price DECIMAL(12,2) NULL,
    admin_category_id BIGINT UNSIGNED NULL,
    published_product_id BIGINT UNSIGNED NULL,
    submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME NULL,
    reviewed_by BIGINT UNSIGNED NULL,
    PRIMARY KEY (id),
    KEY idx_submissions_supplier (supplier_id),
    KEY idx_submissions_status (submission_status),
    CONSTRAINT fk_submissions_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE,
    CONSTRAINT fk_submissions_admin_category FOREIGN KEY (admin_category_id) REFERENCES categories(id) ON DELETE SET NULL,
    CONSTRAINT fk_submissions_published_product FOREIGN KEY (published_product_id) REFERENCES products(id) ON DELETE SET NULL,
    CONSTRAINT fk_submissions_reviewer FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS notifications (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    supplier_id BIGINT UNSIGNED NULL,
    type VARCHAR(50) NOT NULL DEFAULT 'info',
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    is_read TINYINT(1) NOT NULL DEFAULT 0,
    related_type VARCHAR(50) NULL,
    related_id BIGINT UNSIGNED NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_notifications_user (user_id, is_read),
    KEY idx_notifications_supplier (supplier_id),
    CONSTRAINT fk_notifications_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_notifications_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
