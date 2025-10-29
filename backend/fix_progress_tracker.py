"""
Fix Progress Tracker
Tracks the progress of PDF fixes in real-time and provides step-by-step updates
"""

import time
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

class FixProgressTracker:
    """Tracks progress of PDF fixes with detailed step-by-step updates"""
    
    def __init__(self, scan_id: str, total_steps: int = 10):
        self.scan_id = scan_id
        self.total_steps = total_steps
        self.current_step = 0
        self.steps = []
        self.start_time = datetime.now()
        self.status = 'initializing'  # initializing, in_progress, completed, failed
        self.error = None
        
    def add_step(self, step_name: str, description: str, status: str = 'pending'):
        """Add a new step to track"""
        step = {
            'id': len(self.steps) + 1,
            'name': step_name,
            'description': description,
            'status': status,  # pending, in_progress, completed, failed, skipped
            'startTime': None,
            'endTime': None,
            'duration': None,
            'details': None,
            'error': None
        }
        self.steps.append(step)
        return step['id']
    
    def start_step(self, step_id: int):
        """Mark a step as started"""
        if 0 < step_id <= len(self.steps):
            step = self.steps[step_id - 1]
            step['status'] = 'in_progress'
            step['startTime'] = datetime.now().isoformat()
            self.current_step = step_id
            self.status = 'in_progress'
            print(f"[ProgressTracker] Step {step_id}/{self.total_steps}: {step['name']} - STARTED")
    
    def complete_step(self, step_id: int, details: Optional[str] = None):
        """Mark a step as completed"""
        if 0 < step_id <= len(self.steps):
            step = self.steps[step_id - 1]
            step['status'] = 'completed'
            step['endTime'] = datetime.now().isoformat()
            if step['startTime']:
                start = datetime.fromisoformat(step['startTime'])
                end = datetime.fromisoformat(step['endTime'])
                step['duration'] = (end - start).total_seconds()
            if details:
                step['details'] = details
            print(f"[ProgressTracker] Step {step_id}/{self.total_steps}: {step['name']} - COMPLETED ({step.get('duration', 0):.2f}s)")
    
    def fail_step(self, step_id: int, error: str):
        """Mark a step as failed"""
        if 0 < step_id <= len(self.steps):
            step = self.steps[step_id - 1]
            step['status'] = 'failed'
            step['endTime'] = datetime.now().isoformat()
            step['error'] = error
            if step['startTime']:
                start = datetime.fromisoformat(step['startTime'])
                end = datetime.fromisoformat(step['endTime'])
                step['duration'] = (end - start).total_seconds()
            print(f"[ProgressTracker] Step {step_id}/{self.total_steps}: {step['name']} - FAILED: {error}")
    
    def skip_step(self, step_id: int, reason: str):
        """Mark a step as skipped"""
        if 0 < step_id <= len(self.steps):
            step = self.steps[step_id - 1]
            step['status'] = 'skipped'
            step['details'] = reason
            print(f"[ProgressTracker] Step {step_id}/{self.total_steps}: {step['name']} - SKIPPED: {reason}")
    
    def complete_all(self):
        """Mark the entire process as completed"""
        self.status = 'completed'
        end_time = datetime.now()
        total_duration = (end_time - self.start_time).total_seconds()
        print(f"[ProgressTracker] All steps completed in {total_duration:.2f}s")
    
    def fail_all(self, error: str):
        """Mark the entire process as failed"""
        self.status = 'failed'
        self.error = error
        print(f"[ProgressTracker] Process failed: {error}")
    
    def get_progress(self) -> Dict[str, Any]:
        """Get current progress state"""
        completed_steps = sum(1 for step in self.steps if step['status'] == 'completed')
        failed_steps = sum(1 for step in self.steps if step['status'] == 'failed')
        
        return {
            'scanId': self.scan_id,
            'status': self.status,
            'currentStep': self.current_step,
            'totalSteps': len(self.steps),
            'completedSteps': completed_steps,
            'failedSteps': failed_steps,
            'progress': int((completed_steps / len(self.steps)) * 100) if self.steps else 0,
            'steps': self.steps,
            'startTime': self.start_time.isoformat(),
            'error': self.error
        }
    
    def to_json(self) -> str:
        """Convert progress to JSON string"""
        return json.dumps(self.get_progress())


# Global progress tracker storage
_progress_trackers: Dict[str, FixProgressTracker] = {}

def create_progress_tracker(scan_id: str, total_steps: int = 10) -> FixProgressTracker:
    """Create a new progress tracker for a scan"""
    tracker = FixProgressTracker(scan_id, total_steps)
    _progress_trackers[scan_id] = tracker
    return tracker

def get_progress_tracker(scan_id: str) -> Optional[FixProgressTracker]:
    """Get an existing progress tracker"""
    return _progress_trackers.get(scan_id)

def remove_progress_tracker(scan_id: str):
    """Remove a progress tracker"""
    if scan_id in _progress_trackers:
        del _progress_trackers[scan_id]
