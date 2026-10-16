"""A rate-limited HTTP client shared by the capture scripts (at most 2 requests per second)."""

import time

import requests

USER_AGENT = (
    "HireFormLab/0.1 (+https://github.com/JAYATIAHUJA/Hire-Autonomous-Job-Orchestration-Platform-; "
    "read-only capture of public job application forms for offline tests; never submits)"
)
MIN_INTERVAL = 0.5  # seconds between requests -> <= 2 req/s


class Throttle:
    def __init__(self, interval: float = MIN_INTERVAL):
        self.interval = interval
        self._last = 0.0

    def wait(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.interval:
            time.sleep(self.interval - gap)
        self._last = time.monotonic()


class PoliteSession:
    def __init__(self, throttle: Throttle | None = None):
        self.throttle = throttle or Throttle()
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def get(self, url: str, **kw) -> requests.Response | None:
        self.throttle.wait()
        try:
            return self.session.get(url, timeout=20, **kw)
        except requests.RequestException:
            return None
