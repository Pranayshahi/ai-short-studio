"""Car specs: engine/power from the car's OWN Wikipedia article, compacted for end cards; nothing invented."""
from unittest import mock


def test_compact_engine_and_power():
    from agents import specs_db as s
    assert s.compact_engine("4.0 L L411 twin-turbocharged V8", hybrid=True) == "4.0L TWIN-TURBO V8 HYBRID"
    assert s.compact_engine("2992 cc F163 BC 120° twin-turbo V6") == "3.0L TWIN-TURBO V6"
    assert s.compact_engine("electric") == "", "too little data -> nothing, not a guess"
    assert s.power_from_text("producing 830 PS (610 kW; 819 hp)") == "830 PS"
    assert s.power_from_text("rated at 552 kW") == "740 HP"
    assert s.power_from_text("Founded in 1947, 30 cars") == ""


def test_never_uses_a_sibling_models_article():
    from agents import specs_db as s, equipment_catalog as ec
    with mock.patch.object(ec, "_get", side_effect=lambda params: {"query": {"search": [{"title": "McLaren 720S"}]}}
                           if params.get("list") == "search" else (_ for _ in ()).throw(AssertionError("read the 720S article"))):
        assert s._lookup_wikipedia("McLaren 750S") is None


def test_car_specs_use_lookup_and_overrides(tmp_path):
    from agents import specs_db as s
    from agents.car_edit_agent import CarEditAgent
    with mock.patch.object(s, "_lookup_wikipedia", return_value={"spec": "4.0L Twin-Turbo V8 · 907 PS", "source": "Wikipedia: X"}):
        spec = CarEditAgent.resolve_car_specs("Testcar Zeta 9")
    assert spec["spec"] == "4.0L TWIN-TURBO V8 · 907 PS" and spec["brand"] == "TESTCAR"
    over = tmp_path / "o.json"
    over.write_text('{"testcar omega": {"spec": "PINNED · 1 HP"}}')
    with mock.patch.object(s, "OVERRIDES", over), mock.patch.object(s, "_lookup_wikipedia", side_effect=AssertionError("pinned value must win")):
        assert s.lookup_car("Testcar Omega")["spec"] == "PINNED · 1 HP"
