"""Continuous Beijing calendar-day coverage across scheduled and retry runs."""
from datetime import datetime, timedelta
import json


def load_window(root, now):
    path = root / 'state' / 'collection_cursor.json'
    cursor = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not isinstance(cursor, dict):
        raise ValueError('collection_cursor.json must be an object')
    previous = cursor.get('last_success_at')
    if previous:
        last = datetime.fromisoformat(previous)
        if last.tzinfo is None or last > now:
            raise ValueError('Invalid collection cursor timestamp')
        start = last.astimezone(now.tzinfo).date() - timedelta(days=1)
    else:
        # First deployment backfills three days, including the gap in the old window.
        start = now.date() - timedelta(days=2)
        status_path = root / 'state' / 'latest_status.json'
        status = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {}
        if status.get('window_start'):
            # Even before the first success, failed/trial attempts retain their pending coverage.
            start = min(start, datetime.fromisoformat(status['window_start']).date())
    if cursor.get('report_date') == now.date().isoformat() and cursor.get('window_start'):
        # A same-day rerun must not hide entries collected earlier that day.
        start = min(start, datetime.fromisoformat(cursor['window_start']).date())
    return start, cursor


def save_cursor(root, now, start):
    from report_store import atomic_write
    cursor = {'last_success_at': now.isoformat(), 'report_date': now.date().isoformat(),
              'window_start': start.isoformat()}
    atomic_write(root / 'state' / 'collection_cursor.json', json.dumps(cursor, indent=2) + '\n')
