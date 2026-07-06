"""
voice_assistant/context_processors.py

Injects the current voice language configuration into every template
context, so pages can render the recognition/response language into
JS without any app importing voice_assistant.config directly.
"""

from .config import VOICE_RECOGNITION_LANGUAGE, VOICE_RESPONSE_LANGUAGE


def voice_language_settings(request):
    return {
        'voice_recognition_language': VOICE_RECOGNITION_LANGUAGE,
        'voice_response_language': VOICE_RESPONSE_LANGUAGE,
    }