/**
 * Reusable Voice Assistant module.
 *
 * Wraps the browser's SpeechRecognition and SpeechSynthesis APIs behind
 * a small, consistent interface so any page (Shopping Assistant, Credit &
 * Loyalty Assistant, staff Advisor Recap) can add voice interaction with
 * minimal code. Contains NO business logic — it only captures speech,
 * exposes the transcript, and speaks text handed to it.
 *
 * Language values are read once at construction time, not hardcoded,
 * so a future switch to a Krio locale only requires changing the config
 * values passed in from the Django template — nothing here needs to change.
 */
class VoiceAssistant {
  /**
   * @param {Object} options
   * @param {string} options.recognitionLanguage - e.g. 'en-US'
   * @param {string} [options.responseLanguage] - e.g. 'en' (informational;
   *   response text is expected to already be formatted server-side by
   *   voice_assistant/language.py before being passed to speak()).
   */
  constructor(options = {}) {
    this.recognitionLanguage = options.recognitionLanguage || 'en-US';
    this.responseLanguage = options.responseLanguage || 'en';

    const SpeechRecognitionAPI =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    this.recognitionSupported = !!SpeechRecognitionAPI;
    this.synthesisSupported = 'speechSynthesis' in window;

    if (this.recognitionSupported) {
      this.recognition = new SpeechRecognitionAPI();
      this.recognition.lang = this.recognitionLanguage;
      this.recognition.interimResults = false;
      this.recognition.maxAlternatives = 1;
    } else {
      this.recognition = null;
    }

    this._listening = false;
  }

  /**
   * Starts listening for a single spoken utterance.
   * @param {(transcript: string) => void} onResult
   * @param {(error: any) => void} [onError]
   */
  startListening(onResult, onError) {
    if (!this.recognitionSupported) {
      if (onError) onError(new Error('SpeechRecognition not supported in this browser.'));
      return;
    }
    if (this._listening) return;

    this._listening = true;

    this.recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      this._listening = false;
      onResult(transcript);
    };

    this.recognition.onerror = (event) => {
      this._listening = false;
      if (onError) onError(event.error);
    };

    this.recognition.onend = () => {
      this._listening = false;
    };

    this.recognition.start();
  }

  stopListening() {
    if (this.recognition && this._listening) {
      this.recognition.stop();
    }
  }

  /**
   * Speaks the given text aloud. Text is expected to already be
   * formatted for the target response language upstream (see
   * voice_assistant/language.py) — this method does not translate.
   * @param {string} text
   * @param {() => void} [onEnd]
   */
  speak(text, onEnd) {
    if (!this.synthesisSupported) {
      if (onEnd) onEnd();
      return;
    }

    window.speechSynthesis.cancel(); // avoid overlapping utterances

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = this.recognitionLanguage;
    if (onEnd) utterance.onend = onEnd;
    window.speechSynthesis.speak(utterance);
  }

  isListening() {
    return this._listening;
  }
}

window.VoiceAssistant = VoiceAssistant;