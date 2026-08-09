"""Desktop WeChat discovery with an explicit public-search compatibility mode.

The public API returns URLs only. It never accepts or exposes WeChat backend
credentials, message databases, or account tokens.
"""

from collections.abc import Iterable, Mapping
import asyncio
from dataclasses import dataclass
import multiprocessing
from queue import Empty
import time
from typing import Optional
from urllib.parse import urlparse
from uuid import uuid4

from extensions.platforms.opencli.runner import OpenCLIRunner, OpenCLIRunnerError

from .public_link import canonicalize_public_article_url


class WeChatDiscoveryError(RuntimeError):
    """A WeChat article discovery source could not complete its work."""

    def __init__(
        self,
        message: str,
        *,
        step: str = "unknown",
        retry_from: str = "account_search",
        progress_kept: bool = False,
    ):
        super().__init__(message)
        self.step = step
        self.retry_from = retry_from
        self.progress_kept = bool(progress_kept)


# Compatibility name for callers of the earlier UI-only boundary.
WeChatUIDiscoveryError = WeChatDiscoveryError


@dataclass(frozen=True)
class WeChatDiscoveryStatus:
    complete: bool = True
    attempts: int = 0
    incomplete_accounts: tuple[str, ...] = ()
    resume_dates: Mapping[str, str] = None
    warning: str = ""
    failed_step: str = ""
    retry_from: str = ""
    progress_kept: bool = False

    def __post_init__(self):
        if self.resume_dates is None:
            object.__setattr__(self, "resume_dates", {})


class PyWeixinLinkBackend:
    """Small compatibility seam around pyweixin's proven UI workflow."""

    def __init__(self, worker=None, timeout: float = 120):
        self._worker = worker or _collect_with_pyweixin
        self._timeout = timeout

    def collect_links(self, account: str, limit: int) -> Iterable[str]:
        context = multiprocessing.get_context("spawn")
        result_queue = context.Queue()
        process = context.Process(
            target=_worker_entry,
            args=(self._worker, account, limit, result_queue),
        )
        process.start()
        process.join(self._timeout)
        if process.is_alive():
            process.terminate()
            process.join(5)
            raise WeChatUIDiscoveryError(
                f"WeChat UI discovery timed out for {account}"
            )
        try:
            status, payload = result_queue.get(timeout=1)
        except Empty as exc:
            raise WeChatUIDiscoveryError(
                f"WeChat UI discovery stopped unexpectedly for {account}"
            ) from exc
        finally:
            result_queue.close()
        if status == "error":
            raise WeChatUIDiscoveryError(
                f"WeChat UI discovery failed for {account}: {payload}"
            )
        return payload


class WeChatUIDiscoverer:
    def __init__(self, backend=None, max_attempts: int = 3):
        if backend is None:
            from .desktop_vision import WeChatVisualLinkBackend

            backend = WeChatVisualLinkBackend()
        self._backend = backend
        self._max_attempts = max(1, int(max_attempts))
        self.last_status = WeChatDiscoveryStatus()

    def discover(
        self,
        accounts: Iterable[str],
        per_account: int = 10,
        date_from=None,
        date_to=None,
    ) -> tuple[str, ...]:
        if per_account < 1:
            raise ValueError("per_account must be at least 1")
        discovered: list[str] = []
        seen: set[str] = set()
        total_attempts = 0
        incomplete_accounts: list[str] = []
        resume_dates: dict[str, str] = {}
        for account in accounts:
            account = str(account).strip()
            if not account:
                continue
            account_links: list[str] = []
            account_seen: set[str] = set()
            resume_to = date_to
            last_error: RuntimeError | None = None
            for attempt in range(1, self._max_attempts + 1):
                total_attempts += 1
                remaining = per_account - len(account_links)
                if remaining <= 0:
                    break
                options = {}
                if date_from is not None or resume_to is not None:
                    options.update(date_from=date_from, date_to=resume_to)
                if account_seen:
                    options["exclude_urls"] = tuple(account_links)
                try:
                    candidates = self._backend.collect_links(
                        account,
                        remaining,
                        **options,
                    )
                except RuntimeError as exc:
                    last_error = exc
                    checkpoint_entries = self._checkpoint_entries(
                        account,
                        date_from=date_from,
                        date_to=resume_to,
                    )
                    for _published, candidate in checkpoint_entries:
                        self._append_public_link(
                            candidate,
                            account_links,
                            account_seen,
                        )
                        if len(account_links) >= per_account:
                            break
                    if len(account_links) >= per_account:
                        last_error = None
                        break
                    if checkpoint_entries:
                        resume_to = min(item[0] for item in checkpoint_entries)
                    if attempt < self._max_attempts:
                        continue
                    if not account_links:
                        raise WeChatDiscoveryError(
                            f"Desktop WeChat discovery failed for {account} "
                            f"after {self._max_attempts} attempts: {exc}",
                            step=getattr(exc, "step", "unknown"),
                            retry_from=getattr(exc, "retry_from", "account_search"),
                            progress_kept=bool(
                                getattr(exc, "progress_kept", False)
                            ),
                        ) from exc
                    incomplete_accounts.append(account)
                    if resume_to is not None:
                        resume_dates[account] = resume_to.isoformat()
                    break
                else:
                    for candidate in candidates:
                        self._append_public_link(
                            candidate,
                            account_links,
                            account_seen,
                        )
                    last_error = None
                    break

            for public_url in account_links:
                if public_url not in seen:
                    seen.add(public_url)
                    discovered.append(public_url)

        warning = ""
        if incomplete_accounts:
            warning = (
                f"微信界面连续 {self._max_attempts} 次未恢复；"
                "已保存成功链接，可从检查点继续。"
            )
        self.last_status = WeChatDiscoveryStatus(
            complete=not incomplete_accounts,
            attempts=total_attempts,
            incomplete_accounts=tuple(incomplete_accounts),
            resume_dates=resume_dates,
            warning=warning,
            failed_step=getattr(last_error, "step", "") if last_error else "",
            retry_from=getattr(last_error, "retry_from", "") if last_error else "",
            progress_kept=bool(account_links),
        )
        return tuple(discovered)

    def _checkpoint_entries(self, account, *, date_from=None, date_to=None):
        index = getattr(self._backend, "index", None)
        reader = getattr(index, "entries_for", None)
        if not callable(reader):
            return ()
        return reader(account, date_from=date_from, date_to=date_to)

    @staticmethod
    def _append_public_link(candidate, links, seen) -> None:
        try:
            public_url = canonicalize_public_article_url(candidate)
        except ValueError:
            return
        if public_url not in seen:
            seen.add(public_url)
            links.append(public_url)


class OpenCLIWeChatDiscoverer:
    """Discover public articles without controlling the desktop WeChat app."""

    def __init__(
        self,
        runner: Optional[OpenCLIRunner] = None,
        resolve_timeout: float = 8,
        poll_interval: float = 0.25,
    ):
        self._runner = runner or OpenCLIRunner()
        self._resolve_timeout = max(0, resolve_timeout)
        self._poll_interval = max(0, poll_interval)

    async def discover(
        self, accounts: Iterable[str], per_account: int = 10
    ) -> tuple[str, ...]:
        if per_account < 1:
            raise ValueError("per_account must be at least 1")

        discovered = []
        seen = set()
        session = f"medical-knowledge-hub-wechat-{uuid4().hex}"
        session_opened = False
        try:
            for raw_account in accounts:
                account = str(raw_account).strip()
                if not account:
                    continue
                remaining = per_account
                page = 1
                while remaining > 0:
                    page_limit = min(remaining, 10)
                    rows = await self._runner.run_json(
                        "weixin",
                        "search",
                        account,
                        "--page",
                        str(page),
                        "--limit",
                        str(page_limit),
                        timeout=30,
                    )
                    if not isinstance(rows, list):
                        raise WeChatDiscoveryError(
                            f"Public WeChat search returned invalid data for {account}"
                        )
                    for row in rows:
                        candidate = str(
                            row.get("url", "") if isinstance(row, Mapping) else ""
                        ).strip()
                        if not candidate:
                            raise WeChatDiscoveryError(
                                f"Public WeChat search returned a result without a URL for {account}"
                            )
                        try:
                            public_url = canonicalize_public_article_url(candidate)
                        except ValueError:
                            if urlparse(candidate).hostname != "weixin.sogou.com":
                                raise WeChatDiscoveryError(
                                    f"Public WeChat search returned an unsupported URL for {account}"
                                )
                            await self._runner.run_text(
                                "browser", session, "open", candidate, timeout=20
                            )
                            session_opened = True
                            public_url = await self._wait_for_public_url(session)
                        if public_url not in seen:
                            seen.add(public_url)
                            discovered.append(public_url)
                    remaining -= len(rows)
                    if len(rows) < page_limit:
                        break
                    page += 1
        except OpenCLIRunnerError as exc:
            raise WeChatDiscoveryError(
                f"Public WeChat discovery failed: {exc}"
            ) from exc
        finally:
            if session_opened:
                try:
                    await self._runner.run_text(
                        "browser", session, "close", timeout=8
                    )
                except OpenCLIRunnerError:
                    pass
        return tuple(discovered)

    async def _wait_for_public_url(self, session: str) -> str:
        deadline = time.monotonic() + self._resolve_timeout
        while True:
            current = await self._runner.run_text(
                "browser", session, "get", "url", timeout=8
            )
            try:
                return canonicalize_public_article_url(current)
            except ValueError:
                if time.monotonic() >= deadline:
                    raise WeChatDiscoveryError(
                        "Could not resolve the public WeChat article URL"
                    )
                await asyncio.sleep(self._poll_interval)


def _worker_entry(worker, account, limit, result_queue):
    try:
        result_queue.put(("ok", list(worker(account, limit))))
    except Exception as exc:
        result_queue.put(("error", f"{type(exc).__name__}: {exc}"))


def _collect_with_pyweixin(account: str, limit: int) -> Iterable[str]:
    try:
        from pyweixin import Collections
    except ImportError as exc:
        raise RuntimeError(
            "The optional pywechat127 UI dependency is not installed"
        ) from exc
    collected = Collections.collect_offAcc_articles(
        name=account,
        number=limit,
        close_weixin=False,
    )
    links = Collections.cardLink_to_url(
        number=collected,
        delete=False,
        close_weixin=False,
    )
    return links.keys() if isinstance(links, Mapping) else links
