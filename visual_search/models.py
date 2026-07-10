from django.db import models
from django.utils import timezone
from products.models import Product
from ecommerce.models import OnlineCustomer


class ProductEmbedding(models.Model):
    """
    Stores a precomputed CLIP embedding for a single product's image.
    Regenerated via the `generate_product_embeddings` management command.
    Never written to directly outside that command / visual_search.services.
    """
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='visual_embedding'
    )
    embedding_vector = models.JSONField(
        help_text="CLIP embedding stored as a list of floats"
    )
    model_version = models.CharField(max_length=100)
    generated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Embedding for {self.product.product_name} ({self.model_version})"


class VisualSearchQuery(models.Model):
    """
    Append-only log of every visual search performed, mirroring the
    ShoppingSession pattern. Never updated after creation except for
    the optional post-hoc feedback fields.
    """
    customer = models.ForeignKey(
        OnlineCustomer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='visual_search_queries'
    )
    query_image = models.ImageField(upload_to='visual_search_queries/%Y/%m/')
    matched_products = models.JSONField(
        help_text="Snapshot of returned matches: [{'product_id': int, 'similarity_score': float}, ...]"
    )
    top_match_confidence = models.FloatField(null=True, blank=True)
    model_version = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)

    was_helpful = models.BooleanField(null=True, blank=True)
    feedback_notes = models.TextField(blank=True)

    def __str__(self):
        return f"Visual search #{self.pk} — {self.created_at:%Y-%m-%d %H:%M}"