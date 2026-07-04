"""
One-off test data seed for Step 12 testing. Adds a small, realistic set of
products across a couple of new categories (Beverages, Snacks) so the AI
Shopping Assistant's NLP, matching, and ranking can be properly exercised.
Safe to run multiple times — uses get_or_create throughout.

Run with: python manage.py shell < seed_step12_test_data.py
"""

from products.models import Category, Product

beverages, _ = Category.objects.get_or_create(category_name="Beverages")
snacks, _ = Category.objects.get_or_create(category_name="Snacks")

test_products = [
    {
        "product_name": "Coca-Cola 500ml",
        "description": "Chilled cola soft drink, 500ml bottle.",
        "category": beverages,
        "unit_price": 10.00,
        "online_price": 12.00,
        "quantity_in_stock": 50,
        "reorder_level": 10,
    },
    {
        "product_name": "Fanta Orange 500ml",
        "description": "Chilled orange-flavoured soft drink, 500ml bottle.",
        "category": beverages,
        "unit_price": 10.00,
        "online_price": 12.00,
        "quantity_in_stock": 40,
        "reorder_level": 10,
    },
    {
        "product_name": "Bottled Water 1.5L",
        "description": "Still drinking water, 1.5 litre bottle.",
        "category": beverages,
        "unit_price": 5.00,
        "online_price": 6.00,
        "quantity_in_stock": 80,
        "reorder_level": 15,
    },
    {
        "product_name": "Premium Sparkling Juice 750ml",
        "description": "Premium sparkling fruit juice, party bottle, 750ml.",
        "category": beverages,
        "unit_price": 25.00,
        "online_price": 30.00,
        "quantity_in_stock": 20,
        "reorder_level": 5,
    },
    {
        "product_name": "Potato Chips 150g",
        "description": "Crispy salted potato chips, party pack, 150g.",
        "category": snacks,
        "unit_price": 8.00,
        "online_price": 9.50,
        "quantity_in_stock": 60,
        "reorder_level": 10,
    },
    {
        "product_name": "Mixed Party Snack Pack",
        "description": "Assorted snack mix for parties and gatherings.",
        "category": snacks,
        "unit_price": 15.00,
        "online_price": 18.00,
        "quantity_in_stock": 30,
        "reorder_level": 8,
    },
    {
        "product_name": "Budget Biscuit Pack",
        "description": "Affordable plain biscuits, everyday snack pack.",
        "category": snacks,
        "unit_price": 4.00,
        "online_price": 5.00,
        "quantity_in_stock": 70,
        "reorder_level": 15,
    },
]

for data in test_products:
    product, created = Product.objects.get_or_create(
        product_name=data["product_name"],
        defaults={
            "description": data["description"],
            "category": data["category"],
            "unit_price": data["unit_price"],
            "online_price": data["online_price"],
            "quantity_in_stock": data["quantity_in_stock"],
            "reorder_level": data["reorder_level"],
            "is_active": True,
            "is_available_online": True,
        },
    )
    status = "created" if created else "already exists"
    print(f"{data['product_name']}: {status}")

print("Done.")