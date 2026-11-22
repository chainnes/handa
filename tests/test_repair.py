from handa.agents.repair import accept_schema, repair_handoff
from handa.schemas import Handoff


def test_a_text_field_is_repaired_once():
    model, review = accept_schema({"text": "The menu is ready for inventory."}, Handoff, repair_handoff)
    assert review is False
    assert model.message.startswith("The menu")


def test_off_schema_goes_to_review_after_one_repair():
    model, review = accept_schema({"nope": 1}, Handoff, repair_handoff)
    assert model is None
    assert review is True
