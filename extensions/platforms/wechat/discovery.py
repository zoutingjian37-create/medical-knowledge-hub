"""Public-search discovery with an optional desktop WeChat UI fallback.

The public API returns URLs only. It never accepts or exposes WeChat backend
credentials, message databases, or account tokens.
"""

from collections.abc import Iterable, Mapping
import asyncio
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


# Compatibility name for callers of the earlier UI-only boundary.
WeChatUIDiscoveryError = WeChatDiscoveryError


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
    def __init__(self, backend: Optional[PyWeixinLinkBackend] = None):
        self._backend = backend or PyWeixinLinkBackend()

    def discover(
        self, accounts: Iterable[str], per_account: int = 10
    ) -> tuple[str, ...]:
        if per_account < 1:
            raise ValueError("per_account must be at least 1")
        discovered = []
        seen = set()
        for account in accounts:
            account = str(account).strip()
            if not account:
                continue
            for candidate in self._backend.collect_links(account, per_account):
                try:
                    public_url = canonicalize_public_article_url(candidate)
                except ValueError:
                    continue
                if public_url not in seen:
                    seen.add(public_url)
                    discovered.append(public_url)
        return tuple(discovered)


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
