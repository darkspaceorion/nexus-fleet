"""Ping my phone: python notify.py "R-004 ready for review" [--title NEXUS] [--urgent]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fleet_lib import notify  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("message")
ap.add_argument("--title", default="NEXUS")
ap.add_argument("--urgent", action="store_true")
a = ap.parse_args()
ok = notify(a.message, a.title, "high" if a.urgent else "default")
print("sent" if ok else "NOT sent (no NTFY_TOPIC or no network)")
sys.exit(0 if ok else 1)
