import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "web" / "index.html"
STYLES = ROOT / "web" / "styles.css"
APP_JS = ROOT / "web" / "app.js"


class ElementCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class WebUiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.css = STYLES.read_text(encoding="utf-8")
        cls.js = APP_JS.read_text(encoding="utf-8")
        parser = ElementCollector()
        parser.feed(cls.html)
        cls.elements = parser.elements
        cls.by_id = {
            attrs["id"]: (tag, attrs)
            for tag, attrs in cls.elements
            if attrs.get("id")
        }

    def test_semantic_three_column_shell_exists(self):
        required = {
            "appWorkspace",
            "courseSidebar",
            "leftResizer",
            "agentPanel",
            "rightResizer",
            "previewPanel",
            "previewToggle",
            "preview",
        }
        self.assertTrue(required.issubset(self.by_id))
        self.assertEqual(self.by_id["courseSidebar"][0], "aside")
        self.assertEqual(self.by_id["agentPanel"][0], "main")
        self.assertEqual(self.by_id["previewPanel"][0], "aside")

    def test_resizers_are_keyboard_accessible_separators(self):
        for element_id in ("leftResizer", "rightResizer"):
            self.assertIn(element_id, self.by_id)
            _, attrs = self.by_id[element_id]
            self.assertEqual(attrs.get("role"), "separator")
            self.assertEqual(attrs.get("aria-orientation"), "vertical")
            self.assertEqual(attrs.get("tabindex"), "0")
            self.assertTrue(attrs.get("aria-label"))

    def test_preview_and_upload_controls_exist(self):
        for element_id in (
            "previewToggle",
            "previewTabFile",
            "previewTabSources",
            "previewTabInfo",
            "courseFilePicker",
            "chatFilePicker",
        ):
            self.assertIn(element_id, self.by_id)
        self.assertEqual(self.by_id["previewToggle"][0], "button")
        self.assertEqual(self.by_id["courseFilePicker"][1].get("type"), "file")
        self.assertEqual(self.by_id["chatFilePicker"][1].get("type"), "file")

    def test_percentage_layout_contract_is_declared(self):
        self.assertIn("--sidebar-share: 22%", self.css)
        self.assertIn("--preview-share: 31%", self.css)
        self.assertIn("100dvh", self.css)
        self.assertIn("grid-template-columns", self.css)

    def test_layout_controller_contract_is_declared(self):
        for name in (
            "setupResizableLayout",
            "moveLeftBoundary",
            "moveRightBoundary",
            "setPreviewOpen",
            "renderLayout",
            "local-course-agent-layout-v1",
        ):
            self.assertIn(name, self.js)

    def test_high_risk_interaction_contracts_are_declared(self):
        for token in (
            "hasStoredLayout",
            "dblclick",
            "aria-valuemin",
            "setBusy",
            "previewByCitation",
            "citation.quote",
            "Escape",
            "inert",
            "activeCourse?.id !== courseId",
            "pendingChatFiles = []",
            'href="${url}${page}"',
        ):
            self.assertIn(token, self.html + self.css + self.js)
        self.assertNotIn("min-height: 30rem", self.css)

    def test_stale_preview_responses_are_guarded(self):
        for token in (
            "let previewRequestVersion = 0",
            "const requestVersion = ++previewRequestVersion",
            "previewRequestVersion += 1",
            "requestVersion !== previewRequestVersion",
            "activeCourse?.id !== courseId",
            "activeFile?.id !== fileId",
        ):
            self.assertIn(token, self.js)

    def test_stale_citation_preview_must_report_render_status(self):
        for token in (
            "return false",
            "return true",
            ".then((rendered) => {",
            "if (!rendered || activeCourse?.id !== courseId || activeFile?.id !== fileId) return",
        ):
            self.assertIn(token, self.js)


if __name__ == "__main__":
    unittest.main()
