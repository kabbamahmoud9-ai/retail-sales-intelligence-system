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
from collections import Counter
from decimal import Decimal

import nltk
from django.db.models import Avg, Q
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

from products.models import Category, Product

from ecommerce.models import OnlineOrderItem
from .models import CreditAssessment, ShoppingRecommendation

ASSISTANT_VERSION = "v1-rule-based"
MAX_CANDIDATES = 25   # keeps candidate scoring bounded
MAX_RECOMMENDATIONS = 8  # size of the basket shown to the customer
MAX_PER_CATEGORY = 3  # prevents one category with many tied-score items
                       # from crowding out a genuinely relevant but
                       # lower-scoring match from a different category
                       # (e.g. a single keyword-matched "chicken" item
                       # getting squeezed out by many "Cooking Oil" items)


def _effective_max_recommendations(session):
    """
    Scales basket size with family_size when provided — a party of 10
    reasonably needs more items shown than a party of 1. Falls back to
    the existing fixed MAX_RECOMMENDATIONS when family_size is unset,
    so every existing caller (Mode 1, Mode 3, no family_size set) is
    completely unaffected.
    """
    if session.family_size and session.family_size > 4:
        return min(MAX_RECOMMENDATIONS + 4, 12)
    return MAX_RECOMMENDATIONS



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
    categories = set(_match_categories(lemmas))
    categories.update(_detect_dish_categories(raw_query))
    price_sensitivity = _detect_price_sensitivity(lemmas)

    # Keywords = lemmas that aren't just category names or price-signal words,
    # since those are already captured in their own fields.
    signal_words = _BUDGET_SIGNAL_WORDS | _PREMIUM_SIGNAL_WORDS
    keywords = [l for l in lemmas if l not in signal_words]

    return {
        "categories": list(categories),
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

_DISH_KEYWORD_CATEGORY_MAP = {
    'jollof rice': ['Rice & Grains', 'Cooking Oil', 'Canned Foods', 'Spices & Seasonings'],
    'fried rice': ['Rice & Grains', 'Cooking Oil', 'Frozen Foods', 'Spices & Seasonings', 'Fresh Produce'],
    'salad': ['Fresh Produce', 'Cooking Oil'],
    'breakfast': ['Bread & Bakery', 'Dairy Products', 'Tea & Coffee', 'Beverages'],
    'party': ['Water & Soft Drinks', 'Beverages', 'Biscuits & Snacks', 'Confectionery'],
}


def _detect_dish_categories(raw_query):
    """
    Detects mentions of common local dishes/occasions in the raw query and
    maps them to the categories that supply their ingredients. This bridges
    the gap between a dish name (not itself a category or literal product
    keyword) and the actual catalog structure — e.g. "jollof rice" implies
    Rice & Grains + Cooking Oil + Spices, even though none of those words
    appear verbatim in "jollof rice". Deliberately simple substring
    matching on the full phrase, not per-token — same rule-based
    philosophy as the rest of this module, easily extended with more
    dishes as the catalog grows.
    """
    query_lower = raw_query.lower()
    matched_categories = set()
    for phrase, categories in _DISH_KEYWORD_CATEGORY_MAP.items():
        if phrase in query_lower:
            matched_categories.update(categories)
    return list(matched_categories)


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

# shopping_purpose is free text on ANY mode (not just guided_planner) —
    # reuse the same dish/occasion -> category bridge already proven for
    # Mode 1's raw_query, so "birthday party" or "light food" contributes
    # real category signal instead of being silently ignored.
    if session.shopping_purpose:
        categories = list(set(categories) | set(_detect_dish_categories(session.shopping_purpose)))
        purpose_lemmas = _tokenize_and_lemmatize(session.shopping_purpose)
        keywords = list(set(keywords) | set(purpose_lemmas))

    # Category and keyword matches combine as OR, not AND — a request like
    # "fried rice and chicken" should surface BOTH Rice & Grains category
    # products AND keyword-matched chicken products (in a different
    # category), not exclude one because of the other. Keyword matching
    # only checks product_name/description — NOT category_name — since
    # matching a keyword against the category's own label caused false
    # positives (e.g. "rice" matching the text "Rice & Grains" for every
    # product in that category, including unrelated ones like Garri).
    category_matches = (
        queryset.filter(category__category_name__in=categories) if categories else queryset.none()
    )

    keyword_query = Q()
    for word in keywords:
        keyword_query |= Q(product_name__icontains=word) | Q(description__icontains=word)
    keyword_matches = queryset.filter(keyword_query) if keywords else queryset.none()

    if categories or keywords:
        combined = (category_matches | keyword_matches).distinct()
        # Soft fallback: if neither signal matched anything real, fall
        # through to the full (quality-tier-filtered) queryset below,
        # rather than returning nothing.
        if combined.exists():
            queryset = combined

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

    if session.shopping_purpose:
        categories = list(set(categories) | set(_detect_dish_categories(session.shopping_purpose)))
        purpose_lemmas = _tokenize_and_lemmatize(session.shopping_purpose)
        keywords = list(set(keywords) | set(purpose_lemmas))

    quality_preference = _effective_quality_preference(session)

    scored = [
        (product, *_score_and_explain_one(session, product, categories, keywords, quality_preference))
        for product in candidates
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return _diversify_by_category(scored, max_recommendations=_effective_max_recommendations(session))


def _diversify_by_category(scored, max_recommendations=MAX_RECOMMENDATIONS):
    """
    Selects the final basket from the score-sorted candidate list, capping
    how many items any single category contributes (MAX_PER_CATEGORY).
    This ensures a multi-need request (e.g. salad ingredients + chicken)
    surfaces items across all genuinely matched categories/keywords,
    rather than one category with many similarly-scored products
    dominating every slot. Falls back to filling remaining slots from
    whatever's left over, still in score order, if the cap leaves room.
    """
    selected = []
    leftover = []
    category_counts = Counter()

    for product, score, reasoning in scored:
        if len(selected) >= max_recommendations:
            break
        category_name = product.category.category_name if product.category else 'Uncategorized'
        if category_counts[category_name] < MAX_PER_CATEGORY:
            selected.append((product, score, reasoning))
            category_counts[category_name] += 1
        else:
            leftover.append((product, score, reasoning))

    for item in leftover:
        if len(selected) >= max_recommendations:
            break
        selected.append(item)

    return selected


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
# ---------------------------------------------------------------------------
# Smart Credit & Loyalty Assistant (Step 12c)
# ---------------------------------------------------------------------------

# Base recommended limit per loyalty tier, before the trust-score
# multiplier is applied. Named constants, not scattered magic numbers —
# same convention as ecommerce.services.LOYALTY_TIER_THRESHOLDS.
CREDIT_TIER_BASE_LIMITS = {
    'Bronze': Decimal('500.00'),
    'Silver': Decimal('2000.00'),
    'Gold': Decimal('5000.00'),
    'Platinum': Decimal('10000.00'),
}


def calculate_credit_recommendation(customer):
    """
    Rule-based v1 Smart Credit Assistant. Encapsulated here so it can be
    replaced by an ML model later without changing any caller — same
    extensibility philosophy as ecommerce.services.calculate_trust_score().

    Formula:
      1. Start from a base limit for the customer's current loyalty_tier
      2. Scale it by a trust-score multiplier (0.5x at trust_score=0, up
         to 1.5x at trust_score=100)
      3. Compare the recommended limit and credit utilization
         (credit_balance / credit_limit) against thresholds to decide
         eligibility_status

    Persists and returns a new CreditAssessment row (append-only — full
    history retained for future accuracy review, same philosophy as
    DemandForecast/ShoppingRecommendation). This function only ever
    recommends; OnlineCustomer.credit_limit is never written here.
    """
    tier = customer.loyalty_tier
    base_limit = CREDIT_TIER_BASE_LIMITS.get(tier, CREDIT_TIER_BASE_LIMITS['Bronze'])

    trust_multiplier = Decimal('0.5') + (Decimal(customer.trust_score) / Decimal('100'))
    recommended_limit = (base_limit * trust_multiplier).quantize(Decimal('0.01'))

    utilization = (
        customer.credit_balance / customer.credit_limit
        if customer.credit_limit > 0 else Decimal('0.00')
    )

    if customer.trust_score < 40 or utilization > Decimal('0.8'):
        eligibility_status = 'review_needed'
        reasoning = (
            f"Trust score ({customer.trust_score}) or credit utilization "
            f"({utilization:.0%}) indicates a manual review is warranted "
            f"before adjusting this customer's limit."
        )
    elif (
        customer.trust_score >= 70
        and utilization <= Decimal('0.3')
        and recommended_limit > customer.credit_limit
    ):
        eligibility_status = 'eligible_increase'
        reasoning = (
            f"Strong trust score ({customer.trust_score}), low utilization "
            f"({utilization:.0%}), and {tier} loyalty tier support increasing "
            f"the credit limit to Le {recommended_limit}."
        )
    else:
        eligibility_status = 'maintain'
        reasoning = (
            f"Current trust score ({customer.trust_score}), utilization "
            f"({utilization:.0%}), and {tier} tier support keeping the "
            f"existing credit limit as-is for now."
        )

    return CreditAssessment.objects.create(
        customer=customer,
        trust_score_snapshot=customer.trust_score,
        loyalty_tier_snapshot=tier,
        lifetime_spending_snapshot=customer.lifetime_spending,
        outstanding_balance_snapshot=customer.credit_balance,
        recommended_credit_limit=recommended_limit,
        eligibility_status=eligibility_status,
        reasoning=reasoning,
        assistant_version=ASSISTANT_VERSION,
    )


def get_reorder_suggestions(customer, limit=5):
    """
    Returns the customer's most frequently purchased products, most-bought
    first, for the "reorder previous purchases" feature. Only suggests
    products still active and available online.

    Pure read/aggregation against existing order history — no new model,
    no AI involved (this is fact retrieval, not a recommendation call).

    Returns a list of dicts:
        [{"product": Product, "times_ordered": int, "last_ordered": datetime}, ...]
    """
    items = (
        OnlineOrderItem.objects
        .filter(
            order__customer=customer,
            order__status__in=['confirmed', 'processing', 'shipped', 'delivered'],
            product__is_active=True,
            product__is_available_online=True,
        )
        .select_related('product', 'order')
    )

    counts = Counter()
    last_ordered = {}
    products_by_id = {}
    for item in items:
        counts[item.product_id] += 1
        products_by_id[item.product_id] = item.product
        if item.product_id not in last_ordered or item.order.order_date > last_ordered[item.product_id]:
            last_ordered[item.product_id] = item.order.order_date

    ranked = counts.most_common(limit)
    return [
        {
            "product": products_by_id[product_id],
            "times_ordered": count,
            "last_ordered": last_ordered[product_id],
        }
        for product_id, count in ranked
    ]