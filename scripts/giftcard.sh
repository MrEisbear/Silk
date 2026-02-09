#!/bin/bash
if [ -f "/home/SilkC/.venv/bin/activate" ]; then
    source /home/SilkC/.venv/bin/activate
fi
PYTHON_BIN="/home/SilkC/.venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi
$PYTHON_BIN /home/SilkC/scripts/issue_giftcard.py "$@"
