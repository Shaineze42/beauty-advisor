-- Schéma du pipeline temps réel. Idempotent : peut être rejoué à chaque exécution.
-- Les tables métier (users, products, interactions) existent déjà (init.sql).

CREATE SCHEMA IF NOT EXISTS pipeline;
CREATE SCHEMA IF NOT EXISTS analytics;

-- Un enregistrement par message lu dans le flux (traçabilité complète, lecture seule ensuite).
CREATE TABLE IF NOT EXISTS pipeline.raw_events (
    topic        TEXT        NOT NULL,
    partition_id INTEGER     NOT NULL,
    "offset"     BIGINT      NOT NULL,
    event_id     TEXT,
    status       TEXT        NOT NULL CHECK (status IN ('valid', 'corrected', 'rejected', 'duplicate')),
    corrections  TEXT,
    payload      TEXT        NOT NULL,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (topic, partition_id, "offset")
);

-- Événements rejetés et leur raison : à examiner, corriger puis rejouer.
CREATE TABLE IF NOT EXISTS pipeline.quarantine (
    topic          TEXT        NOT NULL,
    partition_id   INTEGER     NOT NULL,
    "offset"       BIGINT      NOT NULL,
    reason         TEXT        NOT NULL,
    payload        TEXT        NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    replayed       BOOLEAN     NOT NULL DEFAULT FALSE,
    PRIMARY KEY (topic, partition_id, "offset")
);

-- Un enregistrement par exécution du DAG.
CREATE TABLE IF NOT EXISTS pipeline.runs (
    run_id       TEXT PRIMARY KEY,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    status       TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed')),
    consumed     INTEGER NOT NULL DEFAULT 0,
    loaded       INTEGER NOT NULL DEFAULT 0,
    corrected    INTEGER NOT NULL DEFAULT 0,
    rejected     INTEGER NOT NULL DEFAULT 0,
    duplicates   INTEGER NOT NULL DEFAULT 0,
    lag          BIGINT  NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pipeline.quality_checks (
    run_id     TEXT        NOT NULL,
    check_name TEXT        NOT NULL,
    value      DOUBLE PRECISION NOT NULL,
    threshold  DOUBLE PRECISION NOT NULL,
    passed     BOOLEAN     NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, check_name)
);

-- Agrégat ELT reconstruit à chaque run sur une fenêtre glissante.
CREATE TABLE IF NOT EXISTS analytics.interactions_per_minute (
    minute           TIMESTAMP NOT NULL,
    category         TEXT      NOT NULL,
    interaction_type TEXT      NOT NULL,
    interactions     INTEGER   NOT NULL,
    avg_rating       NUMERIC(4, 2),
    PRIMARY KEY (minute, category, interaction_type)
);
