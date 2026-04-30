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

git add .

if git diff --cached --quiet; then
  echo "No changes to commit. Running git pull..."
  git pull
else
  git commit -m "$commit_message"
  git push
fi

run_game

