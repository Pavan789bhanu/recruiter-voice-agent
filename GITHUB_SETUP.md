# GitHub Repository Setup Guide

## Recommended Repo Name
```
recruiter-voice-agent
```
Full URL: `https://github.com/Pavan789bhanu/recruiter-voice-agent`

---

## Step 1: Create the GitHub Repo

1. Go to github.com → New repository
2. Repository name: `recruiter-voice-agent`
3. Description: `AI-powered voice agent that answers recruiter calls using your resume as context`
4. Visibility: **Private** (your resume_context.md stays off it — but keep it private anyway)
5. Do NOT initialize with README (we're pushing existing files)
6. Create repository

---

## Step 2: Push This Project to GitHub

Run these commands from the `ai-recruiter-agent/` folder on your Mac:

```bash
cd /path/to/ai-recruiter-agent

# Initialize git
git init
git add .
git commit -m "feat: initial project — AI recruiter voice agent"

# Connect to GitHub
git remote add origin https://github.com/Pavan789bhanu/recruiter-voice-agent.git

# Push main branch
git branch -M main
git push -u origin main

# Create and push dev branch
git checkout -b dev
git push -u origin dev
```

---

## Step 3: Configure Branch Protection Rules

Go to: GitHub repo → Settings → Branches → Add rule

### Protect `main`:
- Branch name pattern: `main`
- ✅ Require a pull request before merging
  - ✅ Require approvals: **1**
  - ✅ Dismiss stale pull request approvals when new commits are pushed
- ✅ Require status checks to pass before merging
  - Add these required checks:
    - `Secret Scan`
    - `Lint (Ruff)`
    - `Unit Tests (Python 3.12)`
    - `Security Scan (Bandit)`
    - `Docker Build Check`
- ✅ Require branches to be up to date before merging
- ✅ Restrict pushes that create files — **block direct pushes**
- ✅ Do not allow bypassing the above settings

### Protect `dev`:
- Branch name pattern: `dev`
- ✅ Require a pull request before merging
  - ✅ Require approvals: **1**
- ✅ Require status checks to pass before merging
  - Add the same required checks as main
- ✅ Require branches to be up to date before merging

---

## Step 4: Add GitHub Secrets

Go to: Settings → Secrets and variables → Actions → New repository secret

Add all of these:

### AWS (Dev environment)
| Secret Name | Value |
|-------------|-------|
| `AWS_ACCESS_KEY_ID_DEV` | Your dev IAM key |
| `AWS_SECRET_ACCESS_KEY_DEV` | Your dev IAM secret |
| `AWS_REGION` | e.g. `us-east-1` |
| `DEV_EC2_INSTANCE_ID` | e.g. `i-0123456789abcdef0` |
| `DEV_PUBLIC_URL` | e.g. `https://dev.yourserver.com` |
| `ECR_REGISTRY` | e.g. `123456789.dkr.ecr.us-east-1.amazonaws.com` |

### AWS (Production environment)
| Secret Name | Value |
|-------------|-------|
| `AWS_ACCESS_KEY_ID_PROD` | Your prod IAM key |
| `AWS_SECRET_ACCESS_KEY_PROD` | Your prod IAM secret |
| `PROD_EC2_INSTANCE_ID` | e.g. `i-abcdef1234567890` |
| `PROD_PUBLIC_URL` | e.g. `https://yourserver.com` |

---

## Step 5: Set Up GitHub Environments

Go to: Settings → Environments → New environment

### Create `dev` environment:
- Name: `dev`
- No approval required (auto-deploys on merge to dev)

### Create `production` environment:
- Name: `production`
- ✅ Required reviewers: add yourself
- ✅ Wait timer: 0 minutes (or 5 if you want a buffer)
- This means prod deploys pause for your manual approval

---

## Step 6: Verify CI is Working

### Test the PR workflow:
```bash
# On your local machine
git checkout dev
git checkout -b feature/test-ci
echo "# test" >> README.md
git add . && git commit -m "test: verify CI pipeline"
git push origin feature/test-ci
```
Open a PR from `feature/test-ci` → `dev` on GitHub.
You should see all 6 checks run automatically.

### Expected checks to appear:
- ✅ Secret Scan
- ✅ Lint (Ruff)
- ✅ Unit Tests (Python 3.12)
- ✅ Type Check (Pyright)
- ✅ Security Scan (Bandit)
- ✅ Docker Build Check
- ✅ PR Checks Summary

---

## Workflow Summary

```
Developer workflow:
──────────────────
git checkout dev && git pull origin dev
git checkout -b feature/my-feature
[make changes]
git push origin feature/my-feature

Open PR: feature/my-feature → dev
  ↓ GitHub Actions: pr-checks.yml runs all 6 gates
  ↓ Code review (1 approval required)
  ↓ Merge → triggers deploy-dev.yml → auto-deploys to staging

Open PR: dev → main  (when ready for production)
  ↓ pr-checks.yml runs again
  ↓ Code review + production environment approval
  ↓ Merge → triggers deploy-prod.yml → deploys to production + creates release
```

---

## IAM Permissions Needed

The GitHub Actions IAM user needs these AWS permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:GetRepositoryPolicy",
        "ecr:DescribeRepositories",
        "ecr:BatchGetImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ssm:SendCommand",
        "ssm:GetCommandInvocation"
      ],
      "Resource": "*"
    }
  ]
}
```

Create this as an IAM policy, attach it to a dedicated `github-actions` IAM user, generate access keys, and add them as GitHub secrets above.
