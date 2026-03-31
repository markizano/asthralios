"""
LangGraph-based 2nd Brain classifier.

Flow:
  classify_message → [confidence check]
      → if confident:    structured_extract → return ClassificationResult
      → if uncertain:    return ClassificationResult(needs_clarification=True, ...)
"""

import json
from typing import Optional

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from asthralios.brain.schema import (
    ClassificationResult, PersonEntry, ProjectEntry,
    IdeaEntry, AdminEntry, MusingEntry, EventEntry,
)
from asthralios.brain.prompts import CLASSIFIER_SYSTEM, CLASSIFIER_USER
import asthralios

log = asthralios.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.60  # below this → ask for clarification


class BrainClassifier:
    """
    Classifies a single message into the 2nd Brain taxonomy.
    Takes only the active thread (not full history) as context.
    """

    def __init__(self, config: dict):
        model = config.get('model', 'llama3.2:3b')
        provider = config.get('provider', 'ollama')
        self.llm = init_chat_model(model=model, model_provider=provider)

    def classify(self, message: str, thread_context: Optional[list[dict]] = None) -> ClassificationResult:
        """
        Classify a message. thread_context is a list of recent messages in the
        current thread: [{'role': 'user'|'assistant', 'content': str}, ...]
        Only the thread is passed — never the full channel history.
        """
        messages = [SystemMessage(content=CLASSIFIER_SYSTEM)]

        # Include thread context if provided (for fix: commands or follow-ups)
        if thread_context:
            for msg in thread_context[-6:]:  # cap at 6 to keep context tight
                if msg['role'] == 'user':
                    messages.append(HumanMessage(content=msg['content']))
                # assistant messages in the thread can inform re-classification

        messages.append(HumanMessage(content=CLASSIFIER_USER.format(message=message)))

        raw = self.llm.invoke(messages)
        content = raw.content.strip()

        # Strip accidental markdown fences if the model misbehaves
        if content.startswith('```'):
            content = content.split('```')[1]
            if content.startswith('json'):
                content = content[4:]
        content = content.strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            log.error(f'Classifier returned invalid JSON: {e}\nRaw: {content}')
            return ClassificationResult(
                category='musings',
                confidence=0.0,
                name='Unclassified message',
                payload={},
                raw_message=message,
                needs_clarification=True,
                clarification_question="I couldn't parse this. Could you rephrase or prefix with people/project/idea/admin/musing?"
            )

        confidence = float(data.get('confidence', 0.0))
        needs_clarification = data.get('needs_clarification', False) or confidence < CONFIDENCE_THRESHOLD

        if needs_clarification and not data.get('clarification_question'):
            data['clarification_question'] = (
                f"I'm not sure where this goes (confidence: {confidence:.0%}). "
                "Could you clarify? Try prefixing with: people / project / idea / admin / musing"
            )

        return ClassificationResult(
            category=data.get('category', 'musings'),
            confidence=confidence,
            name=data.get('name', 'Untitled'),
            next_action=data.get('next_action'),
            payload=data.get('payload', {}),
            raw_message=message,
            needs_clarification=needs_clarification,
            clarification_question=data.get('clarification_question') if needs_clarification else None,
        )


def build_brain_classifier(config: dict) -> BrainClassifier:
    return BrainClassifier(config)
