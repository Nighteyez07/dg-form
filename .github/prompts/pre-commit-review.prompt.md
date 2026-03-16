---
description: "Run the full pre-commit review pipeline: security scan, performance check, and UX audit on changed files, then confirm all tests pass before committing. Use this before every git commit."
---

You are about to commit changes to the dg-form repository. Before the commit is made, run the following review pipeline in order. **Do not commit until all steps pass or all findings are explicitly accepted by the user.**

## Step 1 — Identify changed files

Use `git diff --name-only HEAD` (or `git diff --cached --name-only` if files are already staged) to identify which files have changed. Pass the list to each relevant agent below.

## Step 2 — Security scan (always required)

Invoke the **dg-form Security** agent with the list of changed files. Ask it to perform:
- SAST on all changed Python and TypeScript files
- DAST review of any changed API endpoints or nginx/Docker config
- SCA check if `requirements.txt`, `requirements-dev.txt`, or `package.json` changed

**Gate**: If any CRITICAL or HIGH findings are reported, the commit is **blocked**. Present the findings to the user and require explicit confirmation or a fix before proceeding. MEDIUM and below may be noted but do not block.

## Step 3 — Performance review (if backend or video pipeline files changed)

If any files under `api/` changed, invoke the **dg-form Performance** agent.
Ask it to check for:
- Any new blocking I/O on the async event loop
- Memory allocation concerns (especially in upload/frame processing paths)
- Unnecessary re-reads of video files

**Gate**: P0 findings block the commit. P1 and P2 are noted but do not block.

## Step 4 — UX/Accessibility review (if frontend files changed)

If any files under `web/src/` changed, invoke the **dg-form UX** agent.
Ask it to check for:
- Any new interactive elements missing ARIA attributes or keyboard support
- WCAG 2.2 AA violations introduced by the change
- Mobile viewport regressions

**Gate**: WCAG 2.2 AA violations block the commit. Best-practice observations do not block.

## Step 5 — Tests (always required)

Remind the user to run the pre-commit hook before committing:
```sh
bash scripts/install-hooks.sh   # first time only
git commit ...                  # hook runs tests automatically
```

Or to run manually:
```sh
# Backend
cd api && python -m pytest

# Frontend  
cd web && npm run test:coverage
```

**Gate**: Any test failure blocks the commit.

## Step 6 — Commit

Only after all gates pass (or user explicitly accepts non-blocking findings), proceed with:
```sh
git add <files>
git commit -m "<type>(<scope>): <description>"
```

Use [Conventional Commits](https://www.conventionalcommits.org/) format for the message.
