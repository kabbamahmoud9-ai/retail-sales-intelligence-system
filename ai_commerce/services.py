"""
Service layer for the ai_commerce app.

Architecture (rule-based + NLTK, per Step 12 revision — no external/paid AI
APIs):
    1. parse_natural_language_query() -> NLTK-based NLP. Tokenizes, removes
       stopwords, lemmatizes, then matches tokens against real category
       names (fuzzy match) and detects a price-sensitivity signal. This is
       genuine NLP, entirely offline and free.
    2. get_candidate_products()       -> Pure Django ORM, zero AI. Filters
       our actual catalogue using the parsed intent plus stock, quality-
       tier, and price rules. This is the ONLY place product eligibility
       is decided.
    3. generate_shopping_recommendations() -> Pure rule-based scoring.
       Ranks the pre-filtered candidates using a weighted-factor formula
       and generates a specific, per-product explanation from dynamic
       templates (no LLM).

Extensibility seam: `_extract_intent()` and `_rank_and_explain()` are the
two swap points. If an LLM is added later (e.g. for richer NL understanding
or more natural-sounding explanations), only these two functions need to
change — everything else (views, models, cart integration, the public
function signatures) stays untouched. Same philosophy as
DeliveryZone.calculate_fee() being the sole seam for a future mapping API.
"""

import difflib
import re

import nltk
from django.db.models import Avg, Q
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

from products.models import Category, Product

from .models import ShoppingRecommendation

ASSISTANT_VERSION = "v1-rule-based"
MAX_CANDIDATES = 25   # keeps candidate scoring bounded
MAX_RECOMMENDATIONS = 8  # size of the basket shown to the customer

_LEMMATIZER = WordNetLemmatizer()

_BUDGET_SIGNAL_WORDS = {"cheap", "affordable", "budget", "save", "cheapest", "inexpensive"}
_PREMIUM_SIGNAL_WORDS = {"premium", "quality", "best", "deluxe", "finest", "top"}
_EXTRA_STOPWORDS = {"need", "want", "get", "like", "looking", "give", "please", "would"}


def _ensure_nltk_data():
    """
    Defensive one-time check so the app doesn't crash on a fresh machine
    that hasn't run the download command yet — auto-downloads quietly if
    a resource is missing. Doesn't re-download if already present.
    """
    resources = [
        ("tokenizers/punkt_tab", "punkt_tab"),
        ("corpora/stopwords", "stopwords"),
        ("corpora/wordnet", "wordnet"),
    ]
    for path, name in resources:
        try:
            nltk.data.find(path)
        except LookupError:
            nltk.download(name, quiet=True)


def _tokenize_and_lemmatize(text):
    """
    Tokenize, lowercase, strip punctuation/stopwords, lemmatize.
    Returns a list of meaningful lemmas.
    """
    _ensure_nltk_data()
    stop_words = set(stopwords.words('english')) | _EXTRA_STOPWORDS
    tokens = word_tokenize(text.lower())
    tokens = [re.sub(r'[^a-z]', '', t) for t in tokens]
    tokens = [t for t in tokens if t and t not in stop_words]
    return [_LEMMATIZER.lemmatize(t) for t in tokens]


def _match_categories(lemmas):
    """
    Fuzzy-matches lemmatized tokens against real Category.category_name
    values, so "drink" matches "Beverages" via a close-enough string match
    on the lemma, not an exact match.
    """
    category_names = list(Category.objects.values_list('category_name', flat=True))
    matched = set()
    for lemma in lemmas:
        for name in category_names:
            name_lemmas = _tokenize_and_lemmatize(name)
            if lemma in name_lemmas or difflib.get_close_matches(lemma, name_lemmas, cutoff=0.8):
                matched.add(name)
    return list(matched)


def _detect_price_sensitivity(lemmas):
    """
    'low'    = customer wants low prices (budget-conscious)
    'high'   = customer is prioritizing quality/premium over price
    'medium' = no clear signal, treat as standard
    """
    lemma_set = set(lemmas)
    if lemma_set & _BUDGET_SIGNAL_WORDS:
        return 'low'
    if lemma_set & _PREMIUM_SIGNAL_WORDS:
        return 'high'
    return 'medium'


def parse_natural_language_query(raw_query):
    """
    Mode 1 only. Extracts structured shopping intent from free text using
    NLTK tokenization/stopword-removal/lemmatization plus fuzzy category
    matching — no external AI service involved.

    Returns:
        {
          "categories": [str, ...],
          "keywords": [str, ...],       # lemmatized, category-independent
          "price_sensitivity": "low" | "medium" | "high"
        }
    """
    lemmas = _tokenize_and_lemmatize(raw_query)
    categories = _match_categories(lemmas)
    price_sensitivity = _detect_price_sensitivity(lemmas)

    # Keywords = lemmas that aren't just category names or price-signal words,
    # since those are already captured in their own fields.
    signal_words = _BUDGET_SIGNAL_WORDS | _PREMIUM_SIGNAL_WORDS
    keywords = [l for l in lemmas if l not in signal_words]

    return {
        "categories": categories,
        "keywords": keywords,
        "price_sensitivity": price_sensitivity,
    }


_GOAL_KEYWORD_MAP = {
    'healthy_living': ['fresh', 'fruit', 'vegetable', 'organic'],
    'party_shopping': ['drink', 'snack', 'party'],
    'weekly_groceries': ['rice', 'oil', 'staple'],
    # 'save_money' and 'premium_quality' are handled via quality_preference
    # (or the derived price_sensitivity for NL mode) instead of keywords.
}


def _apply_quality_tier_filter(queryset, quality_preference):
    """
    v1 proxy for "quality": price relative to the category average, since
    Product has no explicit quality/rating field. Budget = at or below
    category average, Premium = at or above, Standard = no filter.
    """
    result_ids = []
    for product in queryset:
        if not product.online_price:
            continue
        category_avg = (
            Product.objects.filter(category=product.category, is_active=True)
            .aggregate(avg_price=Avg('online_price'))['avg_price']
        )
        if not category_avg:
            result_ids.append(product.id)
            continue
        if quality_preference == 'budget' and product.online_price <= category_avg:
            result_ids.append(product.id)
        elif quality_preference == 'premium' and product.online_price >= category_avg:
            result_ids.append(product.id)
        elif quality_preference == 'standard':
            result_ids.append(product.id)
    return queryset.filter(id__in=result_ids)


def _effective_quality_preference(session):
    """
    Mode 2 (guided planner) sets quality_preference explicitly. For Mode 1
    (natural language), derive an equivalent from the NLTK-detected
    price_sensitivity so the same filter logic applies uniformly.
    """
    if session.quality_preference:
        return session.quality_preference
    if session.mode == 'natural_language' and session.parsed_intent:
        sensitivity = session.parsed_intent.get('price_sensitivity')
        return {'low': 'budget', 'high': 'premium'}.get(sensitivity)
    return None


def get_candidate_products(session):
    """
    Pure rule-based filtering. No AI. The single source of truth for which
    products are even eligible to be recommended in this session.
    """
    queryset = Product.objects.filter(
        is_active=True,
        is_available_online=True,
        quantity_in_stock__gt=0,
    )

    categories = []
    keywords = []

    if session.mode == 'natural_language' and session.parsed_intent:
        categories = session.parsed_intent.get('categories', [])
        keywords = session.parsed_intent.get('keywords', [])
    elif session.mode == 'shop_by_goal':
        keywords = _GOAL_KEYWORD_MAP.get(session.goal, [])

    if categories:
        queryset = queryset.filter(category__category_name__in=categories)

    if keywords:
        keyword_query = Q()
        for word in keywords:
            keyword_query |= (
                Q(product_name__icontains=word)
                | Q(description__icontains=word)
                | Q(category__category_name__icontains=word)
            )
        keyword_filtered = queryset.filter(keyword_query)
        # Soft filter: if strict keyword matching excludes everything,
        # fall back to the unfiltered (category/quality-only) queryset
        # rather than returning nothing.
        if keyword_filtered.exists():
            queryset = keyword_filtered

    quality_preference = _effective_quality_preference(session)
    if quality_preference:
        queryset = _apply_quality_tier_filter(queryset, quality_preference)

    return list(queryset.select_related('category').distinct()[:MAX_CANDIDATES])


def _score_and_explain_one(session, product, categories, keywords, quality_preference):
    """
    Scores a single candidate product and generates its explanation.
    Weighted-factor formula, same rule-based-transparency spirit as
    calculate_trust_score(). Returns (score, reasoning).
    """
    score = 0.0
    reasons = []
    relevance_found = False

    category_matched = bool(product.category and product.category.category_name in categories)
    if category_matched:
        score += 3
        relevance_found = True
        reasons.append(f"matches your interest in {product.category.category_name}")

    product_lemmas = set(_tokenize_and_lemmatize(product.product_name))
    matched_keywords = product_lemmas & set(keywords)
    if matched_keywords:
        score += min(len(matched_keywords), 2)
        relevance_found = True
        reasons.append(f"matches what you asked for ({', '.join(sorted(matched_keywords))})")

    budget_note = None
    if session.budget and product.online_price:
        if product.online_price <= session.budget:
            score += 2
            budget_note = "fits comfortably within your budget"
        elif product.online_price <= session.budget * 1.2:
            score += 1
            budget_note = "just slightly above your stated budget"
        else:
            budget_note = "above your stated budget, included as a higher-quality option"
    if budget_note:
        reasons.append(budget_note)

    if quality_preference == 'premium':
        score += 1
        reasons.append("is a top-tier option in its category")
    elif quality_preference == 'budget':
        score += 1
        reasons.append("is a wallet-friendly option in its category")

    if product.quantity_in_stock > product.reorder_level:
        score += 0.5
        reasons.append("is well-stocked and ready to ship")

    if not relevance_found:
        # Honest fallback: no category/keyword match exists in the catalog
        # for this request, so don't imply relevance that isn't there.
        fallback_reasons = reasons if reasons else ["is currently in stock"]
        reasoning = (
            "No close match for your request was found in our catalog, so "
            "this is shown as an available option: it " + ", and ".join(fallback_reasons) + "."
        )
        return score, reasoning

    reasoning = "Recommended because it " + ", and ".join(reasons) + "."
    return score, reasoning


def _rank_and_explain(session, candidates):
    """
    The swappable ranking/explanation seam. Scores every candidate, sorts
    descending, returns (product, score, reasoning) tuples for the top
    MAX_RECOMMENDATIONS.
    """
    categories = []
    keywords = []
    if session.mode == 'natural_language' and session.parsed_intent:
        categories = session.parsed_intent.get('categories', [])
        keywords = session.parsed_intent.get('keywords', [])
    elif session.mode == 'shop_by_goal':
        keywords = _GOAL_KEYWORD_MAP.get(session.goal, [])

    quality_preference = _effective_quality_preference(session)

    scored = [
        (product, *_score_and_explain_one(session, product, categories, keywords, quality_preference))
        for product in candidates
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:MAX_RECOMMENDATIONS]


def generate_shopping_recommendations(session):
    """
    The single entry point for producing a ranked, explained basket —
    entirely rule-based, no external AI service.

    Flow:
      1. get_candidate_products(session) — rule-based, zero AI
      2. _rank_and_explain(session, candidates) — weighted scoring +
         template-based reasoning
      3. Persist ShoppingRecommendation rows

    Returns the list of created ShoppingRecommendation instances. Returns
    an empty list if there are no eligible candidates.
    """
    candidates = get_candidate_products(session)
    if not candidates:
        return []

    ranked = _rank_and_explain(session, candidates)
    if not ranked:
        return []

    max_score = max(score for _, score, _ in ranked) or 1.0

    created = []
    for rank, (product, score, reasoning) in enumerate(ranked, start=1):
        created.append(
            ShoppingRecommendation.objects.create(
                session=session,
                product=product,
                rank=rank,
                reasoning=reasoning,
                match_score=score,
                confidence_score=round(score / max_score, 2),
                assistant_version=ASSISTANT_VERSION,
            )
        )
    return created