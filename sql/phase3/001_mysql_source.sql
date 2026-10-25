CREATE TABLE IF NOT EXISTS source_identity (
    singleton_id TINYINT PRIMARY KEY,
    project_name VARCHAR(64) NOT NULL,
    source_epoch CHAR(36) NOT NULL,
    schema_version VARCHAR(64) NOT NULL,
    ddl_sha256 CHAR(64) NOT NULL,
    install_state VARCHAR(16) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT ck_identity_singleton CHECK (singleton_id = 1),
    CONSTRAINT ck_identity_state CHECK (install_state IN ('PREPARING','READY'))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS customers (
    customer_id VARCHAR(40) PRIMARY KEY,
    gender VARCHAR(32),
    profile_city VARCHAR(128),
    profile_district VARCHAR(128),
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT ck_customer_demo CHECK (is_demo IN (0,1)),
    CONSTRAINT ck_customer_namespace CHECK ((is_demo=1 AND LEFT(customer_id,5)='DEMO_') OR (is_demo=0 AND LEFT(customer_id,5)<>'DEMO_'))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS products (
    product_id VARCHAR(40) PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    product_group VARCHAR(128),
    category_code VARCHAR(40) NOT NULL,
    catalog_unit_price DECIMAL(18,2) NOT NULL,
    product_size_band VARCHAR(64),
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT ck_product_price CHECK (catalog_unit_price > 0),
    CONSTRAINT ck_product_demo CHECK (is_demo IN (0,1)),
    CONSTRAINT ck_product_namespace CHECK ((is_demo=1 AND LEFT(product_id,5)='DEMO_') OR (is_demo=0 AND LEFT(product_id,5)<>'DEMO_'))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(40) PRIMARY KEY,
    customer_id VARCHAR(40) NOT NULL,
    product_id VARCHAR(40) NOT NULL,
    quantity INT NOT NULL,
    transaction_unit_price DECIMAL(18,2) NOT NULL,
    goods_amount DECIMAL(20,2) NOT NULL,
    vat_amount DECIMAL(20,2) NOT NULL,
    shipping_fee DECIMAL(20,2) NOT NULL,
    total_paid DECIMAL(20,2) NOT NULL,
    shipping_method VARCHAR(64) NOT NULL,
    quantity_band VARCHAR(64),
    warehouse_name VARCHAR(255),
    vehicle_type VARCHAR(64),
    delivery_city VARCHAR(128),
    delivery_district VARCHAR(128),
    packed_at DATETIME,
    dispatched_at DATETIME,
    expected_at DATETIME,
    received_at DATETIME,
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_order_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_order_product FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT ck_order_quantity CHECK (quantity > 0),
    CONSTRAINT ck_order_unit_price CHECK (transaction_unit_price > 0),
    CONSTRAINT ck_order_money_positive CHECK (goods_amount >= 0 AND vat_amount >= 0 AND shipping_fee >= 0 AND total_paid >= 0),
    CONSTRAINT ck_order_goods CHECK (goods_amount = quantity * transaction_unit_price),
    CONSTRAINT ck_order_vat CHECK (vat_amount = ROUND(goods_amount * 0.1,2)),
    CONSTRAINT ck_order_total CHECK (total_paid = goods_amount + vat_amount + shipping_fee),
    CONSTRAINT ck_order_demo CHECK (is_demo IN (0,1)),
    CONSTRAINT ck_order_namespace CHECK ((is_demo=1 AND LEFT(order_id,5)='DEMO_') OR (is_demo=0 AND LEFT(order_id,5)<>'DEMO_')),
    INDEX idx_order_customer_packed (customer_id, packed_at),
    INDEX idx_order_dispatch (dispatched_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS import_files (
    file_name VARCHAR(128) NOT NULL,
    file_sha256 CHAR(64) NOT NULL,
    row_count INT NOT NULL,
    PRIMARY KEY(file_name,file_sha256)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS import_rows (
    file_name VARCHAR(128) NOT NULL,
    file_sha256 CHAR(64) NOT NULL,
    excel_row_number INT NOT NULL,
    entity_type VARCHAR(32) NOT NULL,
    entity_key VARCHAR(40) NOT NULL,
    sanitized_payload JSON NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    redaction_version VARCHAR(32) NOT NULL,
    PRIMARY KEY(file_name,file_sha256,excel_row_number),
    CONSTRAINT fk_import_file FOREIGN KEY (file_name,file_sha256) REFERENCES import_files(file_name,file_sha256),
    CONSTRAINT ck_import_row_number CHECK (excel_row_number >= 2),
    INDEX idx_import_entity(entity_type,entity_key)
) ENGINE=InnoDB;
