import pytest
from target_app.app import running_average, format_greeting


def test_running_average_ok():
    assert running_average(10, 2) == 5.0


def test_running_average_bug():
    # This should fail until the bug is fixed.
    with pytest.raises(ValueError):
        running_average(5, 0)


def test_running_average_correct_division():
    assert running_average(9, 3) == 3.0


def test_format_greeting():
    assert format_greeting("Peb") == "Hello, Peb!"
