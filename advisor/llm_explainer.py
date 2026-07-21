"""
advisor/llm_explainer.py

Optional LLM-powered natural-language explanation layer for the AI
Business Advisor, built on the same centralized core.ai_engine
abstraction used by Conversational Shopping AI. Never a source of
truth — only rephrases/explains data that data_gathering.py and the
existing rule-based handlers in conversational.py already computed
correctly. Governed by the same global settings.AI_PROVIDER as every
other AI-powered module in this project.
"""
from core.ai_engine import generate as ai_generate

SYSTEM_INSTRUCTION = (
    "You are a knowledgeable, professional Sierra Leonean retail business "
    "consultant speaking to a store manager. Explain the given business data "
    "clearly and encouragingly, in 2-4 sentences. Do not invent any figures, "
    "names, or facts beyond what is given — only explain and contextualize them."
)


def explain(base_reply, question_text):
    """
    Rephrases an already-correct rule-based reply via the configured
    LLM provider. Returns rephrased text, or None if the provider is
    rule_based, unconfigured, or fails — callers must fall back to
    base_reply on None.
    """
    prompt = (
        f"A store manager asked: \"{question_text}\"\n\n"
        f"Here is the factually correct business data to respond with:\n\n{base_reply}"
    )
    return ai_generate(prompt, system_instruction=SYSTEM_INSTRUCTION)