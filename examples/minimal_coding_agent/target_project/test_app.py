"""Tests for minimal coding agent target project."""

import pytest

from app import running_average


def test_running_average_basic():
    assert running_average(10, 2) == 5


def test_running_average_zero_count():
    with pytest.raises(ValueError):
        running_average(10, 0)


def test_running_average_negative_count():
    with pytest.raises(ValueError):
        running_average(10, -1)
