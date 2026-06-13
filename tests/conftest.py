"""Pytest configuration and shared fixtures."""
import os

# Set dummy env vars so config.py doesn't raise on import during tests
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_auth_token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15005550006")
os.environ.setdefault("DEEPGRAM_API_KEY", "test_deepgram_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test000000")
os.environ.setdefault("ELEVENLABS_API_KEY", "test_elevenlabs_key")
os.environ.setdefault("PUBLIC_URL", "https://test.example.com")
os.environ.setdefault("FORWARD_TO_NUMBER", "+15005550007")
