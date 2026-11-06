"""Offline wait prototype. Explicit reference-test mode only; never auto-installed."""
import time
from typing import Any

def wait_for(self, js_cond: str, timeout: float = 15, interval: float = 1.0) -> Any:
    """Poll until JS body returns a truthy value."""
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        # Only a successful false predicate means "keep waiting".
        # A timeout, denied sync, uncertain dispatch or script exception
        # must propagate; it is not permission to repeat that operation.
        last = self.here(js_cond)
        if last:
            return last
        time.sleep(interval)
    return last
