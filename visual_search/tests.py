from unittest.mock import patch
from django.test import TestCase
from products.models import Product, Category
from visual_search.models import ProductEmbedding
from visual_search.services import find_similar_products, MIN_SIMILARITY_THRESHOLD


class SimilarityThresholdTests(TestCase):
    """
    Verifies the MIN_SIMILARITY_THRESHOLD filtering added to
    find_similar_products(). cosine_similarity is mocked so scores
    are fully controlled and deterministic — these tests check the
    filtering logic, not CLIP's actual output.
    """

    def setUp(self):
        self.category = Category.objects.create(category_name='Test Category')
        self.products = []
        for i in range(4):
            p = Product.objects.create(
                category=self.category,
                product_name=f'Test Product {i}',
                unit_price=10,
            )
            ProductEmbedding.objects.create(
                product=p,
                embedding_vector=[float(i)],
                model_version='test-version',
            )
            self.products.append(p)

    def _mock_scores(self, mock_embed, mock_cosine, scores_by_index):
        mock_embed.return_value = [0.0]
        mock_cosine.side_effect = lambda q, v: scores_by_index[int(v[0])]

    @patch('visual_search.services.cosine_similarity')
    @patch('visual_search.services.generate_embedding')
    def test_result_at_0_76_is_retained(self, mock_embed, mock_cosine):
        self._mock_scores(mock_embed, mock_cosine, {0: 0.76, 1: 0.50, 2: 0.40, 3: 0.30})
        results = find_similar_products(query_image=object(), top_n=10)
        ids = [r['product'].id for r in results]
        self.assertIn(self.products[0].id, ids)
        self.assertEqual(len(results), 1)

    @patch('visual_search.services.cosine_similarity')
    @patch('visual_search.services.generate_embedding')
    def test_result_at_0_74_is_excluded(self, mock_embed, mock_cosine):
        self._mock_scores(mock_embed, mock_cosine, {0: 0.74, 1: 0.50, 2: 0.40, 3: 0.30})
        results = find_similar_products(query_image=object(), top_n=10)
        self.assertEqual(results, [])

    @patch('visual_search.services.cosine_similarity')
    @patch('visual_search.services.generate_embedding')
    def test_threshold_applied_before_top_n_truncation(self, mock_embed, mock_cosine):
        # 2 products above threshold, 2 below; top_n=10 must not pad with weak matches
        self._mock_scores(mock_embed, mock_cosine, {0: 0.90, 1: 0.80, 2: 0.60, 3: 0.50})
        results = find_similar_products(query_image=object(), top_n=10)
        self.assertEqual(len(results), 2)
        returned_ids = {r['product'].id for r in results}
        self.assertEqual(returned_ids, {self.products[0].id, self.products[1].id})
        self.assertEqual(results[0]['product'].id, self.products[0].id)  # highest first

    @patch('visual_search.services.cosine_similarity')
    @patch('visual_search.services.generate_embedding')
    def test_no_confident_matches_returns_empty_list(self, mock_embed, mock_cosine):
        self._mock_scores(mock_embed, mock_cosine, {0: 0.10, 1: 0.10, 2: 0.10, 3: 0.10})
        results = find_similar_products(query_image=object(), top_n=10)
        self.assertEqual(results, [])

    @patch('visual_search.services.cosine_similarity')
    @patch('visual_search.services.generate_embedding')
    def test_top_n_still_limits_results_above_threshold(self, mock_embed, mock_cosine):
        # all 4 above threshold, but top_n=2 should still cap the count
        self._mock_scores(mock_embed, mock_cosine, {0: 0.95, 1: 0.90, 2: 0.85, 3: 0.80})
        results = find_similar_products(query_image=object(), top_n=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['product'].id, self.products[0].id)
        self.assertEqual(results[1]['product'].id, self.products[1].id)