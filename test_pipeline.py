import unittest
from pipeline import PipelineService

class TestPipelineService(unittest.TestCase):
    def setUp(self):
        # Load the mock JSON data provided in the prompt
        self.apps = [
            {"application_id": "app-001", "candidate_name": "Aisha Khan", "school": "Sample Tech", "academy_lane": "entry_level", "artifact_url": "url"},
            {"application_id": "app-002", "candidate_name": "Bilal Ahmed", "school": "Sample Biz", "academy_lane": "entry_level", "artifact_url": ""},
            {"application_id": "app-003", "candidate_name": "Sara Perera", "school": "Sample Eng", "academy_lane": "entry_level", "artifact_url": "url"},
            {"application_id": "app-004", "candidate_name": "Omar Rahman", "school": "Sample Tech", "academy_lane": "experienced", "artifact_url": "url"},
            {"application_id": "app-005", "candidate_name": "Aisha Khan", "school": "Sample Tech", "academy_lane": "entry_level", "artifact_url": "url"} # Duplicate
        ]
        self.events = [
            {"application_id": "app-001", "type": "application_received", "evidence": "complete"},
            {"application_id": "app-003", "type": "email_bounced", "evidence": "bounced"},
            {"application_id": "app-004", "type": "application_received", "evidence": "stale_no_followup"}
        ]
        self.routes = [
            {"institution": "Sample Tech", "status": "active"},
            {"institution": "Sample Eng", "status": "bounced_route"}
        ]
        self.service = PipelineService(self.apps, self.events, self.routes)

    def test_missing_evidence(self):
        self.service.normalize_state()
        queue = self.service.build_action_queue()
        app_2 = next(c for c in queue if c.application_id == "app-002")
        self.assertEqual(app_2.reason_code, "MISSING_EVIDENCE")

    def test_bounced_route(self):
        self.service.normalize_state()
        queue = self.service.build_action_queue()
        app_3 = next(c for c in queue if c.application_id == "app-003")
        self.assertEqual(app_3.reason_code, "BOUNCED_ROUTE")
        self.assertEqual(app_3.next_action, "HUMAN_REVIEW")

    def test_stale_and_out_of_lane(self):
        self.service.normalize_state()
        queue = self.service.build_action_queue()
        app_4 = next(c for c in queue if c.application_id == "app-004")
        # OUT_OF_LANE should take precedence over stale as it is a hard rejection
        self.assertEqual(app_4.reason_code, "OUT_OF_LANE")

    def test_duplicate_detection(self):
        self.service.normalize_state()
        queue = self.service.build_action_queue()
        app_5 = next(c for c in queue if c.application_id == "app-005")
        self.assertEqual(app_5.reason_code, "DUPLICATE_APPLICANT")

    def test_idempotency(self):
        # First run should take actions
        first_run = self.service.process_queue_idempotent()
        self.assertTrue(any("ACTION TAKEN" in log for log in first_run if "app-001" in log))
        
        # Second run should skip everything processed
        second_run = self.service.process_queue_idempotent()
        self.assertTrue(all("SKIPPED" in log for log in second_run))

if __name__ == '__main__':
    unittest.main()