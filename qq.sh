#!/usr/bin/env bash
set -u
set -o pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! git -C "$script_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: qq.sh is not inside a git repository."
  exit 1
fi

repo_root="$(git -C "$script_dir" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$repo_root" ]]; then
  echo "Error: failed to detect repository root."
  exit 1
fi

cd "$repo_root" || exit 1

commit_message="${1:-fixed small bags}"
python_cmd=""

detect_python_cmd() {
  local candidates=()
  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    candidates+=("$VIRTUAL_ENV/bin/python")
    candidates+=("$VIRTUAL_ENV/Scripts/python.exe")
    candidates+=("$VIRTUAL_ENV/Scripts/python")
  fi
  candidates+=(
    ".venv/bin/python"
    ".venv/Scripts/python.exe"
    ".venv/Scripts/python"
    "venv/bin/python"
    "venv/Scripts/python.exe"
    "venv/Scripts/python"
    "env/bin/python"
    "env/Scripts/python.exe"
    "env/Scripts/python"
  )

  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      python_cmd="$candidate"
      return 0
    fi
  done

  if command -v python3.13 >/dev/null 2>&1; then
    python_cmd="python3.13"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    python_cmd="python3"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    python_cmd="python"
    return 0
  fi
  return 1
}

run_game() {
  if [[ -z "$python_cmd" ]]; then
    if ! detect_python_cmd; then
      echo "Error: Python interpreter not found."
      return 1
    fi
  fi
  "$python_cmd" python/ksusha_walk.py
}

setup_env_after_pull() {
  local activated=0
  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    echo "Using active virtualenv: ${VIRTUAL_ENV}"
    activated=1
  elif [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
    activated=1
  elif [[ -f ".venv/Scripts/activate" ]]; then
    # shellcheck disable=SC1091
    source ".venv/Scripts/activate"
    activated=1
  elif [[ -f "venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "venv/bin/activate"
    activated=1
  elif [[ -f "venv/Scripts/activate" ]]; then
    # shellcheck disable=SC1091
    source "venv/Scripts/activate"
    activated=1
  elif [[ -f "env/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "env/bin/activate"
    activated=1
  elif [[ -f "env/Scripts/activate" ]]; then
    # shellcheck disable=SC1091
    source "env/Scripts/activate"
    activated=1
  fi

  if [[ "$activated" -eq 0 ]]; then
    echo "Warning: venv not found (.venv/venv/env). Using detected Python."
  fi

  if ! detect_python_cmd; then
    echo "Error: Python interpreter not found."
    return 1
  fi
  echo "Using Python: $python_cmd"

  local requirements_file=""
  if [[ -f "python/requirements.txt" ]]; then
    requirements_file="python/requirements.txt"
  elif [[ -f "requirements.txt" ]]; then
    requirements_file="requirements.txt"
  fi

  if [[ -n "$requirements_file" ]]; then
    "$python_cmd" -m pip install -r "$requirements_file"
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
  if ! git push; then
    echo "Push rejected. Running git pull --rebase and retry push..."
    git pull --rebase && git push
  fi
fi

run_game
