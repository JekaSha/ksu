#!/usr/bin/env bash
set -u
set -o pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: not inside a git repository."
  exit 1
fi

commit_message="${1:-fixed small bags}"

run_game() {
  if command -v python >/dev/null 2>&1; then
    python python/ksusha_walk.py
  else
    python3 python/ksusha_walk.py
  fi
}

setup_env_after_pull() {
  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    echo "Using active virtualenv: ${VIRTUAL_ENV}"
  elif [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
  elif [[ -f "venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "venv/bin/activate"
  elif [[ -f "env/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "env/bin/activate"
  else
    echo "Warning: venv not found (.venv/venv/env). Using system Python."
  fi

  if [[ -f "python/requirements.txt" ]]; then
    if command -v python >/dev/null 2>&1; then
      python -m pip install -r python/requirements.txt
    else
      python3 -m pip install -r python/requirements.txt
    fi
  elif [[ -f "requirements.txt" ]]; then
    if command -v python >/dev/null 2>&1; then
      python -m pip install -r requirements.txt
    else
      python3 -m pip install -r requirements.txt
    fi
  else
    echo "Warning: requirements file not found (python/requirements.txt or requirements.txt). Skipping dependency install."
  fi
}

git add .

if git diff --cached --quiet; then
  echo "No changes to commit. Running git pull..."
  git pull
  setup_env_after_pull
else
  git commit -m "$commit_message"
  git push
fi

run_game
