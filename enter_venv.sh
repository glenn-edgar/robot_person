#!/usr/bin/env bash
# Activate the robot_person Python venv.
#
# Usage:  source enter_venv.sh   (must be sourced, not executed)
#
# After sourcing you have:
#   python   → .venv/bin/python3
#   pytest   → .venv/bin/pytest
#   pip      → .venv/bin/pip

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "enter_venv.sh: must be sourced, not executed." >&2
    echo "  source enter_venv.sh" >&2
    exit 1
fi

_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_venv="${_here}/.venv"

if [[ ! -f "${_venv}/bin/activate" ]]; then
    echo "enter_venv.sh: venv missing at ${_venv}" >&2
    echo "  run: python3 -m venv ${_venv} && ${_venv}/bin/pip install pytest" >&2
    return 1
fi

# shellcheck disable=SC1091
source "${_venv}/bin/activate"
export PYTHONPATH="${_here}/s_engine${PYTHONPATH:+:${PYTHONPATH}}"

echo "robot_person venv active — python=$(python --version 2>&1), pytest=$(pytest --version 2>&1 | head -1)"
