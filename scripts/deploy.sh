#!/bin/bash
# ============================================================
# AI Recruiter Agent — AWS EC2 Deployment Script
# Run this on your EC2 instance (Ubuntu 22.04)
# ============================================================

set -e

echo "=== AI Recruiter Agent Deploy ==="

# 1. Install Docker
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | bash
    sudo usermod -aG docker ubuntu
    echo "Docker installed. Log out and back in if running as ubuntu user."
fi

# 2. Install Nginx
if ! command -v nginx &> /dev/null; then
    echo "Installing Nginx..."
    sudo apt-get update -y
    sudo apt-get install -y nginx certbot python3-certbot-nginx
fi

# 3. Pull latest code (git) or assume we're in the repo
cd /home/ubuntu/ai-recruiter-agent/backend

# 4. Build Docker image
echo "Building Docker image..."
docker build -t ai-recruiter-agent:latest .

# 5. Stop existing container (if any)
docker stop ai-recruiter-agent 2>/dev/null || true
docker rm ai-recruiter-agent 2>/dev/null || true

# 6. Start new container
echo "Starting container..."
docker run -d \
    --name ai-recruiter-agent \
    --restart unless-stopped \
    -p 8000:8000 \
    --env-file .env \
    -v /tmp/ai_recruiter_audio:/tmp/ai_recruiter_audio \
    -v /tmp/transcripts:/tmp/transcripts \
    ai-recruiter-agent:latest

echo "Container started. Checking health..."
sleep 5
curl -f http://localhost:8000/health && echo "✓ Health check passed" || echo "✗ Health check failed"

echo "=== Deploy complete ==="
