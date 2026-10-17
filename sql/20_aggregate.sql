-- Transformation ELT : agrégat par minute, catégorie et type d'interaction.
-- Fenêtre glissante de 30 minutes, supprimée puis reconstruite dans la même transaction
-- (idempotent : relancer le run produit le même résultat).

DELETE FROM analytics.interactions_per_minute
WHERE minute >= date_trunc('minute', now() - interval '30 minutes');

INSERT INTO analytics.interactions_per_minute (minute, category, interaction_type, interactions, avg_rating)
SELECT
    date_trunc('minute', i.created_at)::timestamp AS minute,
    p.category,
    i.interaction_type,
    COUNT(*)                                       AS interactions,
    ROUND(AVG(i.rating)::numeric, 2)               AS avg_rating
FROM public.interactions i
JOIN public.products p ON p.product_id = i.product_id
WHERE i.created_at >= date_trunc('minute', now() - interval '30 minutes')
GROUP BY 1, 2, 3
ON CONFLICT (minute, category, interaction_type) DO UPDATE
    SET interactions = EXCLUDED.interactions,
        avg_rating   = EXCLUDED.avg_rating;
