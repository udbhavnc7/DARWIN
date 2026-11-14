"""Synchronization hook enabled only in an explicitly isolated fault sandbox."""
import json
import os
from pathlib import Path
import time


def pause_acknowledgment(control, key):
    path = Path(control)
    if not path.exists() or path.read_text() != key:
        return
    temporary = path.with_suffix('.writing')
    temporary.write_text(json.dumps({
        'key': key, 'pid': os.getpid(), 'instance': os.environ.get('DARWIN_INSTANCE_ID')}))
    temporary.replace(path.with_suffix('.reached.json'))
    while path.exists():
        time.sleep(.05)
