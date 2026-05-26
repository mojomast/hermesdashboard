import json
import tempfile
import unittest
from pathlib import Path

import app as dashboard_app


class DashboardStatePersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old_path = dashboard_app.DASHBOARD_STATE_DB_PATH
        dashboard_app.DASHBOARD_STATE_DB_PATH = Path(self._tmpdir.name) / "dashboard_state.db"

    def tearDown(self):
        dashboard_app.DASHBOARD_STATE_DB_PATH = self._old_path
        self._tmpdir.cleanup()

    def test_round_trips_large_conversation_payload_in_sqlite(self):
        payload = [
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": "done",
                "events": [{"type": "tool_output", "content": "x" * 500_000}],
                "trace": {"nodes": [{"id": "n1", "payload": "y" * 500_000}]},
            },
        ]

        dashboard_app._save_dashboard_state("conversation", payload)
        found, loaded = dashboard_app._load_dashboard_state("conversation")

        self.assertTrue(found)
        self.assertEqual(loaded, payload)
        self.assertTrue(dashboard_app.DASHBOARD_STATE_DB_PATH.exists())
        self.assertGreater(dashboard_app.DASHBOARD_STATE_DB_PATH.stat().st_size, 900_000)

    def test_delete_dashboard_state_removes_value(self):
        dashboard_app._save_dashboard_state("active_run", {"runId": "run_123"})

        dashboard_app._delete_dashboard_state("active_run")
        found, loaded = dashboard_app._load_dashboard_state("active_run")

        self.assertFalse(found)
        self.assertIsNone(loaded)

    def test_rejects_unknown_dashboard_state_key(self):
        with self.assertRaises(ValueError):
            dashboard_app._save_dashboard_state("not_allowed", {"x": 1})


if __name__ == "__main__":
    unittest.main()
