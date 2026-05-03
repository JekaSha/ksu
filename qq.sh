#!/usr/bin/env bash
set -u
set -o pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: not inside a git repository."
  exit 1
fi

commit_message="${1:-fixed small bags}"

run_game() {
  python python/ksusha_walk.py
}

setup_env_after_pull() {
  if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
  else
    echo "Warning: .venv/bin/activate not found. Using system Python."
  fi

  if [[ -f "requirements.txt" ]]; then
    pip install -r requirements.txt
  else
    echo "Warning: requirements.txt not found. Skipping dependency install."
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
