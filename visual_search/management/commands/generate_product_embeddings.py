from django.core.management.base import BaseCommand
from django.db import transaction
from products.models import Product
from visual_search.models import ProductEmbedding
from visual_search.services import generate_embedding, MODEL_VERSION


class Command(BaseCommand):
    help = (
        "Generates (or regenerates) CLIP embeddings for all active products "
        "that have a product image. Idempotent — safe to rerun any time "
        "products or product images change; existing embeddings are updated "
        "in place rather than duplicated."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Regenerate embeddings even for products that already have one with the current model version.',
        )

    def handle(self, *args, **options):
        force = options['force']

        products = Product.objects.filter(
            is_active=True
        ).exclude(product_image='').exclude(product_image__isnull=True)

        total = products.count()
        created_count = 0
        updated_count = 0
        skipped_count = 0
        failed_count = 0

        self.stdout.write(f"Found {total} active products with images.")

        for product in products:
            existing = ProductEmbedding.objects.filter(product=product).first()

            if existing and existing.model_version == MODEL_VERSION and not force:
                skipped_count += 1
                continue

            try:
                vector = generate_embedding(product.product_image)
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f"Failed to embed '{product.product_name}': {e}")
                )
                failed_count += 1
                continue

            with transaction.atomic():
                if existing:
                    existing.embedding_vector = vector
                    existing.model_version = MODEL_VERSION
                    existing.save(update_fields=['embedding_vector', 'model_version', 'generated_at'])
                    updated_count += 1
                else:
                    ProductEmbedding.objects.create(
                        product=product,
                        embedding_vector=vector,
                        model_version=MODEL_VERSION,
                    )
                    created_count += 1

            self.stdout.write(f"  Embedded: {product.product_name}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Created: {created_count}, Updated: {updated_count}, "
            f"Skipped (already current): {skipped_count}, Failed: {failed_count}"
        ))