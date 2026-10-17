import quality


def by_name(checks):
    return {c["name"]: c for c in checks}


def test_run_sain():
    c = by_name(quality.evaluate_checks({"consumed": 1000, "rejected": 60, "lag": 0,
                                         "freshness_seconds": 30, "integrity_violations": 0}))
    assert all(x["passed"] for x in c.values())


def test_taux_de_rejet_trop_eleve():
    c = by_name(quality.evaluate_checks({"consumed": 100, "rejected": 40, "lag": 0,
                                         "freshness_seconds": 10, "integrity_violations": 0}))
    assert not c["taux_de_rejet"]["passed"]


def test_donnees_perimees():
    c = by_name(quality.evaluate_checks({"consumed": 0, "rejected": 0, "lag": 0,
                                         "freshness_seconds": 4000, "integrity_violations": 0}))
    assert not c["fraicheur_secondes"]["passed"]


def test_aucune_donnee_est_un_echec_de_fraicheur():
    c = by_name(quality.evaluate_checks({"consumed": 0, "rejected": 0, "lag": 0,
                                         "freshness_seconds": None, "integrity_violations": 0}))
    assert not c["fraicheur_secondes"]["passed"]


def test_retard_et_integrite():
    c = by_name(quality.evaluate_checks({"consumed": 10, "rejected": 0, "lag": 50000,
                                         "freshness_seconds": 5, "integrity_violations": 2}))
    assert not c["retard_consommateur"]["passed"] and not c["violations_integrite"]["passed"]


def test_aucun_message_pas_de_division_par_zero():
    c = by_name(quality.evaluate_checks({"consumed": 0, "rejected": 0, "lag": 0,
                                         "freshness_seconds": 5, "integrity_violations": 0}))
    assert c["taux_de_rejet"]["passed"] and c["taux_de_rejet"]["value"] == 0.0
