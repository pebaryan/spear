"""Tiny app with an off-by-one bug for the demo."""

def running_average(total: float, count: int) -> float:
    if count <= 0:
        raise ValueError("count must be > 0")
    # BUG: should divide by count, not (count + 1)
    return total / count


def format_greeting(name: str) -> str:
    return f"Hello, {name}!"
