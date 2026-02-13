# Python Bug Fix Patterns

Description: Common bug patterns and how to fix them in Python code.

## Examples

- Division by zero: Add checks for zero before dividing
- IndexError: Check list bounds before access
- TypeError: Ensure correct types before operations
- KeyError: Use .get() for dictionary access

## Patterns

1. `if divisor == 0: raise ValueError(...)`
2. `result = list.get(key, default)`
3. `if isinstance(x, int): ...`
4. `for i in range(len(items)): ...` → `for item in items: ...`
