#!/usr/bin/env python3
"""
Tests for BrainClassifier.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from asthralios.brain.classifier import BrainClassifier, CONFIDENCE_THRESHOLD
from asthralios.brain.schema import ClassificationResult


class TestBrainClassifier:

    @pytest.fixture
    def config(self):
        return {'model': 'llama3.2:3b', 'provider': 'ollama'}

    @pytest.fixture
    def classifier(self, config):
        with patch('asthralios.brain.classifier.init_chat_model') as mock_init:
            mock_llm = Mock()
            mock_init.return_value = mock_llm
            c = BrainClassifier(config)
            c._mock_llm = mock_llm
            return c

    def _make_llm_response(self, content: str) -> Mock:
        resp = Mock()
        resp.content = content
        return resp

    def test_classify_valid_project(self, classifier):
        payload = {
            "category": "projects",
            "confidence": 0.92,
            "name": "Build new dashboard feature",
            "next_action": "Create initial mockups",
            "needs_clarification": False,
            "clarification_question": None,
            "payload": {
                "name": "Build new dashboard feature",
                "priority": "high",
                "summary": "Dashboard redesign project",
            },
        }
        import json
        classifier._mock_llm.invoke.return_value = self._make_llm_response(json.dumps(payload))

        result = classifier.classify("Build out the new dashboard this sprint")

        assert isinstance(result, ClassificationResult)
        assert result.category == "projects"
        assert result.confidence == 0.92
        assert result.needs_clarification is False
        assert result.name == "Build new dashboard feature"

    def test_classify_low_confidence_sets_needs_clarification(self, classifier):
        payload = {
            "category": "musings",
            "confidence": 0.3,
            "name": "Unclear entry",
            "next_action": None,
            "needs_clarification": False,  # model says no, but threshold overrides
            "clarification_question": None,
            "payload": {"name": "Unclear entry", "blob": "hmm"},
        }
        import json
        classifier._mock_llm.invoke.return_value = self._make_llm_response(json.dumps(payload))

        result = classifier.classify("hmm")

        assert result.needs_clarification is True
        assert result.clarification_question is not None
        assert "confidence" in result.clarification_question or "clarify" in result.clarification_question.lower()

    def test_classify_malformed_json_returns_graceful_fallback(self, classifier):
        classifier._mock_llm.invoke.return_value = self._make_llm_response("not valid json {{")

        result = classifier.classify("some message")

        assert isinstance(result, ClassificationResult)
        assert result.needs_clarification is True
        assert result.confidence == 0.0
        assert result.category == "musings"
        assert "parse" in result.clarification_question.lower() or "prefix" in result.clarification_question.lower()

    def test_classify_strips_markdown_fences(self, classifier):
        payload = {
            "category": "ideas",
            "confidence": 0.85,
            "name": "Build a personal wiki",
            "next_action": "Research tools",
            "needs_clarification": False,
            "clarification_question": None,
            "payload": {"name": "Build a personal wiki", "premise": "A place for all thoughts"},
        }
        import json
        fenced = f"```json\n{json.dumps(payload)}\n```"
        classifier._mock_llm.invoke.return_value = self._make_llm_response(fenced)

        result = classifier.classify("I want to build a personal wiki")

        assert result.category == "ideas"
        assert result.needs_clarification is False

    def test_classify_with_thread_context(self, classifier):
        payload = {
            "category": "people",
            "confidence": 0.88,
            "name": "Follow up with Alice",
            "next_action": "Send email",
            "needs_clarification": False,
            "clarification_question": None,
            "payload": {"name": "Alice", "email": "alice@example.com"},
        }
        import json
        classifier._mock_llm.invoke.return_value = self._make_llm_response(json.dumps(payload))

        thread_context = [
            {'role': 'user', 'content': 'I met Alice at the conference'},
            {'role': 'assistant', 'content': 'Noted. Do you want to follow up?'},
        ]
        result = classifier.classify("Yes, send her an email about the proposal", thread_context=thread_context)

        assert result.category == "people"
        # Verify thread context messages were passed to the LLM
        call_args = classifier._mock_llm.invoke.call_args[0][0]
        user_messages = [m for m in call_args if hasattr(m, 'content') and 'conference' in m.content]
        assert len(user_messages) == 1

    def test_classify_model_sets_needs_clarification(self, classifier):
        payload = {
            "category": "admin",
            "confidence": 0.75,
            "name": "Handle some thing",
            "next_action": None,
            "needs_clarification": True,
            "clarification_question": "What specifically needs to be handled?",
            "payload": {"name": "Handle some thing"},
        }
        import json
        classifier._mock_llm.invoke.return_value = self._make_llm_response(json.dumps(payload))

        result = classifier.classify("handle that thing")

        assert result.needs_clarification is True
        assert result.clarification_question == "What specifically needs to be handled?"

    def test_classify_high_confidence_no_clarification(self, classifier):
        payload = {
            "category": "admin",
            "confidence": 0.95,
            "name": "Renew car insurance by Friday",
            "next_action": "Call insurance company",
            "needs_clarification": False,
            "clarification_question": None,
            "payload": {"name": "Renew car insurance by Friday", "due": "Friday"},
        }
        import json
        classifier._mock_llm.invoke.return_value = self._make_llm_response(json.dumps(payload))

        result = classifier.classify("Renew car insurance, due Friday")

        assert result.needs_clarification is False
        assert result.clarification_question is None
        assert result.confidence >= CONFIDENCE_THRESHOLD


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
