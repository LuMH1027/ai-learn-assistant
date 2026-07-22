import unittest
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

from local_course_agent.parser import discover_mineru_command, extract_text
from local_course_agent.parser.mineru import MineruAgentClient


class MineruDiscoveryTest(unittest.TestCase):
    def test_prefers_configured_command(self):
        self.assertEqual(discover_mineru_command({"command": "mineru -p {input}"}), "mineru -p {input}")

    def test_auto_discovers_known_binary(self):
        with mock.patch("local_course_agent.parser.mineru.shutil.which") as which:
            which.side_effect = lambda name: "/usr/bin/mineru" if name == "mineru" else None

            self.assertEqual(discover_mineru_command({"auto": True}), 'mineru -p "{input}"')

    def test_returns_empty_when_disabled(self):
        self.assertEqual(discover_mineru_command({"auto": False}), "")

    def test_mineru_agent_client_adds_authorization_header(self):
        client = MineruAgentClient(token="test-token")

        self.assertEqual(client._headers().get("Authorization"), "Bearer test-token")

    def test_extracts_docx_paragraph_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.docx"
            xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>"
                "<w:p><w:r><w:t>页表用于地址转换。</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>TLB 缓存常用页表项。</w:t></w:r></w:p>"
                "</w:body></w:document>"
            )
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml", xml)

            pages = extract_text(path)

            self.assertEqual(pages[0]["page"], None)
            self.assertIn("页表用于地址转换", pages[0]["text"])
            self.assertIn("TLB 缓存", pages[0]["text"])


if __name__ == "__main__":
    unittest.main()
