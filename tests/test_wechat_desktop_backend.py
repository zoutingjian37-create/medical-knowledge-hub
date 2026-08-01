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
        self.opened = []
        self.returned = 0

    def open_account_articles(self, account):
        self.opened_account = account

    def list_visible_articles(self, now):
        return self.pages[self.page]

    def open_article(self, candidate):
        self.opened.append(candidate.title)

    def copy_current_link(self):
        return self.copied[self.opened[-1]]

    def return_to_articles(self):
        self.returned += 1

    def scroll_articles(self):
        if self.page + 1 >= len(self.pages):
            return False
        self.page += 1
        return True


class WeChatDesktopBackendTests(unittest.TestCase):
    def _candidate(self, title, published, top):
        return ArticleCandidate(title, published, Rect(10, top, 400, top + 30), "")

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

    def test_article_header_date_must_match_the_list_date(self):
        from extensions.platforms.wechat.desktop_vision import (
            WeChatDesktopError,
            WeChatDiscoveryIndex,
            WeChatVisualLinkBackend,
        )

        candidate = self._candidate("日期错配", date(2026, 8, 1), 100)
        session = _Session(
            [(candidate,)],
            {"日期错配": (PUBLIC_A, date(2026, 7, 31))},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = WeChatVisualLinkBackend(
                session=session,
                index=WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json"),
                now_provider=lambda: datetime(2026, 8, 1, 9, 0, tzinfo=SHANGHAI_TZ),
            )

            with self.assertRaisesRegex(WeChatDesktopError, "date mismatch"):
                backend.collect_links("示例医学统计", 1)

        self.assertEqual(1, session.returned)

    def test_existing_account_date_url_marker_is_not_emitted_again(self):
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

        self.assertEqual([], links)


if __name__ == "__main__":
    unittest.main()
