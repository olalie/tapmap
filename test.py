def factorial(n: int):
    """Return n! (factorial of n)."""
    if n < 0:
        raise ValueError("Negative input not allowed")
    elif n == 0 or n == 1:
        return 1
    else:
        result = 1
        for i in range(2, n + 1):
            result *= i
        return result
