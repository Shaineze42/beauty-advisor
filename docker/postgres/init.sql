CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(50) PRIMARY KEY,
    skin_type VARCHAR(50) NOT NULL,
    complexion VARCHAR(50),
    undertone VARCHAR(50),
    preferred_finish VARCHAR(50),
    preferred_style VARCHAR(50),
    max_budget NUMERIC(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    product_id VARCHAR(50) PRIMARY KEY,
    brand VARCHAR(100) NOT NULL,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(50) NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    shade VARCHAR(100),
    finish VARCHAR(50),
    suitable_skin_type VARCHAR(50),
    available BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interactions (
    interaction_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    product_id VARCHAR(50) NOT NULL,
    interaction_type VARCHAR(20) NOT NULL,
    rating INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_interaction_user
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_interaction_product
        FOREIGN KEY (product_id)
        REFERENCES products(product_id)
        ON DELETE CASCADE,

    CONSTRAINT valid_interaction_type
        CHECK (interaction_type IN ('favorite', 'purchase', 'review')),

    CONSTRAINT valid_rating
        CHECK (rating IS NULL OR rating BETWEEN 1 AND 5)
);

CREATE INDEX IF NOT EXISTS idx_products_category
    ON products(category);

CREATE INDEX IF NOT EXISTS idx_products_skin_type
    ON products(suitable_skin_type);

CREATE INDEX IF NOT EXISTS idx_interactions_user
    ON interactions(user_id);

CREATE INDEX IF NOT EXISTS idx_interactions_product
    ON interactions(product_id);