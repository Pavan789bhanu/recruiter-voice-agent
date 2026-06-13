# Contributing to Recruiter Voice Agent

## Branch Strategy

```
main (production)
 └── dev (integration / staging)
      └── feature/your-feature-name
      └── fix/short-description
      └── hotfix/critical-fix  (branches from main)
```

### Rules

- **Never commit directly to `main` or `dev`** — always use a PR
- `feature/*` branches → PR to `dev`
- `hotfix/*` branches → PR to `main` AND back-merge into `dev`
- All PRs require at least 1 approving review
- All CI checks must pass before merge

## Development Workflow

```bash
# 1. Start from dev
git checkout dev
git pull origin dev

# 2. Create your feature branch
git checkout -b feature/add-voice-cloning

# 3. Make changes, commit often
git add .
git commit -m "feat: add ElevenLabs voice cloning endpoint"

# 4. Push and open PR to dev
git push origin feature/add-voice-cloning
# Open PR on GitHub: base=dev, compare=feature/add-voice-cloning
```

## Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short description>

[optional body]
[optional footer]
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`, `perf`

Examples:
```
feat: add real-time caller classification API
fix: handle Deepgram websocket reconnect on timeout
docs: update AWS deployment steps for EC2 t3.small
test: add unit tests for human_ai_detector scoring
ci: add Docker build check to PR workflow
```

## PR Checklist

Before opening a PR, verify:
- [ ] Tests pass locally: `pytest tests/`
- [ ] Linting passes: `ruff check backend/`
- [ ] No secrets or `.env` files committed
- [ ] `resume_context.md` is NOT committed (it's in `.gitignore`)
- [ ] PR description filled out using the template

## Running Tests Locally

```bash
cd backend
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov ruff

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=term-missing

# Lint
ruff check .
```

## Security

- Never commit API keys, `.env`, `.pem` files, or `resume_context.md`
- If you accidentally commit a secret, rotate it immediately
- All secrets go in GitHub Secrets (Settings → Secrets → Actions)

## GitHub Actions Secrets

Add these in **Settings → Secrets and variables → Actions** to enable AWS deploy workflows:

| Secret | Purpose |
|--------|---------|
| `AWS_ACCESS_KEY_ID_DEV` | Dev IAM access key |
| `AWS_SECRET_ACCESS_KEY_DEV` | Dev IAM secret |
| `AWS_REGION` | e.g. `us-east-1` |
| `DEV_EC2_INSTANCE_ID` | Dev EC2 instance ID |
| `DEV_PUBLIC_URL` | Dev health-check URL |
| `ECR_REGISTRY` | ECR registry URL |
| `AWS_ACCESS_KEY_ID_PROD` | Prod IAM access key |
| `AWS_SECRET_ACCESS_KEY_PROD` | Prod IAM secret |
| `PROD_EC2_INSTANCE_ID` | Prod EC2 instance ID |
| `PROD_PUBLIC_URL` | Prod health-check URL |

Create **Environments** named `dev` (auto-deploy) and `production` (requires approval).
Deploy workflows skip gracefully until these secrets are configured.
