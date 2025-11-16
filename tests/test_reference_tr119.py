from fhops.reference import get_tr119_treatment, load_tr119_treatments


def test_tr119_treatments_load():
    data = load_tr119_treatments()
    assert any(entry.treatment == "strip_cut" for entry in data)


def test_tr119_get_specific_treatment():
    entry = get_tr119_treatment("65_retention")
    assert entry.volume_multiplier < 1.0
    assert entry.yarding_total_cost_per_m3 > 0
