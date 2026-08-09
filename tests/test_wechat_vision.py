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
    def test_article_tab_rows_use_the_date_on_the_same_metadata_line(self):
        from extensions.platforms.wechat.vision import (
            OCRToken,
            Rect,
            SHANGHAI_TZ,
            extract_article_tab_candidates,
        )

        now = datetime(2026, 8, 2, 20, 0, tzinfo=SHANGHAI_TZ)
        tokens = (
            OCRToken("文章", Rect(480, 390, 530, 420)),
            OCRToken("逻辑回归、COX回归与竞争风险模型的适用场", Rect(405, 515, 840, 540)),
            OCRToken("景全解（附案例文献）", Rect(405, 545, 650, 570)),
            OCRToken("今天 阅读 222 赞 6", Rect(405, 580, 610, 605)),
            OCRToken("GBD数据库四区发文，2026年的最低工作量是", Rect(405, 660, 840, 685)),
            OCRToken("多少？", Rect(405, 690, 490, 715)),
            OCRToken("昨天 阅读 393", Rect(405, 730, 570, 755)),
            OCRToken("公共数据库创新方向—多状态模型实操指南", Rect(405, 805, 825, 830)),
            OCRToken("（附SCI案例）", Rect(405, 835, 560, 860)),
            OCRToken("星期五 阅读 348 赞 6", Rect(405, 875, 625, 900)),
        )

        candidates = extract_article_tab_candidates(tokens, now)

        self.assertEqual(
            [
                ("逻辑回归、COX回归与竞争风险模型的适用场景全解(附案例文献)", date(2026, 8, 2)),
                ("GBD数据库四区发文,2026年的最低工作量是多少?", date(2026, 8, 1)),
                ("公共数据库创新方向—多状态模型实操指南(附SCI案例)", date(2026, 7, 31)),
            ],
            [(item.title, item.published_date) for item in candidates],
        )

    def test_article_tab_does_not_prepend_the_category_chips_to_first_title(self):
        from extensions.platforms.wechat.vision import (
            OCRToken,
            Rect,
            SHANGHAI_TZ,
            extract_article_tab_candidates,
        )

        tokens = (
            OCRToken("GBD", Rect(400, 100, 470, 125)),
            OCRToken("公共数据库答疑解惑", Rect(490, 100, 680, 125)),
            OCRToken("逻辑回归与竞争风险模型", Rect(400, 160, 720, 185)),
            OCRToken("适用场景全解", Rect(400, 190, 600, 215)),
            OCRToken("今天 阅读 224 赞 6", Rect(400, 225, 610, 250)),
        )

        candidates = extract_article_tab_candidates(
            tokens,
            datetime(2026, 8, 2, 20, 0, tzinfo=SHANGHAI_TZ),
        )

        self.assertEqual("逻辑回归与竞争风险模型适用场景全解", candidates[0].title)

    def test_article_tab_navigation_label_is_never_merged_into_clipped_first_row(self):
        from extensions.platforms.wechat.vision import (
            OCRToken,
            Rect,
            SHANGHAI_TZ,
            extract_article_tab_candidates,
        )

        tokens = (
            OCRToken("全部", Rect(405, 130, 450, 155)),
            OCRToken("文章", Rect(485, 130, 530, 155)),
            OCRToken("视频号", Rect(565, 130, 635, 155)),
            OCRToken("到底有什么区别?", Rect(410, 180, 635, 205)),
            OCRToken("7月23日 阅读 326 赞 2", Rect(410, 215, 620, 240)),
        )

        candidates = extract_article_tab_candidates(
            tokens,
            datetime(2026, 8, 2, 20, 0, tzinfo=SHANGHAI_TZ),
        )

        self.assertEqual("到底有什么区别?", candidates[0].title)
        self.assertEqual(Rect(410, 180, 635, 205), candidates[0].click_rect)

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

    def test_exact_account_result_accepts_high_resolution_card_near_top(self):
        from extensions.platforms.wechat.vision import (
            OCRToken,
            Rect,
            VisionSnapshot,
            locate_exact_account,
        )

        target = "示例医学统计"
        snapshot = VisionSnapshot(
            Rect(0, 0, 3862, 2110),
            (
                OCRToken(target, Rect(1315, 129, 1542, 155)),
                OCRToken(f"{target} - 账号", Rect(1310, 305, 1670, 340)),
                OCRToken(target, Rect(1428, 370, 1670, 399)),
                OCRToken("公众号", Rect(1428, 410, 1510, 438)),
                OCRToken(f"{target}官网", Rect(3100, 680, 3420, 720)),
            ),
        )

        self.assertEqual(
            Rect(1428, 370, 1670, 399),
            locate_exact_account(snapshot, target),
        )

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
            OCRToken("文章", Rect(20, 50, 80, 70)),
            OCRToken("今天", Rect(20, 100, 80, 125)),
            OCRToken("协变量调整的三个", Rect(20, 145, 380, 170)),
            OCRToken("陷阱", Rect(20, 175, 90, 200)),
            OCRToken("阅读 220 赞 6", Rect(20, 210, 180, 233)),
            OCRToken("医学顶刊最近使用的统计方法", Rect(20, 260, 430, 285)),
            OCRToken("阅读 151 赞 6", Rect(20, 295, 200, 318)),
            OCRToken("昨天", Rect(20, 350, 80, 375)),
            OCRToken("童年暴露与成年心血管病", Rect(20, 395, 430, 420)),
            OCRToken("阅读 68 赞 3", Rect(20, 430, 200, 453)),
            OCRToken("星期五", Rect(20, 490, 100, 515)),
            OCRToken("公共数据库创新方向", Rect(20, 535, 430, 560)),
            OCRToken("阅读 348 赞 6", Rect(20, 570, 200, 593)),
            OCRToken("MIMIC 学员接收", Rect(20, 630, 430, 655)),
            OCRToken("阅读 87", Rect(20, 665, 200, 688)),
        )

        candidates = extract_article_candidates(tokens, now)

        self.assertEqual(5, len(candidates))
        self.assertEqual(date(2026, 8, 1), candidates[0].published_date)
        self.assertEqual("协变量调整的三个陷阱", candidates[0].title)
        self.assertEqual(date(2026, 8, 1), candidates[1].published_date)
        self.assertEqual("医学顶刊最近使用的统计方法", candidates[1].title)
        self.assertEqual(date(2026, 7, 31), candidates[2].published_date)
        self.assertEqual(date(2026, 7, 31), candidates[3].published_date)
        self.assertEqual(date(2026, 7, 31), candidates[4].published_date)

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

    def test_date_group_continues_across_viewports_until_the_next_header(self):
        from extensions.platforms.wechat.vision import (
            OCRToken,
            Rect,
            extract_article_candidates,
        )

        from extensions.platforms.wechat.vision import SHANGHAI_TZ

        now = datetime(2026, 8, 2, 20, 0, tzinfo=SHANGHAI_TZ)
        first_view = (
            OCRToken("5月1日", Rect(20, 20, 100, 45)),
            OCRToken("第一篇五月一日文章", Rect(20, 70, 350, 95)),
            OCRToken("阅读 100", Rect(20, 105, 150, 128)),
            OCRToken("第二篇五月一日文章", Rect(20, 170, 350, 195)),
        )
        second_view = (
            OCRToken("第二篇五月一日文章", Rect(20, 10, 350, 35)),
            OCRToken("阅读 80", Rect(20, 45, 150, 68)),
            OCRToken("4月30日", Rect(20, 110, 100, 135)),
            OCRToken("四月旧文", Rect(20, 160, 350, 185)),
            OCRToken("阅读 60", Rect(20, 195, 150, 218)),
        )

        first = extract_article_candidates(first_view, now)
        second = extract_article_candidates(
            second_view,
            now,
            inherited_date=date(2026, 5, 1),
        )

        self.assertEqual(["第一篇五月一日文章"], [item.title for item in first])
        self.assertEqual(
            [
                ("第二篇五月一日文章", date(2026, 5, 1)),
                ("四月旧文", date(2026, 4, 30)),
            ],
            [(item.title, item.published_date) for item in second],
        )

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
