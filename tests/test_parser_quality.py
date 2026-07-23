import unittest

from local_course_agent.ingestion.parser_quality import evaluate_parser_quality


class ParserQualityTest(unittest.TestCase):
    def test_empty_result_fails(self):
        report = evaluate_parser_quality([])

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["score"], 0.0)
        self.assertEqual(report["warnings"][0]["code"], "empty_text")

    def test_ok_text_scores_high(self):
        report = evaluate_parser_quality(
            [
                {"page": 1, "text": "页表用于保存虚拟页到物理页框的映射，TLB 用于缓存常用页表项并减少地址转换开销。"},
                {"page": 2, "text": "缺页中断发生时，操作系统会把所需页面调入内存，更新页表，并恢复被中断的指令执行。"},
            ],
            expected_pages=2,
        )

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["metrics"]["coverage"], 1.0)
        self.assertGreaterEqual(report["score"], 0.85)

    def test_detects_error_message(self):
        report = evaluate_parser_quality(
            [{"page": None, "text": "PDF 解析失败：notes.pdf，原因：bad xref"}],
            expected_pages=1,
        )

        codes = [warning["code"] for warning in report["warnings"]]
        self.assertEqual(report["status"], "warning")
        self.assertIn("error_message", codes)
        self.assertLess(report["score"], 0.85)

    def test_detects_image_placeholder(self):
        report = evaluate_parser_quality(
            [{"page": None, "text": "图片文件已保存：diagram.png。如果当前配置的模型支持视觉输入，聊天时会直接读取截图内容。"}]
        )

        codes = [warning["code"] for warning in report["warnings"]]
        self.assertEqual(report["status"], "warning")
        self.assertIn("image_placeholder", codes)
        self.assertEqual(report["metrics"]["image_placeholder_pages"], 1)

    def test_detects_ocr_placeholder(self):
        report = evaluate_parser_quality(
            [{"page": 1, "text": "扫描件 PDF 需要 OCR 后才能提取正文。"}],
            expected_pages=1,
        )

        codes = [warning["code"] for warning in report["warnings"]]
        self.assertIn("ocr_placeholder", codes)
        self.assertEqual(report["metrics"]["ocr_placeholder_pages"], 1)

    def test_detects_short_page(self):
        report = evaluate_parser_quality([{"page": 1, "text": "定义。"}], short_page_threshold=10)

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["warnings"][0]["code"], "short_page")
        self.assertEqual(report["metrics"]["short_pages"], 1)

    def test_detects_low_page_coverage_from_expected_pages(self):
        report = evaluate_parser_quality(
            [
                {"page": 1, "text": "第一页内容足够长，用于模拟成功抽取的教材正文。"},
                {"page": 3, "text": "第三页内容足够长，用于模拟中间页面缺失。"},
            ],
            expected_pages=5,
        )

        codes = [warning["code"] for warning in report["warnings"]]
        self.assertIn("low_page_coverage", codes)
        self.assertEqual(report["metrics"]["coverage"], 0.4)
        self.assertEqual(report["status"], "warning")


if __name__ == "__main__":
    unittest.main()
