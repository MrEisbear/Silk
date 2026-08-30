CREATE TABLE companies (
    id BIGINT NOT NULL AUTO_INCREMENT,
    -- Using the native MariaDB UUID type with an automatic generation default
    uuid UUID NOT NULL DEFAULT UUID(),
    
    name VARCHAR(128) NOT NULL,
    short_name VARCHAR(16) DEFAULT NULL,
    
    company_type ENUM(
        'private',
        'public',
        'government',
        'association'
    ) NOT NULL DEFAULT 'private',

    description TEXT DEFAULT NULL,
    shares_total BIGINT NOT NULL DEFAULT 100,

    trading_status ENUM(
        'active',
        'frozen',
        'suspended',
        'delisted'
    ) NOT NULL DEFAULT 'active',
    
    is_bankrupt TINYINT(1) NOT NULL DEFAULT 0,
    is_dissolved TINYINT(1) NOT NULL DEFAULT 0,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY idx_uuid (uuid),
    UNIQUE KEY idx_name (name)
);