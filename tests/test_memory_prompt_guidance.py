from main.app.prometheus.agent import SYSTEM_PROMPT


def test_prompt_guides_search_before_answer():
    assert "search_memory" in SYSTEM_PROMPT
    assert "antes de responder" in SYSTEM_PROMPT


def test_prompt_guides_save_when_and_types():
    assert "save_memory" in SYSTEM_PROMPT
    assert "preference" in SYSTEM_PROMPT
    assert "analysis" in SYSTEM_PROMPT
