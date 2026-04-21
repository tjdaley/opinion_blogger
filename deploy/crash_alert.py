"""Send a crash-alert SMS. Invoked by systemd OnFailure= on opinion-blogger.service.

Runs as its own short-lived process, so the main pipeline having already exited is fine.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import notifier

notifier.send("ALERT: opinion-blogger run failed. Check: journalctl -u opinion-blogger -n 200")
