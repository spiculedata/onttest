import polars as pl
import pytest

from brackenfield import mdm


@pytest.fixture(scope="module")
def reg():
    return mdm.load_registry()


@pytest.mark.parametrize(
    ("domain", "raw", "canonical", "basis"),
    [
        ("category", "Tipper truck", "Tipper", "variant"),
        ("category", "T&D", "Tipper", "readme"),
        ("category", "Truck and Dog", "Tipper", "readme"),
        ("category", "Smooth drum", "Roller", "readme"),
        ("category", "Smooth-drum roller", "Roller", "variant"),
        ("category", "UTE", "Light vehicle", "readme"),
        ("category", "Bakkie", "Light vehicle", "regional"),
        ("category", "Pickup", "Light vehicle", "regional"),
        ("category", "20 tonne digger", "Excavator 20t", "readme"),
        ("category", "BOBCAT", "Skid steer", "readme"),
        ("supplier", "TIDAL EARTHMOVING P/L", "Tidal Earthmoving Pty Ltd", "canonical"),
        ("supplier", "Hire Well", "Hirewell Pty Ltd", "inferred"),
        ("status", "Yard", "available", "readme"),
        ("status", "On job", "on_project", "inferred"),
        ("rate_basis", "Weekly", "wk", "variant"),
        ("gst", "Incl. GST", "inc", "variant"),
    ],
)
def test_known_spellings_resolve_exactly(reg, domain, raw, canonical, basis):
    r = reg.domain(domain).resolve(raw)

    assert (r.canonical, r.basis) == (canonical, basis)


@pytest.mark.parametrize(
    ("domain", "raw", "canonical"),
    [("category", "Excavtor 20t", "Excavator 20t"), ("category", "Tiper", "Tipper"),
     ("status", "Reapirs", "workshop"), ("supplier", "Southgte Plant Hire", "Southgate Plant Hire")],
)
def test_typos_are_matched_but_marked_fuzzy(reg, domain, raw, canonical):
    r = reg.domain(domain).resolve(raw)

    assert (r.canonical, r.basis) == (canonical, "fuzzy")


def test_ambiguous_or_unknown_words_are_not_guessed(reg):
    between_sizes = reg.domain("category").resolve("Excavator 50t")
    nonsense = reg.domain("category").resolve("Hovercraft")

    assert between_sizes.canonical is None and "Excavator 5t" in between_sizes.suggestions
    assert nonsense.canonical is None


def test_alias_pointing_at_unknown_canonical_is_rejected(tmp_path):
    (tmp_path / "canonical.csv").write_text("domain,canonical,code,description\ncategory,Tipper,TP,x\n")
    (tmp_path / "aliases.csv").write_text("domain,alias,canonical,basis,note\ncategory,Ute,Light vehicle,regional,\n")

    with pytest.raises(mdm.MdmError, match="not in canonical.csv"):
        mdm.load_registry(tmp_path)


def test_alias_mapped_two_ways_is_rejected(tmp_path):
    (tmp_path / "canonical.csv").write_text("domain,canonical,code,description\ncategory,Tipper,,\ncategory,Roller,,\n")
    (tmp_path / "aliases.csv").write_text(
        "domain,alias,canonical,basis,note\ncategory,Drum,Roller,variant,\ncategory,DRUM,Tipper,variant,\n")

    with pytest.raises(mdm.MdmError, match="already maps"):
        mdm.load_registry(tmp_path)


def test_term_usage_lists_every_value_with_its_resolution():
    frame = pl.DataFrame({"source_tab": ["T", "T", "T"], "source_row": [2, 3, 4], "cat": ["Ute", "Ute", "Tiper"]})

    usage = mdm.term_usage([("category", frame, "cat")])

    rows = {r["raw_value"]: r for r in usage.iter_rows(named=True)}
    assert rows["Ute"]["line_count"] == 2 and rows["Ute"]["source_refs"] == "T!2, T!3"
    assert rows["Tiper"]["needs_confirmation"] and rows["Tiper"]["basis"] == "fuzzy"


def test_a_type_with_no_size_is_not_guessed(reg):
    assert reg.domain("category").resolve("Excavator").canonical is None
    assert reg.domain("category").resolve("Digger").canonical is None
    assert reg.domain("category").resolve("20T Digger").canonical == "Excavator 20t"


def test_short_codes_are_never_typo_matched(reg):
    assert reg.domain("gst").resolve("GST").canonical is None
    assert reg.domain("rate_basis").resolve("wkly").canonical is None
    assert reg.domain("gst").resolve("Incl. GST").canonical == "inc"
