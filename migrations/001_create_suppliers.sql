CREATE TABLE IF NOT EXISTS suppliers (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    contact_person VARCHAR(150) NULL,
    email VARCHAR(255) NULL,
    phone VARCHAR(32) NULL,
    address TEXT NULL,
    notes TEXT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_suppliers_name (name)
);
