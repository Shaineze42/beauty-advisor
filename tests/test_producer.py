import json
import random
from datetime import datetime, timezone

import producer

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


def test_flux_propre_si_ratio_nul():
    rng = random.Random(1)
    prev = []
    for _ in range(100):
        msg, kind = producer.make_message(rng, ["u1"], ["p1"], NOW, 0.0, prev)
        assert kind == "propre"
        assert set(json.loads(msg)) >= {"event_id", "user_id", "product_id", "interaction_type", "ts"}


def test_flux_degrade_si_ratio_un():
    rng = random.Random(2)
    kinds = {producer.make_message(rng, ["u1"], ["p1"], NOW, 1.0, [])[1] for _ in range(300)}
    assert kinds <= set(producer.DIRTY_KINDS)
    assert len(kinds) >= 8


def test_reproductible_avec_graine():
    a = [producer.make_message(random.Random(5), ["u1", "u2"], ["p1"], NOW, 0.2, [])[0] for _ in range(1)]
    b = [producer.make_message(random.Random(5), ["u1", "u2"], ["p1"], NOW, 0.2, [])[0] for _ in range(1)]
    assert a == b
