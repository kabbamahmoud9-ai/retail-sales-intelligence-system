"""
Language formatting layer for Voice Assistant.

This module sits between the narration helper and Text-to-Speech.
It is presentation-only: it never performs business calculations or
generates new recommendations. It takes already-narrated English text
and returns text ready for speech synthesis, in the configured
VOICE_RESPONSE_LANGUAGE.

v1: response language is English, so this simply returns the text
unchanged. This is the documented seam for adding template-based Krio
phrasing later without changing any other part of the Voice Assistant
or any of the services it reads from.
"""

from .config import VOICE_RESPONSE_LANGUAGE


def format_for_speech(narrated_text, response_language=None):
    """
    Format already-narrated text for Text-to-Speech in the configured
    response language.

    Args:
        narrated_text (str): Plain-English summary produced by narration.py.
        response_language (str, optional): Overrides VOICE_RESPONSE_LANGUAGE
            for this call. Defaults to the configured value.

    Returns:
        str: Text ready to be passed to SpeechSynthesis.
    """
    language = response_language or VOICE_RESPONSE_LANGUAGE

    if language == 'en':
        return narrated_text

    # Future seam: add Krio (or other) template-based formatting here,
    # e.g. `if language == 'kri': return _translate_to_krio(narrated_text)`
    # Unrecognized languages fall back to English text rather than failing.
    return narrated_text