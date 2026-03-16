#!/usr/bin/env bash
# scripts/pre-commit.sh
#
# Pre-commit hook for dg-form.
# Runs backend (Python/pytest) and frontend (npm/vitest) test suites with
# coverage checks before allowing a commit to proceed.
#
# Install once after cloning:
#   bash scripts/install-hooks.sh
#
# NOTE: We intentionally do NOT use `set -e` globally so that we can print
# a clear failure message before exiting with code 1.

REPO_ROOT="$(git rev-parse --show-toplevel)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
print_header() {
  echo ""
  echo "=================================================="
  echo "  $1"
  echo "=================================================="
}

# ---------------------------------------------------------------------------
# Resolve Python interpreter
# Prefer a project virtualenv if present, then fall back to python3/python.
# ---------------------------------------------------------------------------
resolve_python() {
  local venv_python="${REPO_ROOT}/api/.venv/bin/python"
  # Git Bash on Windows uses Scripts/ instead of bin/
  local venv_python_win="${REPO_ROOT}/api/.venv/Scripts/python"

  if [ -x "${venv_python}" ]; then
    echo "${venv_python}"
  elif [ -x "${venv_python_win}" ]; then
    echo "${venv_python_win}"
  elif command -v python3 &>/dev/null; then
    echo "python3"
  elif command -v python &>/dev/null; then
    echo "python"
  else
    echo ""
  fi
}

# ---------------------------------------------------------------------------
# 1. Backend tests
# ---------------------------------------------------------------------------
print_header "Backend tests (pytest + coverage)"

PYTHON="$(resolve_python)"

if [ -z "${PYTHON}" ]; then
  echo "⚠️  WARNING: No Python interpreter found."
  echo "   Create a virtualenv at api/.venv or install Python in your PATH."
  echo "❌ Backend tests failed. Commit blocked."
  exit 1
fi

echo "Using Python: ${PYTHON}"
echo "Running: python -m pytest --tb=short -q  (coverage threshold enforced by pytest.ini)"
echo ""

cd "${REPO_ROOT}/api"
"${PYTHON}" -m pytest --tb=short -q
BACKEND_EXIT=$?

if [ ${BACKEND_EXIT} -ne 0 ]; then
  echo ""
  echo "❌ Backend tests failed. Commit blocked."
  exit 1
fi

echo ""
echo "✅ Backend tests passed."

# ---------------------------------------------------------------------------
# 2. Frontend tests
# ---------------------------------------------------------------------------
print_header "Frontend tests (npm run test:coverage)"

cd "${REPO_ROOT}/web"

# Ensure node_modules are present
if [ ! -d "node_modules" ]; then
  echo "⚠️  node_modules not found. Running npm install first..."
  npm install --silent
  if [ $? -ne 0 ]; then
    echo "❌ npm install failed. Commit blocked."
    exit 1
  fi
fi

echo "Running: npm run test:coverage"
echo ""

npm run test:coverage
FRONTEND_EXIT=$?

if [ ${FRONTEND_EXIT} -ne 0 ]; then
  echo ""
  echo "❌ Frontend tests failed. Commit blocked."
  exit 1
fi

echo ""
echo "✅ Frontend tests passed."

# ---------------------------------------------------------------------------
# All checks passed
# ---------------------------------------------------------------------------
echo ""
echo "=================================================="
echo "✅ All tests passed. Proceeding with commit."
echo "=================================================="
echo ""
