-- Contrôles de qualité mesurés dans la base (utilisés par le portail qualité du DAG).
-- Fraîcheur : secondes écoulées depuis la dernière interaction enregistrée par le flux.
SELECT COALESCE(EXTRACT(EPOCH FROM (now() - MAX(created_at))), NULL)::float AS freshness_seconds
FROM public.interactions
WHERE interaction_id LIKE 'evt-%';

-- Intégrité : lignes qui violeraient les règles métier (doit retourner 0).
SELECT COUNT(*)::int AS integrity_violations
FROM public.interactions
WHERE interaction_type NOT IN ('favorite', 'purchase', 'review')
   OR (rating IS NOT NULL AND rating NOT BETWEEN 1 AND 5);
