from fhops.reference import (
    ADV2N21Treatment,
    adv2n21_cost_base_year,
    get_adv2n21_treatment,
    load_adv2n21_treatments,
)


def test_load_adv2n21_treatments() -> None:
    treatments = load_adv2n21_treatments()
    assert treatments, "Expected at least one ADV2N21 treatment."
    ids = {t.id for t in treatments}
    assert "partial_cut_2" in ids
    assert adv2n21_cost_base_year() == 1997


def test_get_adv2n21_treatment_contents() -> None:
    treatment = get_adv2n21_treatment("partial_cut_1")
    assert isinstance(treatment, ADV2N21Treatment)
    assert treatment.pre_harvest is not None
    assert treatment.pre_harvest.live_trees_per_ha == 411
    assert treatment.cost_per_m3_cad_1997 == 11.68
