import pytest
from app import add_ten


def test_add_ten_basic():
    """Test basic addition of ten."""
    assert add_ten(5) == 15
    assert add_ten(0) == 10
    assert add_ten(100) == 110


def test_add_ten_negative():
    """Test with negative numbers."""
    assert add_ten(-5) == 5
    assert add_ten(-10) == 0
    assert add_ten(-100) == -90


def test_add_ten_large_numbers():
    """Test with large numbers."""
    assert add_ten(1000000) == 1000010
    assert add_ten(-1000000) == -999990
