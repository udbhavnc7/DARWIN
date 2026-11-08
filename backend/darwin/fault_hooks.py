"""Synchronization hook enabled only in an explicitly isolated fault sandbox."""
import json
import os
from pathlib import Path
import time


def pause_acknowledgment(control, key):
    path = Path(control)
    if not path.exists() or path.read_text() != key:
        return
    path.with_suffix('.reached.json').write_text(json.dumps({
        'key': key, 'pid': os.getpid(), 'instance': os.environ.get('DARWIN_INSTANCE_ID')}))
    while path.exists():
        time.sleep(.05)
