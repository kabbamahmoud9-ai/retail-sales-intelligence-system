from django.contrib import admin
from .models import ProductEmbedding, VisualSearchQuery


@admin.register(ProductEmbedding)
class ProductEmbeddingAdmin(admin.ModelAdmin):
    list_display = ('product', 'model_version', 'generated_at')
    list_filter = ('model_version',)
    search_fields = ('product__product_name',)
    readonly_fields = ('generated_at',)


@admin.register(VisualSearchQuery)
class VisualSearchQueryAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'top_match_confidence', 'model_version', 'created_at', 'was_helpful')
    list_filter = ('model_version', 'was_helpful')
    readonly_fields = ('customer', 'query_image', 'matched_products', 'top_match_confidence', 'model_version', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return True  # allow cleanup of test data; entries are never edited, only created via services