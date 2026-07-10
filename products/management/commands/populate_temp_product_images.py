import io
import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from decouple import config
from products.models import Product

PEXELS_API_KEY = config('PEXELS_API_KEY', default='')
PIXABAY_API_KEY = config('PIXABAY_API_KEY', default='')

PEXELS_SEARCH_URL = 'https://api.pexels.com/v1/search'
PIXABAY_SEARCH_URL = 'https://pixabay.com/api/'


def _search_pexels(query):
    """Returns an image URL from Pexels for the given query, or None."""
    if not PEXELS_API_KEY:
        return None
    try:
        response = requests.get(
            PEXELS_SEARCH_URL,
            headers={'Authorization': PEXELS_API_KEY},
            params={'query': query, 'per_page': 1},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        photos = data.get('photos', [])
        if photos:
            return photos[0]['src']['medium']
    except requests.RequestException:
        pass
    return None


def _search_pixabay(query):
    """Returns an image URL from Pixabay for the given query, or None."""
    if not PIXABAY_API_KEY:
        return None
    try:
        response = requests.get(
            PIXABAY_SEARCH_URL,
            params={'key': PIXABAY_API_KEY, 'q': query, 'image_type': 'photo', 'per_page': 3},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        hits = data.get('hits', [])
        if hits:
            return hits[0]['webformatURL']
    except requests.RequestException:
        pass
    return None


def _download_image(url):
    """Downloads image bytes from a URL. Returns bytes or None."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.content
    except requests.RequestException:
        return None


class Command(BaseCommand):
    help = (
        "Populates a temporary product image for any Product with no "
        "product_image, sourced from Pexels (primary) or Pixabay (fallback). "
        "Idempotent — only ever targets products with no image, so a real "
        "admin-uploaded photo is never touched or overwritten by a rerun."
    )

    def handle(self, *args, **options):
        if not PEXELS_API_KEY and not PIXABAY_API_KEY:
            self.stderr.write(self.style.ERROR(
                "No PEXELS_API_KEY or PIXABAY_API_KEY found in .env — at least one is required."
            ))
            return

        products = Product.objects.filter(product_image='') | Product.objects.filter(product_image__isnull=True)
        products = products.distinct()

        total = products.count()
        self.stdout.write(f"Found {total} products with no image.")

        filled_count = 0
        skipped_count = 0

        for product in products:
            query = product.product_name

            image_url = _search_pexels(query)
            source = 'Pexels'

            if not image_url:
                image_url = _search_pixabay(query)
                source = 'Pixabay'

            if not image_url and product.category:
                # fallback to category name if the specific product name found nothing
                image_url = _search_pexels(product.category.category_name)
                source = 'Pexels (category fallback)'
                if not image_url:
                    image_url = _search_pixabay(product.category.category_name)
                    source = 'Pixabay (category fallback)'

            if not image_url:
                self.stdout.write(self.style.WARNING(
                    f"  SKIPPED: '{product.product_name}' — no image found on any provider"
                ))
                skipped_count += 1
                continue

            image_bytes = _download_image(image_url)
            if not image_bytes:
                self.stdout.write(self.style.WARNING(
                    f"  SKIPPED: '{product.product_name}' — found a result but download failed"
                ))
                skipped_count += 1
                continue

            filename = f"{product.pk}_temp.jpg"
            product.product_image.save(filename, ContentFile(image_bytes), save=True)

            self.stdout.write(
                f"  Populated: '{product.product_name}' — source: {source}"
            )
            filled_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Populated: {filled_count}, Skipped: {skipped_count}, Total considered: {total}"
        ))