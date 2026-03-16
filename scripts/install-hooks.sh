#!/usr/bin/env bash
# scripts/install-hooks.sh
#
# Installs the dg-form pre-commit hook into the local .git/hooks directory.
# Run this once after cloning the repository:
#
#   bash scripts/install-hooks.sh
#
# NOTE: .git/hooks/ is NOT committed to the repo, so every contributor must
# run this script once on their own clone.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK_SRC="${REPO_ROOT}/scripts/pre-commit.sh"
HOOKS_DIR="${REPO_ROOT}/.git/hooks"
HOOK_DEST="${HOOKS_DIR}/pre-commit"

# Ensure we are inside a git repository
if [ ! -d "${HOOKS_DIR}" ]; then
  echo "❌ .git/hooks directory not found. Are you inside a git repository?"
  exit 1
fi

# Copy the script (a copy rather than a symlink works on Windows Git Bash too)
cp "${HOOK_SRC}" "${HOOK_DEST}"
chmod +x "${HOOK_DEST}"

echo "✅ pre-commit hook installed."
echo "   Hook path : ${HOOK_DEST}"
echo "   Source    : ${HOOK_SRC}"
