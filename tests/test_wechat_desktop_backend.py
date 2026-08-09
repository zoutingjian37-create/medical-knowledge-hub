from datetime import date, datetime
import tempfile
import unittest
from pathlib import Path

from extensions.platforms.wechat.vision import ArticleCandidate, Rect, SHANGHAI_TZ


PUBLIC_A = "https://mp.weixin.qq.com/s/article-a"
PUBLIC_B = "https://mp.weixin.qq.com/s/article-b"


class _Session:
    def __init__(self, pages, copied):
        self.pages = pages
        self.copied = copied
        self.page = 0
        self.opened_account = ""
        self.open_account_calls = 0
        self.opened = []
        self.returned = 0

    def open_account_articles(self, account):
        self.open_account_calls += 1
        self.opened_account = account

    def list_visible_articles(self, now):
        return self.pages[self.page]

    def open_article(self, candidate):
        self.opened.append(candidate.title)

    def copy_current_link(self):
        return self.copied[self.opened[-1]]

    def return_to_articles(self):
        self.returned += 1

    def scroll_articles(self, steps=1):
        next_page = min(max(0, self.page + steps), len(self.pages) - 1)
        if next_page == self.page:
            return False
        self.page = next_page
        return True

    def recover_to_article_list(self):
        return False


class WeChatDesktopBackendTests(unittest.TestCase):
    def _candidate(self, title, published, top):
        return ArticleCandidate(title, published, Rect(10, top, 400, top + 30), "")

    def test_copy_failure_recovers_to_list_and_retries_same_article_locally(self):
        from extensions.platforms.wechat.desktop_vision import (
            WeChatDesktopError,
            WeChatDiscoveryIndex,
            WeChatVisualLinkBackend,
        )

        candidate = self._candidate("可恢复文章", date(2026, 8, 2), 160)

        class RecoveringSession(_Session):
            def __init__(self):
                super().__init__([(candidate,)], {candidate.title: (PUBLIC_A, candidate.published_date)})
                self.copy_calls = 0
                self.recoveries = 0

            def copy_current_link(self):
                self.copy_calls += 1
                if self.copy_calls == 1:
                    raise WeChatDesktopError(
                        "copy menu disappeared",
                        step="copy_link",
                        retry_from="article_list",
                    )
                return super().copy_current_link()

            def recover_to_article_list(self):
                self.recoveries += 1
                return True

        session = RecoveringSession()
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = WeChatVisualLinkBackend(
                session=session,
                index=WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json"),
                now_provider=lambda: datetime(2026, 8, 2, 9, 0, tzinfo=SHANGHAI_TZ),
            )
            links = backend.collect_links(
                "示例公众号",
                1,
                date_from=date(2026, 8, 2),
                date_to=date(2026, 8, 2),
            )

        self.assertEqual([PUBLIC_A], links)
        self.assertEqual(1, session.open_account_calls)
        self.assertEqual(1, session.recoveries)
        self.assertEqual([candidate.title, candidate.title], session.opened)

    def test_blocked_title_open_failure_returns_to_list_before_retrying_same_row(self):
        from extensions.platforms.wechat.desktop_vision import (
            WeChatDesktopError,
            WeChatDiscoveryIndex,
            WeChatVisualLinkBackend,
        )

        candidate = self._candidate("顶部被遮挡的文章", date(2026, 8, 2), 80)

        class BlockedOnceSession(_Session):
            def __init__(self):
                super().__init__([(candidate,)], {candidate.title: (PUBLIC_A, candidate.published_date)})
                self.open_attempts = 0
                self.recoveries = 0

            def open_article(self, requested):
                self.open_attempts += 1
                self.opened.append(requested.title)
                if self.open_attempts == 1:
                    raise WeChatDesktopError(
                        "sticky header still covered the title",
                        step="open_article",
                        retry_from="article_list",
                        progress_kept=True,
                    )

            def recover_to_article_list(self):
                self.recoveries += 1
                return True

        session = BlockedOnceSession()
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = WeChatVisualLinkBackend(
                session=session,
                index=WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json"),
                now_provider=lambda: datetime(2026, 8, 2, 9, 0, tzinfo=SHANGHAI_TZ),
            )
            links = backend.collect_links("示例公众号", 1)

        self.assertEqual([PUBLIC_A], links)
        self.assertEqual(1, session.open_account_calls)
        self.assertEqual(1, session.recoveries)
        self.assertEqual([candidate.title, candidate.title], session.opened)

    def test_irrecoverable_article_failure_reports_exact_step(self):
        from extensions.platforms.wechat.desktop_vision import (
            WeChatDesktopError,
            WeChatDiscoveryIndex,
            WeChatVisualLinkBackend,
        )

        candidate = self._candidate("无法恢复文章", date(2026, 8, 2), 160)

        class BrokenSession(_Session):
            def copy_current_link(self):
                raise WeChatDesktopError(
                    "copy menu disappeared",
                    step="copy_link",
                    retry_from="article_list",
                )

        session = BrokenSession([(candidate,)], {})
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = WeChatVisualLinkBackend(
                session=session,
                index=WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json"),
                now_provider=lambda: datetime(2026, 8, 2, 9, 0, tzinfo=SHANGHAI_TZ),
            )
            with self.assertRaises(WeChatDesktopError) as raised:
                backend.collect_links("示例公众号", 1)

        self.assertEqual("copy_link", raised.exception.step)
        self.assertEqual("article_list", raised.exception.retry_from)
        self.assertEqual(1, session.open_account_calls)

    def test_scroll_estimator_coarsens_far_away_and_becomes_precise_near_target(self):
        from extensions.platforms.wechat.desktop_vision import (
            _estimate_scroll_batch,
        )

        self.assertEqual(1, _estimate_scroll_batch(90, ()))
        self.assertEqual(8, _estimate_scroll_batch(90, (3.0, 4.0)))
        self.assertEqual(1, _estimate_scroll_batch(4, (3.0, 4.0)))

    def test_newest_real_dates_are_selected_and_pinned_old_article_is_ignored(self):
        from extensions.platforms.wechat.desktop_vision import (
            WeChatDiscoveryIndex,
            WeChatVisualLinkBackend,
        )

        pinned = self._candidate("置顶旧文", date(2026, 5, 26), 20)
        today = self._candidate("今日文章", date(2026, 8, 1), 120)
        yesterday = self._candidate("昨日文章", date(2026, 7, 31), 220)
        session = _Session(
            [(pinned, today, yesterday)],
            {
                "今日文章": (PUBLIC_A, date(2026, 8, 1)),
                "昨日文章": (PUBLIC_B, date(2026, 7, 31)),
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            index = WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json")
            backend = WeChatVisualLinkBackend(
                session=session,
                index=index,
                now_provider=lambda: datetime(2026, 8, 1, 9, 0, tzinfo=SHANGHAI_TZ),
            )

            links = backend.collect_links(
                "示例医学统计",
                2,
                date_from=date(2026, 7, 31),
                date_to=date(2026, 8, 1),
            )
            markers = index.markers()

        self.assertEqual([PUBLIC_A, PUBLIC_B], links)
        self.assertEqual(["今日文章", "昨日文章"], session.opened)
        self.assertEqual(2, session.returned)
        self.assertTrue(any("|2026-08-01|" in marker for marker in markers))
        self.assertTrue(any("|2026-07-31|" in marker for marker in markers))

    def test_article_header_date_mismatch_is_skipped_without_losing_valid_rows(self):
        from extensions.platforms.wechat.desktop_vision import (
            WeChatDiscoveryIndex,
            WeChatVisualLinkBackend,
        )

        mismatch = self._candidate("日期错配", date(2026, 8, 1), 100)
        valid = self._candidate("真实今日文章", date(2026, 8, 1), 200)
        session = _Session(
            [(mismatch, valid)],
            {
                "日期错配": (PUBLIC_A, date(2026, 7, 31)),
                "真实今日文章": (PUBLIC_B, date(2026, 8, 1)),
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            index = WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json")
            backend = WeChatVisualLinkBackend(
                session=session,
                index=index,
                now_provider=lambda: datetime(2026, 8, 1, 9, 0, tzinfo=SHANGHAI_TZ),
            )

            links = backend.collect_links(
                "示例医学统计",
                2,
                date_from=date(2026, 8, 1),
                date_to=date(2026, 8, 1),
            )

        self.assertEqual([PUBLIC_B], links)
        self.assertEqual(["日期错配", "真实今日文章"], session.opened)
        self.assertEqual(2, session.returned)
        self.assertFalse(any(PUBLIC_A in marker for marker in index.markers()))

    def test_discovery_audit_marker_does_not_consume_a_link_before_queueing(self):
        from extensions.platforms.wechat.desktop_vision import (
            WeChatDiscoveryIndex,
            WeChatVisualLinkBackend,
        )
        from extensions.platforms.wechat.vision import article_dedup_marker

        candidate = self._candidate("已存文章", date(2026, 8, 1), 100)
        session = _Session(
            [(candidate,)],
            {"已存文章": (PUBLIC_A, date(2026, 8, 1))},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            index = WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json")
            index.add(
                article_dedup_marker("示例医学统计", date(2026, 8, 1), PUBLIC_A)
            )
            backend = WeChatVisualLinkBackend(
                session=session,
                index=index,
                now_provider=lambda: datetime(2026, 8, 1, 9, 0, tzinfo=SHANGHAI_TZ),
            )

            links = backend.collect_links("示例医学统计", 1)

        self.assertEqual([PUBLIC_A], links)

    def test_old_target_date_is_reached_beyond_the_old_fixed_scroll_limit(self):
        from datetime import timedelta

        from extensions.platforms.wechat.desktop_vision import (
            WeChatDiscoveryIndex,
            WeChatVisualLinkBackend,
        )

        target = date(2026, 5, 1)
        pages = []
        copied = {}
        for offset in range(34):
            published = date(2026, 8, 2) - timedelta(days=offset)
            title = f"过渡文章 {offset}"
            pages.append((self._candidate(title, published, 100),))
            copied[title] = (f"https://mp.weixin.qq.com/s/page-{offset}", published)
        pages.append((self._candidate("五月一日目标文章", target, 100),))
        copied["五月一日目标文章"] = (PUBLIC_A, target)
        pages.append(
            (self._candidate("四月旧文", date(2026, 4, 30), 100),)
        )
        copied["四月旧文"] = (
            "https://mp.weixin.qq.com/s/april-old",
            date(2026, 4, 30),
        )
        session = _Session(pages, copied)

        with tempfile.TemporaryDirectory() as temp_dir:
            backend = WeChatVisualLinkBackend(
                session=session,
                index=WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json"),
                now_provider=lambda: datetime(2026, 8, 2, 9, 0, tzinfo=SHANGHAI_TZ),
            )
            links = backend.collect_links(
                "示例医学统计",
                1,
                date_from=target,
                date_to=target,
            )

        self.assertEqual([PUBLIC_A], links)
        self.assertGreaterEqual(session.page, 34)
        self.assertEqual(["五月一日目标文章"], session.opened)

    def test_every_discovered_target_row_must_be_opened_before_success(self):
        from extensions.platforms.wechat.desktop_vision import (
            WeChatDiscoveryIndex,
            WeChatVisualLinkBackend,
        )

        target = date(2026, 5, 1)
        first = self._candidate("五月一日第一篇", target, 100)
        second = self._candidate("五月一日第二篇", target, 200)
        older = self._candidate("四月旧文", date(2026, 4, 30), 100)
        session = _Session(
            [(first,), (first, second), (older,)],
            {
                "五月一日第一篇": (PUBLIC_A, target),
                "五月一日第二篇": (PUBLIC_B, target),
                "四月旧文": (
                    "https://mp.weixin.qq.com/s/april-old",
                    date(2026, 4, 30),
                ),
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = WeChatVisualLinkBackend(
                session=session,
                index=WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json"),
                now_provider=lambda: datetime(2026, 8, 2, 9, 0, tzinfo=SHANGHAI_TZ),
            )
            links = backend.collect_links(
                "示例医学统计",
                10,
                date_from=target,
                date_to=target,
            )

        self.assertEqual([PUBLIC_A, PUBLIC_B], links)
        self.assertEqual(["五月一日第一篇", "五月一日第二篇"], session.opened)

    def test_date_range_reuses_one_account_page_and_collects_all_visible_days(self):
        from extensions.platforms.wechat.desktop_vision import (
            WeChatDiscoveryIndex,
            WeChatVisualLinkBackend,
        )

        may_3 = self._candidate("五月三日文章", date(2026, 5, 3), 100)
        may_2 = self._candidate("五月二日文章", date(2026, 5, 2), 200)
        may_1 = self._candidate("五月一日文章", date(2026, 5, 1), 300)
        april_30 = self._candidate("四月三十日文章", date(2026, 4, 30), 100)
        third_url = "https://mp.weixin.qq.com/s/article-c"
        session = _Session(
            [(may_3, may_2, may_1), (april_30,)],
            {
                "五月三日文章": (PUBLIC_A, date(2026, 5, 3)),
                "五月二日文章": (PUBLIC_B, date(2026, 5, 2)),
                "五月一日文章": (third_url, date(2026, 5, 1)),
                "四月三十日文章": (
                    "https://mp.weixin.qq.com/s/april-30",
                    date(2026, 4, 30),
                ),
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = WeChatVisualLinkBackend(
                session=session,
                index=WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json"),
                now_provider=lambda: datetime(2026, 8, 2, 9, 0, tzinfo=SHANGHAI_TZ),
            )
            links = backend.collect_links(
                "示例医学统计",
                10,
                date_from=date(2026, 5, 1),
                date_to=date(2026, 5, 3),
            )

        self.assertEqual([PUBLIC_A, PUBLIC_B, third_url], links)
        self.assertEqual(1, session.open_account_calls)
        self.assertEqual(
            ["五月三日文章", "五月二日文章", "五月一日文章"],
            session.opened,
        )
        self.assertEqual(3, session.returned)
        self.assertEqual(1, session.page)

    def test_coarse_seek_targets_range_ceiling_before_collecting_every_day(self):
        from datetime import timedelta

        from extensions.platforms.wechat.desktop_vision import (
            WeChatDiscoveryIndex,
            WeChatVisualLinkBackend,
        )

        newest = date(2026, 5, 10)
        pages = []
        copied = {}
        expected = []
        for offset in range(17):
            published = newest - timedelta(days=offset)
            title = f"区间文章 {published.isoformat()}"
            url = f"https://mp.weixin.qq.com/s/range-{published:%m%d}"
            pages.append((self._candidate(title, published, 100),))
            copied[title] = (url, published)
            if date(2026, 4, 25) <= published <= date(2026, 5, 3):
                expected.append(url)
        session = _Session(pages, copied)

        with tempfile.TemporaryDirectory() as temp_dir:
            backend = WeChatVisualLinkBackend(
                session=session,
                index=WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json"),
                now_provider=lambda: datetime(2026, 8, 2, 9, 0, tzinfo=SHANGHAI_TZ),
            )
            links = backend.collect_links(
                "示例医学统计",
                50,
                date_from=date(2026, 4, 25),
                date_to=date(2026, 5, 3),
            )

        self.assertEqual(expected, links)
        self.assertEqual(1, session.open_account_calls)
        self.assertEqual(
            [f"区间文章 {newest - timedelta(days=offset)}" for offset in range(7, 16)],
            session.opened,
        )


if __name__ == "__main__":
    unittest.main()
