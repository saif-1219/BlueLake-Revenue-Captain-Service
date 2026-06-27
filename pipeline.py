import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# --- 1. DATA MODELS & STATE ---

@dataclass
class CandidateState:
    application_id: str
    name: str
    school: str
    academy_lane: str
    artifact_url: str
    events: List[Dict] = field(default_factory=list)
    route_status: str = "unknown"
    
    # Processed output
    status: str = "PENDING"
    reason_code: str = "NONE"
    next_action: str = "NONE"
    priority: int = 99

class PipelineService:
    def __init__(self, applications: List[Dict], events: List[Dict], routes: List[Dict]):
        self.raw_apps = applications
        self.raw_events = events
        self.raw_routes = {r['institution']: r for r in routes}
        self.state_db: Dict[str, CandidateState] = {}
        self.processed_actions = set() # Simulates an idempotency key store

    # --- 2. NORMALIZATION & HYDRATION ---
    def normalize_state(self):
        """Builds the current state of all candidates from raw inputs."""
        for app in self.raw_apps:
            school_route = self.raw_routes.get(app['school'], {})
            
            state = CandidateState(
                application_id=app['application_id'],
                name=app['candidate_name'],
                school=app['school'],
                academy_lane=app['academy_lane'],
                artifact_url=app['artifact_url'],
                route_status=school_route.get('status', 'unknown')
            )
            
            # Attach events
            state.events = [e for e in self.raw_events if e['application_id'] == state.application_id]
            self.state_db[state.application_id] = state

    # --- 3. QUEUE & RULES ENGINE ---
    def build_action_queue(self) -> List[CandidateState]:
        """Evaluates rules and returns a ranked next-action queue."""
        queue = []
        seen_signatures = set() # For duplicate detection

        for app_id, candidate in self.state_db.items():
            # Rule 1: Duplicate Detection
            signature = f"{candidate.name.lower()}_{candidate.school.lower()}"
            if signature in seen_signatures:
                candidate.status, candidate.reason_code, candidate.next_action = "REJECTED", "DUPLICATE_APPLICANT", "ARCHIVE"
                candidate.priority = 4
                queue.append(candidate)
                continue
            seen_signatures.add(signature)

            # Rule 2: Lane check
            if candidate.academy_lane != "entry_level":
                candidate.status, candidate.reason_code, candidate.next_action = "REJECTED", "OUT_OF_LANE", "ARCHIVE"
                candidate.priority = 4
            
            # Rule 3: Missing Evidence
            elif not candidate.artifact_url or any(e['evidence'] == 'missing_artifact' for e in candidate.events):
                candidate.status, candidate.reason_code, candidate.next_action = "BLOCKED", "MISSING_EVIDENCE", "REQUEST_EVIDENCE"
                candidate.priority = 2
                
            # Rule 4: Bounced Route
            elif candidate.route_status == "bounced_route" or any(e['type'] == 'email_bounced' for e in candidate.events):
                candidate.status, candidate.reason_code, candidate.next_action = "ESCALATED", "BOUNCED_ROUTE", "HUMAN_REVIEW"
                candidate.priority = 1 # High priority to fix communication
                
            # Rule 5: Stale Check
            elif any(e['evidence'] == 'stale_no_followup' for e in candidate.events):
                candidate.status, candidate.reason_code, candidate.next_action = "ESCALATED", "STALE_STATE", "HUMAN_REVIEW"
                candidate.priority = 1
                
            # Rule 6: Proceed normally
            else:
                has_been_screened = any(e['type'] == 'technical_screen_sent' for e in candidate.events)
                if has_been_screened:
                    candidate.status, candidate.reason_code, candidate.next_action = "IN_PROGRESS", "AWAITING_CANDIDATE", "WAIT_FOR_RESULTS"
                    candidate.priority = 3
                else:
                    candidate.status, candidate.reason_code, candidate.next_action = "READY", "PACKET_COMPLETE", "SEND_TECHNICAL_SCREEN"
                    candidate.priority = 2

            queue.append(candidate)

        # Sort by priority (1 is highest), then by application_id for deterministic ordering
        return sorted(queue, key=lambda x: (x.priority, x.application_id))

    # --- 4. IDEMPOTENT WORKER ---
    def process_queue_idempotent(self):
        """Worker command that can run repeatedly without corrupting state."""
        self.normalize_state()
        queue = self.build_action_queue()
        
        results = []
        for candidate in queue:
            # Idempotency Key: Application ID + The Action to be taken
            idem_key = f"{candidate.application_id}_{candidate.next_action}"
            
            if idem_key in self.processed_actions:
                results.append(f"SKIPPED (Already processed): {idem_key}")
                continue
                
            if candidate.next_action in ["ARCHIVE", "WAIT_FOR_RESULTS"]:
                # Passive actions, just record them
                self.processed_actions.add(idem_key)
                results.append(f"LOGGED: {idem_key}")
            
            elif candidate.next_action == "HUMAN_REVIEW":
                # Mock sending to a human review Slack channel / dashboard
                self.processed_actions.add(idem_key)
                results.append(f"ROUTED TO HUMAN: {idem_key} - Reason: {candidate.reason_code}")
                
            elif candidate.next_action == "SEND_TECHNICAL_SCREEN":
                # Mock sending email
                self.processed_actions.add(idem_key)
                results.append(f"ACTION TAKEN: Sent screen to {candidate.application_id}")
                
        return results
    

if __name__ == "__main__":
    import json
    
    # Load data
    with open('sample-data/applications.json') as f: apps = json.load(f)
    with open('sample-data/events.json') as f: events = json.load(f)
    with open('sample-data/school_routes.json') as f: routes = json.load(f)
    
    # Initialize and run
    service = PipelineService(apps, events, routes)
    print("--- FIRST RUN ---")
    for log in service.process_queue_idempotent():
        print(log)
        
    print("\n--- SECOND RUN (Testing Idempotency) ---")
    for log in service.process_queue_idempotent():
        print(log)