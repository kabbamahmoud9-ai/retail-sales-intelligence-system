"""
All computer-vision logic is isolated here. This is the ONLY place
the CLIP model is loaded or called. Swapping to a different backend
(e.g. Gemini Vision) later means rewriting the inside of these two
functions only — no other code in the system should ever import
sentence_transformers or reference CLIP directly.
"""
import numpy as np
from django.conf import settings

MODEL_VERSION = "clip-ViT-B-32"

_model = None  # lazy-loaded singleton, avoids reloading CLIP on every call


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_VERSION)
    return _model


def generate_embedding(image):
    """
    Takes a PIL Image (or a path/file-like object sentence-transformers
    can open) and returns a plain Python list of floats.
    """
    from PIL import Image as PILImage
    if not hasattr(image, 'convert'):
        image = PILImage.open(image)
    image = image.convert('RGB')

    model = _get_model()
    vector = model.encode(image)
    return vector.tolist()


def cosine_similarity(vec_a, vec_b):
    a = np.array(vec_a)
    b = np.array(vec_b)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def find_similar_products(query_image, top_n=10):
    """
    Public API. Embeds the uploaded image, compares against every
    stored ProductEmbedding, returns a ranked list of
    {'product': Product, 'similarity_score': float} dicts, highest first.
    """
    from .models import ProductEmbedding

    query_vector = generate_embedding(query_image)

    results = []
    for pe in ProductEmbedding.objects.select_related('product').all():
        score = cosine_similarity(query_vector, pe.embedding_vector)
        results.append({'product': pe.product, 'similarity_score': score})

    results.sort(key=lambda r: r['similarity_score'], reverse=True)
    return results[:top_n]