# Contributing to Recruiter Voice Agent

Thank you for your interest in contributing! This project uses a **maintainer-only** workflow for production branches and an open **`public`** branch for community contributions.

---

## Branch overview

```
main (production)          ← maintainer-only, locked
 └── dev (integration)     ← maintainer-only, locked
      └── public            ← open for community PRs ✓
           └── feature/your-feature-name
```

| Branch | Who can open PRs? | Purpose |
|--------|-------------------|---------|
| `public` | **Everyone** (forks welcome) | Community contributions — review & merge here |
| `dev` | **Maintainers only** | Integration / staging — fork PRs are auto-closed |
| `main` | **Maintainers only** | Production — fork PRs are auto-closed |

> **Important:** Do **not** open pull requests targeting `main` or `dev`. They will be automatically closed. Always target **`public`**.

---

## For contributors (external)

### 1. Fork and clone

```bash
git clone https://github.com/YOUR_USERNAME/recruiter-voice-agent.git
cd recruiter-voice-agent
git remote add upstream https://github.com/Pavan789bhanu/recruiter-voice-agent.git
```

### 2. Branch from `public`

```bash
git fetch upstream
git checkout -b feature/my-improvement upstream/public
```

### 3. Make changes and test

```bash
cd backend
pip install -r requirements.txt
pip install pytest ruff
pytest ../tests/ -v
ruff check .
```

### 4. Open a PR to `public`

```bash
git push origin feature/my-improvement
```

On GitHub, open a pull request with:
- **Base branch:** `public`
- **Compare branch:** your `feature/my-improvement`

All CI checks must pass before a maintainer can merge.

### What happens after merge?

Maintainers review accepted changes on `public` and periodically promote them into `dev` → `main` for deployment. You do not need access to those branches.

---

## For maintainers (internal)

```bash
git checkout dev
git pull origin dev

# Promote reviewed public changes into dev
git merge origin/public
git push origin dev

# When ready for production
# Open PR: dev → main
```

Never commit API keys, `.env`, or `resume_context.md`.

---

## Commit message format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add real-time caller classification API
fix: handle Deepgram websocket reconnect on timeout
docs: update AWS deployment steps
test: add unit tests for human_ai_detector scoring
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`, `perf`

---

## PR checklist

Before opening a PR to `public`, verify:

- [ ] Tests pass locally: `pytest tests/ -v`
- [ ] Lint passes: `ruff check backend/ tests/`
- [ ] No secrets, `.env`, or `resume_context.md` committed
- [ ] PR targets **`public`** (not `main` or `dev`)
- [ ] PR description filled out using the template

---

## Security

- Never commit API keys, `.env`, `.pem` files, or personal resume data
- If you accidentally commit a secret, rotate it immediately and notify a maintainer
