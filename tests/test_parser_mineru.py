import unittest
from unittest import mock

from local_course_agent.mineru_api import MineruAgentClient
from local_course_agent.parser import discover_mineru_command


class MineruDiscoveryTest(unittest.TestCase):
    def test_prefers_configured_command(self):
        self.assertEqual(discover_mineru_command({"command": "mineru -p {input}"}), "mineru -p {input}")

    def test_auto_discovers_known_binary(self):
        with mock.patch("local_course_agent.parser.shutil.which") as which:
            which.side_effect = lambda name: "/usr/bin/mineru" if name == "mineru" else None

            self.assertEqual(discover_mineru_command({"auto": True}), 'mineru -p "{input}"')

    def test_returns_empty_when_disabled(self):
        self.assertEqual(discover_mineru_command({"auto": False}), "")

    def test_mineru_agent_client_adds_authorization_header(self):
        client = MineruAgentClient(token="test-token")

        self.assertEqual(client._headers().get("Authorization"), "Bearer test-token")


if __name__ == "__main__":
    unittest.main()
