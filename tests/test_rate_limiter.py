import unittest

from collector.rate_limiter import InProcessRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


class RateLimiterTest(unittest.TestCase):
    def test_wait_sleeps_until_min_interval_passes(self) -> None:
        clock = FakeClock()
        sleeps = []

        def sleeper(seconds: float) -> None:
            sleeps.append(seconds)
            clock.value += seconds

        limiter = InProcessRateLimiter(
            min_interval_seconds=2.5,
            clock=clock,
            sleeper=sleeper,
        )

        limiter.wait()
        clock.value += 1.0
        limiter.wait()

        self.assertEqual(sleeps, [1.5])


if __name__ == "__main__":
    unittest.main()

