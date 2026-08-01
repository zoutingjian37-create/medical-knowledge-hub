from datetime import date, datetime
import unittest


class WeChatDateRecognitionTests(unittest.TestCase):
    def setUp(self):
        from extensions.platforms.wechat.vision import SHANGHAI_TZ

        self.now = datetime(2026, 8, 1, 9, 30, tzinfo=SHANGHAI_TZ)

    def test_relative_labels_become_concrete_calendar_dates(self):
        from extensions.platforms.wechat.vision import parse_wechat_date

        self.assertEqual(date(2026, 8, 1), parse_wechat_date("今天", self.now))
        self.assertEqual(date(2026, 7, 31), parse_wechat_date("昨天", self.now))
        self.assertEqual(date(2026, 7, 30), parse_wechat_date("星期四", self.now))
        self.assertEqual(date(2026, 7, 29), parse_wechat_date("周三", self.now))

    def test_month_day_and_full_date_are_recognized(self):
        from extensions.platforms.wechat.vision import parse_wechat_date

        self.assertEqual(date(2026, 7, 31), parse_wechat_date("7月31日", self.now))
        self.assertEqual(
            date(2025, 12, 31),
            parse_wechat_date(
                "12月31日",
                datetime(2026, 1, 2, 8, 0, tzinfo=self.now.tzinfo),
            ),
        )
        self.assertEqual(
            date(2024, 2, 29), parse_wechat_date("2024年2月29日", self.now)
        )

    def test_recent_hour_label_uses_beijing_time_and_can_cross_midnight(self):
        from extensions.platforms.wechat.vision import parse_wechat_date

        now = datetime(2026, 8, 1, 3, 0, tzinfo=self.now.tzinfo)
        self.assertEqual(date(2026, 7, 31), parse_wechat_date("10小时前", now))
        self.assertEqual(date(2026, 8, 1), parse_wechat_date("30分钟前", now))

    def test_date_prefix_is_read_from_the_real_wechat_metadata_line(self):
        from extensions.platforms.wechat.vision import parse_wechat_date

        self.assertEqual(
            date(2026, 8, 1), parse_wechat_date("今天阅读57赞2", self.now)
        )
        self.assertEqual(
            date(2026, 7, 31), parse_wechat_date("咋天 阅读151赞6", self.now)
        )
        self.assertEqual(
            date(2026, 7, 30), parse_wechat_date("星期四阅读68赞3", self.now)
        )
        self.assertEqual(
            date(2026, 5, 26), parse_wechat_date("5月26日阅读2634赞15", self.now)
        )

    def test_same_weekday_label_is_rejected_as_inconsistent_with_wechat_ui(self):
        from extensions.platforms.wechat.vision import parse_wechat_date

        self.assertIsNone(parse_wechat_date("星期六", self.now))


class WeChatArticleSelectionTests(unittest.TestCase):
    def test_network_search_row_is_chosen_instead_of_local_account_chat(self):
        from extensions.platforms.wechat.vision import (
            OCRToken,
            Rect,
            VisionSnapshot,
            locate_network_search,
        )

        target = "示例医学统计"
        snapshot = VisionSnapshot(
            Rect(0, 0, 1000, 1200),
            (
                OCRToken(target, Rect(160, 85, 330, 110)),
                OCRToken(target, Rect(200, 200, 420, 230)),
                OCRToken("搜索网络结果", Rect(170, 478, 290, 502)),
                OCRToken(f"Q {target}", Rect(137, 523, 340, 550)),
            ),
        )

        self.assertEqual(
            Rect(137, 523, 340, 550), locate_network_search(snapshot, target)
        )

    def test_exact_account_result_ignores_search_field_and_related_searches(self):
        from extensions.platforms.wechat.vision import (
            OCRToken,
            Rect,
            VisionSnapshot,
            locate_exact_account,
        )

        target = "示例医学统计"
        snapshot = VisionSnapshot(
            Rect(0, 0, 1400, 1300),
            (
                OCRToken(target, Rect(80, 100, 300, 130)),
                OCRToken(f"{target} - 账号", Rect(80, 270, 360, 300)),
                OCRToken(target, Rect(190, 350, 440, 380)),
                OCRToken("公众号", Rect(190, 390, 260, 415)),
                OCRToken(f"{target}官网", Rect(1090, 660, 1290, 690)),
            ),
        )

        result = locate_exact_account(snapshot, target)

        self.assertEqual(Rect(190, 350, 440, 380), result)

    def test_full_article_header_date_can_be_read_inside_author_line(self):
        from extensions.platforms.wechat.vision import extract_article_header_date

        self.assertEqual(
            date(2026, 7, 31),
            extract_article_header_date(
                "医学统计指导找→示例医学统计 2026年7月31日"
            ),
        )

    def test_copy_link_menu_item_is_located_by_text_not_coordinates(self):
        from extensions.platforms.wechat.vision import (
            OCRToken,
            Rect,
            VisionSnapshot,
            locate_copy_link,
        )

        snapshot = VisionSnapshot(
            Rect(100, 50, 1430, 1380),
            (
                OCRToken("刷新", Rect(850, 80, 900, 110)),
                OCRToken("复制链接", Rect(850, 123, 940, 150)),
            ),
        )

        self.assertEqual(Rect(850, 123, 940, 150), locate_copy_link(snapshot))

    def test_article_rows_are_associated_with_their_concrete_dates(self):
        from extensions.platforms.wechat.vision import (
            OCRToken,
            Rect,
            extract_article_candidates,
        )

        from extensions.platforms.wechat.vision import SHANGHAI_TZ

        now = datetime(2026, 8, 1, 9, 30, tzinfo=SHANGHAI_TZ)
        tokens = (
            OCRToken("接收喜报", Rect(20, 50, 110, 70)),
            OCRToken("协变量调整的三个", Rect(20, 100, 380, 125)),
            OCRToken("陷阱", Rect(20, 130, 90, 155)),
            OCRToken("今天阅读57赞2", Rect(20, 165, 180, 188)),
            OCRToken("童年暴露与成年心血管病", Rect(20, 230, 430, 255)),
            OCRToken("星期四阅读68赞3", Rect(20, 265, 200, 288)),
        )

        candidates = extract_article_candidates(tokens, now)

        self.assertEqual(2, len(candidates))
        self.assertEqual(date(2026, 8, 1), candidates[0].published_date)
        self.assertEqual("协变量调整的三个陷阱", candidates[0].title)
        self.assertEqual(date(2026, 7, 30), candidates[1].published_date)

    def test_date_range_is_applied_before_limit(self):
        from extensions.platforms.wechat.vision import ArticleCandidate, Rect, select_articles

        candidates = (
            ArticleCandidate("当天", date(2026, 8, 1), Rect(0, 0, 10, 10), "今天"),
            ArticleCandidate("昨天", date(2026, 7, 31), Rect(0, 10, 10, 20), "昨天"),
            ArticleCandidate("更早", date(2026, 7, 30), Rect(0, 20, 10, 30), "星期四"),
        )

        selected = select_articles(
            candidates,
            date_from=date(2026, 7, 30),
            date_to=date(2026, 7, 31),
            limit=1,
        )

        self.assertEqual(("昨天",), tuple(item.title for item in selected))

    def test_dedup_marker_contains_account_concrete_date_and_canonical_url(self):
        from extensions.platforms.wechat.vision import article_dedup_marker

        marker = article_dedup_marker(
            " 示例 医学统计号 ",
            date(2026, 7, 30),
            "https://mp.weixin.qq.com/s/example?scene=21#wechat_redirect",
        )

        self.assertEqual(
            "示例医学统计号|2026-07-30|https://mp.weixin.qq.com/s/example",
            marker,
        )


if __name__ == "__main__":
    unittest.main()
