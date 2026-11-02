ALTER TABLE suppliers
    ADD COLUMN vendor_code VARCHAR(50) NULL UNIQUE,
    ADD COLUMN tax_id VARCHAR(100) NULL,
    ADD COLUMN city VARCHAR(100) NULL,
    ADD COLUMN postal_code VARCHAR(20) NULL,
    ADD COLUMN contract_status VARCHAR(50) NOT NULL DEFAULT 'Under Review',
    ADD COLUMN bank_name VARCHAR(150) NULL,
    ADD COLUMN bank_branch VARCHAR(150) NULL,
    ADD COLUMN bank_account_no VARCHAR(100) NULL,
    ADD COLUMN authorized_brands JSON NULL,
    ADD COLUMN avatar_url TEXT NULL;

CREATE TABLE shop_branches (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    city VARCHAR(100) NOT NULL,
    address TEXT NOT NULL,
    manager_name VARCHAR(150) NOT NULL,
    phone VARCHAR(32) NOT NULL,
    active_low_stock_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uq_shop_branches_name (name)
);

CREATE TABLE supplier_products (
    id INT NOT NULL AUTO_INCREMENT,
    supplier_id INT NOT NULL,
    name VARCHAR(200) NOT NULL,
    brand VARCHAR(100) NOT NULL,
    category VARCHAR(150) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    wholesale_price DECIMAL(12, 2) NOT NULL,
    retail_msrp DECIMAL(12, 2) NOT NULL,
    available_stock INT NOT NULL DEFAULT 0,
    min_order_qty INT NOT NULL DEFAULT 1,
    warranty_period VARCHAR(100) NOT NULL DEFAULT '',
    status VARCHAR(30) NOT NULL DEFAULT 'In Stock',
    PRIMARY KEY (id),
    UNIQUE KEY uq_supplier_product_sku (supplier_id, sku),
    KEY ix_supplier_products_supplier_id (supplier_id),
    CONSTRAINT fk_supplier_products_supplier
        FOREIGN KEY (supplier_id) REFERENCES suppliers (id) ON DELETE CASCADE
);

CREATE TABLE restock_requests (
    id INT NOT NULL AUTO_INCREMENT,
    supplier_id INT NOT NULL,
    branch_id INT NOT NULL,
    request_no VARCHAR(80) NOT NULL,
    shop_manager VARCHAR(150) NOT NULL,
    shop_phone VARCHAR(32) NOT NULL,
    request_date DATE NOT NULL,
    urgency VARCHAR(40) NOT NULL,
    total_est_value DECIMAL(12, 2) NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'Pending Supplier Approval',
    shop_notes TEXT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_restock_requests_request_no (request_no),
    KEY ix_restock_requests_supplier_id (supplier_id),
    CONSTRAINT fk_restock_requests_supplier
        FOREIGN KEY (supplier_id) REFERENCES suppliers (id) ON DELETE CASCADE,
    CONSTRAINT fk_restock_requests_branch
        FOREIGN KEY (branch_id) REFERENCES shop_branches (id)
);

CREATE TABLE restock_request_items (
    id INT NOT NULL AUTO_INCREMENT,
    request_id INT NOT NULL,
    product_id INT NULL,
    product_name VARCHAR(200) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    current_shop_stock INT NOT NULL,
    min_threshold INT NOT NULL,
    requested_qty INT NOT NULL,
    wholesale_price DECIMAL(12, 2) NOT NULL,
    line_total DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_restock_items_request
        FOREIGN KEY (request_id) REFERENCES restock_requests (id) ON DELETE CASCADE,
    CONSTRAINT fk_restock_items_product
        FOREIGN KEY (product_id) REFERENCES supplier_products (id) ON DELETE SET NULL
);

CREATE TABLE delivery_dispatches (
    id INT NOT NULL AUTO_INCREMENT,
    supplier_id INT NOT NULL,
    branch_id INT NOT NULL,
    request_id INT NULL,
    dispatch_no VARCHAR(80) NOT NULL,
    request_no VARCHAR(80) NULL,
    carrier VARCHAR(150) NOT NULL,
    tracking_number VARCHAR(100) NOT NULL,
    dispatch_date VARCHAR(30) NOT NULL,
    estimated_arrival VARCHAR(100) NOT NULL,
    total_units INT NOT NULL,
    total_value DECIMAL(12, 2) NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'Preparing Dispatch',
    driver_name VARCHAR(150) NULL,
    driver_phone VARCHAR(32) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_delivery_dispatches_dispatch_no (dispatch_no),
    KEY ix_delivery_dispatches_supplier_id (supplier_id),
    CONSTRAINT fk_delivery_dispatches_supplier
        FOREIGN KEY (supplier_id) REFERENCES suppliers (id) ON DELETE CASCADE,
    CONSTRAINT fk_delivery_dispatches_branch
        FOREIGN KEY (branch_id) REFERENCES shop_branches (id),
    CONSTRAINT fk_delivery_dispatches_request
        FOREIGN KEY (request_id) REFERENCES restock_requests (id) ON DELETE SET NULL
);

CREATE TABLE returned_products (
    id INT NOT NULL AUTO_INCREMENT,
    supplier_id INT NOT NULL,
    branch_id INT NOT NULL,
    product_id INT NULL,
    rma_number VARCHAR(80) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    serial_number VARCHAR(150) NOT NULL,
    customer_issue TEXT NOT NULL,
    return_reason VARCHAR(50) NOT NULL,
    return_date DATE NOT NULL,
    warranty_valid BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR(50) NOT NULL DEFAULT 'Pending Inspection',
    resolution_notes TEXT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_returned_products_rma_number (rma_number),
    KEY ix_returned_products_supplier_id (supplier_id),
    CONSTRAINT fk_returned_products_supplier
        FOREIGN KEY (supplier_id) REFERENCES suppliers (id) ON DELETE CASCADE,
    CONSTRAINT fk_returned_products_branch
        FOREIGN KEY (branch_id) REFERENCES shop_branches (id),
    CONSTRAINT fk_returned_products_product
        FOREIGN KEY (product_id) REFERENCES supplier_products (id) ON DELETE SET NULL
);
