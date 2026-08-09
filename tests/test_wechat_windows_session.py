import unittest

from datetime import date
from unittest.mock import patch

from extensions.platforms.wechat.vision import (
    ArticleCandidate,
    Rect,
    VisionSnapshot,
)


class WeChatProcessClassificationTests(unittest.TestCase):
    def test_logged_in_window_is_maximized_before_size_validation(self):
        from extensions.platforms.wechat.windows_session import (
            WindowsWeChatVisionSession,
        )

        session = WindowsWeChatVisionSession.__new__(WindowsWeChatVisionSession)
        session.timeout = 3
        maximized = {"value": False}

        def show_and_focus(_handle, maximize=False):
            maximized["value"] = bool(maximize)

        def snapshot(_handle):
            bounds = Rect(0, 0, 1380, 900) if maximized["value"] else Rect(0, 0, 420, 320)
            return VisionSnapshot(bounds=bounds, tokens=())

        session._snapshot = snapshot
        session._fail = lambda message, handle: (_ for _ in ()).throw(
            AssertionError(message)
        )

        with (
            patch(
                "extensions.platforms.wechat.windows_session._wechat_windows",
                return_value=[101],
            ),
            patch(
                "extensions.platforms.wechat.windows_session._window_rect",
                return_value=Rect(0, 0, 420, 320),
            ),
            patch(
                "extensions.platforms.wechat.windows_session._show_and_focus",
                side_effect=show_and_focus,
            ),
        ):
            handle = session._ensure_logged_in_main_window()

        self.assertEqual(101, handle)
        self.assertTrue(maximized["value"])

    def test_title_under_sticky_header_requires_a_small_upward_reveal(self):
        from extensions.platforms.wechat.windows_session import (
            _candidate_needs_top_reveal,
        )

        bounds = Rect(0, 0, 1380, 1336)
        clipped = ArticleCandidate(
            "到底有什么区别?",
            date(2026, 7, 23),
            Rect(411, 169, 574, 198),
            "7月23日",
        )
        fully_visible = ArticleCandidate(
            "自己医院数据集构建预测模型",
            date(2026, 7, 22),
            Rect(414, 287, 836, 342),
            "7月22日",
        )

        self.assertTrue(_candidate_needs_top_reveal(clipped, bounds))
        self.assertFalse(_candidate_needs_top_reveal(fully_visible, bounds))

    def test_repainted_article_row_uses_its_fresh_click_rectangle(self):
        from extensions.platforms.wechat.windows_session import _match_candidate

        stale = ArticleCandidate(
            "竞争风险/轨迹模型/交叉滞后：医学高分文章常用进阶方法",
            date(2026, 5, 1),
            Rect(100, 600, 500, 650),
            "5月1日",
        )
        repainted = ArticleCandidate(
            "竞争风险／轨迹模型／交叉滞后:医学高分文章常用进阶方法",
            date(2026, 5, 1),
            Rect(120, 560, 520, 610),
            "5月1日",
        )

        matched = _match_candidate((repainted,), stale)

        self.assertIs(repainted, matched)

    def test_unique_title_rebinds_when_repaint_temporarily_loses_the_date_group(self):
        from extensions.platforms.wechat.windows_session import _match_candidate

        stale = ArticleCandidate(
            "GBD数据库四区发文，2026年的最低工作量是多少？",
            date(2026, 8, 1),
            Rect(100, 600, 500, 650),
            "昨天",
        )
        repainted = ArticleCandidate(
            "GBD数据库四区发文,2026年的最低工作量是多少?",
            date(2026, 8, 2),
            Rect(120, 560, 520, 610),
            "今天",
        )

        matched = _match_candidate((repainted,), stale)

        self.assertIs(repainted, matched)

    def test_article_navigation_uses_directional_page_keys(self):
        from extensions.platforms.wechat.windows_session import _scroll_command

        self.assertEqual(("pagedown", 3), _scroll_command(3))
        self.assertEqual(("pageup", 2), _scroll_command(-2))

    def test_main_weixin_window_is_trusted(self):
        from extensions.platforms.wechat.windows_session import _wechat_process_kind

        self.assertEqual(
            "main",
            _wechat_process_kind(r"C:\Program Files\Tencent\Weixin\Weixin.exe"),
        )

    def test_wechat_app_ex_is_trusted_only_when_descended_from_weixin(self):
        from extensions.platforms.wechat.windows_session import _wechat_process_kind

        app_ex = (
            r"C:\Users\admin\AppData\Roaming\Tencent\xwechat\xplugin\plugins"
            r"\RadiumWMPF\25297\extracted\runtime\WeChatAppEx.exe"
        )
        main = r"C:\Program Files\Tencent\Weixin\Weixin.exe"

        self.assertEqual("web", _wechat_process_kind(app_ex, (main,)))
        self.assertIsNone(_wechat_process_kind(app_ex, ()))

    def test_unrelated_visible_window_is_not_trusted(self):
        from extensions.platforms.wechat.windows_session import _wechat_process_kind

        self.assertIsNone(
            _wechat_process_kind(
                r"C:\Program Files\Browser\browser.exe",
                (r"C:\Program Files\Tencent\Weixin\Weixin.exe",),
            )
        )

    def test_large_hidden_main_window_can_be_restored_from_the_tray(self):
        from extensions.platforms.wechat.windows_session import (
            _should_include_wechat_window,
        )

        self.assertTrue(
            _should_include_wechat_window(
                "main",
                visible=False,
                width=1320,
                height=899,
                include_hidden=True,
                class_name="Qt51514QWindowIcon",
                title="微信",
            )
        )
        self.assertFalse(
            _should_include_wechat_window(
                "main",
                visible=False,
                width=295,
                height=387,
                include_hidden=True,
                class_name="Qt51514QWindowIcon",
                title="微信",
            )
        )

    def test_minimized_main_window_with_sentinel_bounds_can_be_restored(self):
        from extensions.platforms.wechat.windows_session import (
            _should_include_wechat_window,
        )

        self.assertTrue(
            _should_include_wechat_window(
                "main",
                visible=True,
                iconic=True,
                width=158,
                height=26,
                include_hidden=True,
                class_name="Qt51514QWindowIcon",
                title="微信",
            )
        )


if __name__ == "__main__":
    unittest.main()
