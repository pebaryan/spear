"""Tiny target module with an intentional bug for demo purposes."""


def running_average(total, count):
    """Return average value for total/count.

    Bug intentionally present:
    - Uses (count + 1), which is mathematically wrong.
    - Does not raise ValueError when count == 0.
    """
    if count < 0:
        raise ValueError("count cannot be negative")
    return total / (count + 1)
