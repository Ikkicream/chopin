#!/bin/bash
# Genesis agent runner — loads .env safely via Python then runs the script.
# Usage: bash scripts/run_agent.sh scripts/brief_agent.py [args...]

cd /home/autoblog/genesis

# Load .env via Python (handles special chars in values)
eval "$(python3 -c "
import os
for line in open('.env'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        v = v.strip(\"'\\\"\")
        # Escape for bash export
        v_escaped = v.replace(\"'\", \"'\\\"'\\\"'\")
        print(f\"export {k}='{v_escaped}'\")
")"

# Run the agent
python3 "$@"
