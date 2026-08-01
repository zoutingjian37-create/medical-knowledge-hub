"""Daily automation policy independent from the Windows task implementation."""

from datetime import datetime


class AutomationService:
    def __init__(self, *, store, runner):
        self.store = store
        self.runner = runner

    def is_due(self, now: datetime | None = None) -> bool:
        current = now or datetime.now()
        settings = self.store.get_automation()
        if not settings.enabled:
            return False
        today = current.date().isoformat()
        if settings.last_scheduled_date == today:
            return False
        hour, minute = (int(value) for value in settings.run_time.split(":"))
        scheduled = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return current >= scheduled if settings.catch_up else (
            current.hour == hour and current.minute == minute
        )

    def mark_scheduled(self, now: datetime | None = None):
        current = now or datetime.now()
        return self.store.update_automation(
            last_scheduled_date=current.date().isoformat()
        )

    def can_run_manually(self, subscription_id: str) -> bool:
        self.store.get(subscription_id)
        return True

    async def run_if_due(self, now: datetime | None = None):
        current = now or datetime.now()
        if not self.is_due(current):
            return ()
        results = await self.runner.run_enabled()
        self.mark_scheduled(current)
        return results
