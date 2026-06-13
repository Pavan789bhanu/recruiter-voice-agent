"""
Tests for CallSession and AI engine session management.

These tests mock the Anthropic client so no real API calls are made.
Run: pytest tests/test_ai_engine.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from unittest.mock import patch, MagicMock


class TestCallSession:

    def _make_session(self, call_sid="test-call-123"):
        """Create a CallSession with mocked Anthropic client."""
        with patch("ai_engine.client") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="I have 3+ years of experience in ML and AI.")]
            mock_client.messages.create.return_value = mock_response

            from ai_engine import CallSession
            session = CallSession(call_sid)
            return session, mock_client

    def test_session_created_with_correct_sid(self):
        session, _ = self._make_session("call-abc-123")
        assert session.call_sid == "call-abc-123"

    def test_initial_turn_count_is_zero(self):
        session, _ = self._make_session()
        assert session.turn_count == 0

    def test_add_recruiter_appends_user_message(self):
        session, _ = self._make_session()
        session.add_recruiter("Tell me about yourself.")
        assert len(session.history) == 1
        assert session.history[0]["role"] == "user"
        assert session.history[0]["content"] == "Tell me about yourself."

    def test_add_candidate_appends_assistant_message(self):
        session, _ = self._make_session()
        session.add_candidate("I'm a Data Scientist with 3 years of experience.")
        assert session.history[0]["role"] == "assistant"

    def test_turn_count_increments_on_candidate_response(self):
        session, _ = self._make_session()
        session.add_candidate("Response 1")
        session.add_candidate("Response 2")
        assert session.turn_count == 2

    def test_generate_response_calls_claude(self):
        from ai_engine import CallSession
        with patch("ai_engine.client") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="My experience is in financial ML.")]
            mock_client.messages.create.return_value = mock_response

            session = CallSession("test-sid")
            session.add_recruiter("What's your background?")
            result = session.generate_response()

            assert mock_client.messages.create.called
            assert result == "My experience is in financial ML."

    def test_generate_response_increments_turn_count(self):
        from ai_engine import CallSession
        with patch("ai_engine.client") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Answer.")]
            mock_client.messages.create.return_value = mock_response

            session = CallSession("test-sid")
            session.add_recruiter("Question?")
            session.generate_response()
            assert session.turn_count == 1

    def test_get_transcript_excludes_system_messages(self):
        from ai_engine import CallSession
        session = CallSession("test-sid")
        session.add_recruiter("Tell me about yourself.")
        session.add_candidate("I'm Pavan, a Data Scientist.")
        transcript = session.get_transcript()
        assert len(transcript) == 2
        assert transcript[0]["role"] == "Recruiter"
        assert transcript[1]["role"] == "Candidate (AI)"

    def test_error_handling_returns_fallback_message(self):
        from ai_engine import CallSession
        with patch("ai_engine.client") as mock_client:
            mock_client.messages.create.side_effect = Exception("API error")
            session = CallSession("test-sid")
            session.add_recruiter("Question?")
            result = session.generate_response()
            assert "technical issue" in result.lower() or "repeat" in result.lower()


class TestSessionRegistry:

    def test_get_or_create_returns_same_session(self):
        from ai_engine import get_or_create_session, _sessions
        _sessions.clear()
        s1 = get_or_create_session("call-xyz")
        s2 = get_or_create_session("call-xyz")
        assert s1 is s2

    def test_close_session_removes_from_registry(self):
        from ai_engine import get_or_create_session, close_session, _sessions
        _sessions.clear()
        get_or_create_session("call-to-close")
        assert "call-to-close" in _sessions
        close_session("call-to-close")
        assert "call-to-close" not in _sessions

    def test_close_nonexistent_session_returns_empty(self):
        from ai_engine import close_session
        result = close_session("nonexistent-call-999")
        assert result == []
