"""Windows WeChat UI discovery boundary.

The public API returns URLs only. It never accepts or exposes WeChat backend
credentials, message databases, or account tokens.
"""

from collections.abc import Iterable, Mapping
import multiprocessing
from queue import Empty
from typing import Optional

from .public_link import canonicalize_public_article_url


class WeChatUIDiscoveryError(RuntimeError):
    """The local WeChat UI could not complete link discovery."""


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
