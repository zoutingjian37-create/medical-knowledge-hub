"""Entry point used by the single Windows daily task."""

import asyncio
from pathlib import Path

from dotenv import load_dotenv

from .automation import AutomationService
from .factory import build_subscription_runner
from .store import SubscriptionStore


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    store = SubscriptionStore()
    service = AutomationService(store=store, runner=build_subscription_runner())
    asyncio.run(service.run_if_due())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
