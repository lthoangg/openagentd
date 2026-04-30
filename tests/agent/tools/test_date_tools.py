from app.agent.tools.builtin.date import get_date


def test_get_current_date():
    result = get_date()
    # Basic format check: YYYY-MM-DD
    assert len(result) > 10
    assert result[4] == "-"
    assert result[7] == "-"
