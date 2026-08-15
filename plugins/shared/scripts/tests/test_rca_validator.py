#!/usr/bin/env python3
"""Regression tests for validate-rca-output.py hook detection.

Zero-dependency (stdlib unittest + subprocess + tempfile). Run with:

    python3 plugins/shared/scripts/tests/test_rca_validator.py

The script is invoked as a subprocess with a synthetic JSON payload piped to
stdin — exactly how Claude Code calls the Stop / SubagentStop hooks. A blocked
turn is signalled by a ``{"decision": "block", ...}`` object on stdout; a no-op
is empty stdout. The script always exits 0 (a non-zero exit would fail the hook,
not block it), so every case asserts exit code 0 as well.

Guards against the shape-detection regression where a main-agent Stop payload
(which also carries ``last_assistant_message``) was validated as RCA output and
blocked every ordinary turn.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "validate-rca-output.py"


def run_hook(payload, extra_env=None):
    """Pipe *payload* (a dict) to the hook script; return (exit_code, stdout)."""
    env = dict(os.environ)
    # Ensure the RCA session gate is off unless a test opts in.
    env.pop("CI_DOCTOR_RCA_SESSION", None)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stdout


def blocked(stdout):
    """True if the hook emitted a block decision."""
    stdout = stdout.strip()
    if not stdout:
        return False
    try:
        return json.loads(stdout).get("decision") == "block"
    except json.JSONDecodeError:
        return False


def valid_rca_entry(evidence_path):
    """A minimal RCA entry that passes validate_message.

    stack_layer is 'deploy phase' so the empty-scenarios/'test' rule does not
    apply; the single causal_chain link cites line 1 of *evidence_path*.
    """
    return {
        "severity": 3,
        "stack_layer": "deploy phase",
        "step_name": "ipi-install",
        "error_signature": "install timed out",
        "root_cause": "cluster operators never went available",
        "raw_error": "timed out waiting for the condition",
        "infrastructure_failure": False,
        "job_url": "https://prow.example/job/123",
        "job_name": "periodic-ci-example",
        "release": "4.20",
        "remediation": "retry the install",
        "finished": "2026-08-13T00:00:00Z",
        "confidence": "high",
        "analysis_gaps": [],
        "scenarios": [],
        "causal_chain": [
            {
                "cause": "install timed out",
                "evidence": f"{evidence_path}:1",
                "quote": "timed out waiting for the condition",
            }
        ],
    }


class HookDetectionTests(unittest.TestCase):
    def test_stop_without_env_is_noop(self):
        """Bug regression: main-agent Stop with no RCA session must not block."""
        code, out = run_hook(
            {"hook_event_name": "Stop", "last_assistant_message": "some prose"}
        )
        self.assertEqual(code, 0)
        self.assertFalse(blocked(out), f"unexpected block: {out!r}")
        self.assertEqual(out.strip(), "")

    def test_subagentstop_invalid_blocks(self):
        """SubagentStop with non-JSON output must still block."""
        code, out = run_hook(
            {"hook_event_name": "SubagentStop", "last_assistant_message": "not json"}
        )
        self.assertEqual(code, 0)
        self.assertTrue(blocked(out), f"expected block, got: {out!r}")

    def test_unknown_event_fails_safe(self):
        """Absent hook_event_name must skip (pre-fix this blocked via shape)."""
        code, out = run_hook({"last_assistant_message": "not json"})
        self.assertEqual(code, 0)
        self.assertFalse(blocked(out), f"unexpected block: {out!r}")

    def test_subagentstop_valid_passes(self):
        """A well-formed one-entry RCA array must not block."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write("timed out waiting for the condition\n")
            evidence_path = f.name
        try:
            payload = {
                "hook_event_name": "SubagentStop",
                "last_assistant_message": json.dumps([valid_rca_entry(evidence_path)]),
            }
            code, out = run_hook(payload)
            self.assertEqual(code, 0)
            self.assertFalse(blocked(out), f"unexpected block: {out!r}")
        finally:
            os.unlink(evidence_path)

    def test_stop_env_gated_transcript_blocks(self):
        """Stop with CI_DOCTOR_RCA_SESSION set validates the transcript message."""
        record = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "not json"}]},
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            f.write(json.dumps(record) + "\n")
            transcript_path = f.name
        try:
            payload = {
                "hook_event_name": "Stop",
                "transcript_path": transcript_path,
            }
            code, out = run_hook(payload, extra_env={"CI_DOCTOR_RCA_SESSION": "1"})
            self.assertEqual(code, 0)
            self.assertTrue(blocked(out), f"expected block, got: {out!r}")
        finally:
            os.unlink(transcript_path)


if __name__ == "__main__":
    unittest.main()
