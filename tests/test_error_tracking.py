"""Error reports must never carry a secret or the visitor's IP address.

Sentry's default header filter only knows generic names, and with local
variables on it sends the database password from inside asyncpg's frames when a
connection fails. This test drives the real app into two database failures with
Sentry on and an in-memory transport, so nothing is sent anywhere. It runs in a
subprocess because the SDK's state is process-wide.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from app.core.error_tracking import scrub_event
from app.db.session import engine

DB_PASSWORD = "db-password-for-the-test"
ORIGIN_SECRET = "o" * 32
ADMIN_KEY = "admin-key-for-the-test"
CLIENT_IP = "203.0.113.77"
REQUEST_ID = "railway-request-id-for-the-test"

# A request as it arrives through Cloudflare, on an admin tool's behalf.
HEADERS = {
    "X-Origin-Auth": ORIGIN_SECRET,
    "X-Admin-Key": ADMIN_KEY,
    "CF-Connecting-IP": CLIENT_IP,
    "X-Railway-Request-Id": REQUEST_ID,
}

PROBE = """
import json, os
import sentry_sdk
from sentry_sdk.transport import Transport

payloads = []

class MemoryTransport(Transport):
    def capture_envelope(self, envelope):
        payloads.extend(item.payload.json for item in envelope.items if item.payload.json)

real_init = sentry_sdk.init
sentry_sdk.init = lambda **options: real_init(transport=MemoryTransport, **options)

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)
headers = json.loads(os.environ["PROBE_HEADERS"])
statuses = [
    client.get(path, headers=headers).status_code
    for path in ("/api/v1/categories", "/api/v1/ready")
]
sentry_sdk.flush()
print(json.dumps({"statuses": statuses, "payloads": payloads}))
"""


def test_database_failures_are_reported_without_secrets():
    env = {
        **os.environ,
        "SENTRY_DSN": "https://public@sentry.example.invalid/1",
        # Nothing listens on port 1, so every query fails to connect.
        "DATABASE_URL": f"postgresql+asyncpg://lambda:{DB_PASSWORD}@127.0.0.1:1/lambda",
        "ORIGIN_SECRET": ORIGIN_SECRET,
        "PROBE_HEADERS": json.dumps(HEADERS),
    }
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True,
        text=True,
        env=env,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    events = [payload for payload in report["payloads"] if "exception" in payload]
    sent = json.dumps(report["payloads"])

    assert report["statuses"] == [500, 503]
    assert len(events) == 2
    for secret in (DB_PASSWORD, ORIGIN_SECRET, ADMIN_KEY, CLIENT_IP):
        assert secret not in sent
    for event in events:
        assert event["tags"]["railway_request_id"] == REQUEST_ID
        assert set(event["request"]["headers"]) <= {"user-agent"}


def test_database_errors_leave_out_bound_parameters():
    # A failed insert would otherwise put the visitor's feedback text into the
    # exception message, which Sentry sends as the error's value.
    assert engine.sync_engine.hide_parameters


def test_constraint_violation_detail_is_not_sent():
    # For a CHECK or NOT NULL violation the asyncpg adapter's error carries
    # Postgres's DETAIL, the whole failing row, as its message.
    event = {
        "exception": {
            "values": [
                {"module": "asyncpg.exceptions", "value": "violates check constraint"},
                {
                    "module": "sqlalchemy.dialects.postgresql.asyncpg",
                    "value": "Failing row contains (drifted, typed feedback words).",
                },
            ]
        }
    }

    values = scrub_event(event, {})["exception"]["values"]

    assert "typed feedback words" not in json.dumps(values)
    assert values[0]["value"] == "violates check constraint"
