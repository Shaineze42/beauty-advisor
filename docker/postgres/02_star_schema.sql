-- Couche analytique en étoile (star schema) construite en VUES sur les tables
-- transactionnelles : aucune donnée dupliquée, toujours à jour.
-- Fait : interactions. Dimensions : utilisateur, produit, date.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.dim_user AS
SELECT
    user_id,
    skin_type,
    complexion,
    undertone,
    preferred_finish,
    preferred_style,
    max_budget
FROM public.users;

CREATE OR REPLACE VIEW analytics.dim_product AS
SELECT
    product_id,
    brand,
    name,
    category,
    price,
    shade,
    finish,
    suitable_skin_type,
    available
FROM public.products;

CREATE OR REPLACE VIEW analytics.dim_date AS
SELECT DISTINCT
    created_at::date                          AS date_key,
    EXTRACT(YEAR FROM created_at)::int        AS year,
    EXTRACT(MONTH FROM created_at)::int       AS month,
    EXTRACT(DAY FROM created_at)::int         AS day,
    EXTRACT(ISODOW FROM created_at)::int      AS iso_weekday
FROM public.interactions;

CREATE OR REPLACE VIEW analytics.fact_interaction AS
SELECT
    interaction_id,
    user_id,
    product_id,
    created_at::date AS date_key,
    interaction_type,
    rating
FROM public.interactions;

-- Exemple d'analyse : interactions par catégorie de produit et type de peau
CREATE OR REPLACE VIEW analytics.v_interactions_by_category_skin AS
SELECT
    p.category,
    u.skin_type,
    COUNT(*)                         AS interactions,
    ROUND(AVG(f.rating)::numeric, 2) AS average_rating
FROM analytics.fact_interaction f
JOIN analytics.dim_product p USING (product_id)
JOIN analytics.dim_user u USING (user_id)
GROUP BY p.category, u.skin_type;
