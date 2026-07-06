"""
Voice Assistant configuration.

This module is the single source of truth for voice language settings.
Change these two values here only — nothing else in the app should
hardcode a language string.
"""

# Controls the browser's SpeechRecognition language (speech -> text).
# Browser support for a native Krio ('kri') locale is not guaranteed today,
# so English is used as a practical approximation for v1.
VOICE_RECOGNITION_LANGUAGE = 'en-US'

# Controls how narrated responses are formatted before being sent to
# SpeechSynthesis (text -> speech). Kept separate from recognition language
# so that, in future, recognition could stay 'en-US' while responses are
# formatted in Krio via language.py, without touching any other code.
VOICE_RESPONSE_LANGUAGE = 'en'