from fhops.reference import get_appendix5_profile, load_appendix5_stands


def test_load_appendix5_stands_returns_records():
    data = load_appendix5_stands()
    assert len(data) > 0
    assert any(entry.author == "Ackerman et al. (2018)" for entry in data)
    sample = next(entry for entry in data if entry.author == "Ackerman et al. (2018)")
    assert sample.slope_percent is not None
    assert sample.stand_age_years is not None


def test_profile_slope_is_parsed():
    profile = get_appendix5_profile("Ackerman et al. (2018)")
    assert profile.average_slope_percent is not None
    assert abs(profile.average_slope_percent - 23.0) < 0.1
