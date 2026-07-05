"""
products/management/commands/seed_full_catalog.py

Seeds a realistic Sierra Leone retail catalog (~100 products across ~21
categories) for dissertation testing: AI Shopping Assistant, Smart Credit
& Loyalty Assistant, Demand Forecasting, Business Advisor, Delivery
Costing, Sales, and Inventory.

SAFE TO RUN MULTIPLE TIMES:
  - Categories: get_or_create() on category_name (no duplicates).
  - Suppliers: get_or_create() on supplier_name (no duplicates).
  - Products: get_or_create() on product_name (no duplicates). If a
    product with that name already exists (including ones you entered
    manually), it is left alone except for filling in any fields that
    are currently blank/null (description, category, supplier,
    online_price) — existing populated values are never overwritten.

USAGE:
    python manage.py seed_full_catalog

Reports counts of categories/suppliers/products created, updated
(missing fields filled in), and skipped (already complete, untouched).
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from products.models import Category, Supplier, Product


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

CATEGORIES = [
    "Rice & Grains",
    "Flour",
    "Sugar",
    "Cooking Oil",
    "Spices & Seasonings",
    "Canned Foods",
    "Beverages",
    "Water & Soft Drinks",
    "Dairy Products",
    "Bread & Bakery",
    "Biscuits & Snacks",
    "Tea & Coffee",
    "Frozen Foods",
    "Personal Care",
    "Toiletries",
    "Baby Products",
    "Cleaning Supplies",
    "Household Essentials",
    "Stationery",
    "Health & Wellness",
    "Confectionery",
]

# ---------------------------------------------------------------------------
# Suppliers — one general-purpose supplier per related category group
# ---------------------------------------------------------------------------

SUPPLIERS = [
    {
        "supplier_name": "Freetown Wholesale Foods Ltd",
        "phone": "+232 76 100 001",
        "email": "sales@freetownwholesale.sl",
        "address": "12 Wallace Johnson St, Freetown",
    },
    {
        "supplier_name": "SL Beverages Distributors",
        "phone": "+232 76 100 002",
        "email": "orders@slbeverages.sl",
        "address": "45 Bo Road, Freetown",
    },
    {
        "supplier_name": "West Africa Dairy & Bakery Supplies",
        "phone": "+232 76 100 003",
        "email": "info@wadairybakery.sl",
        "address": "8 Kissy Road, Freetown",
    },
    {
        "supplier_name": "National Snacks & Confectionery Co.",
        "phone": "+232 76 100 004",
        "email": "sales@nationalsnacks.sl",
        "address": "23 Circular Road, Freetown",
    },
    {
        "supplier_name": "CoolChain Frozen Foods Ltd",
        "phone": "+232 76 100 005",
        "email": "orders@coolchain.sl",
        "address": "3 Cline Town, Freetown",
    },
    {
        "supplier_name": "PureCare Personal & Toiletries Ltd",
        "phone": "+232 76 100 006",
        "email": "info@purecare.sl",
        "address": "17 Siaka Stevens St, Freetown",
    },
    {
        "supplier_name": "Little Ones Baby Supplies",
        "phone": "+232 76 100 007",
        "email": "hello@littleones.sl",
        "address": "9 Regent Road, Freetown",
    },
    {
        "supplier_name": "CleanHome Household Supplies Ltd",
        "phone": "+232 76 100 008",
        "email": "sales@cleanhome.sl",
        "address": "31 Pademba Road, Freetown",
    },
    {
        "supplier_name": "Freetown Stationery & Office Supplies",
        "phone": "+232 76 100 009",
        "email": "info@fnstationery.sl",
        "address": "14 Rawdon St, Freetown",
    },
]

# Maps each category to the supplier that stocks it
CATEGORY_SUPPLIER_MAP = {
    "Rice & Grains": "Freetown Wholesale Foods Ltd",
    "Flour": "Freetown Wholesale Foods Ltd",
    "Sugar": "Freetown Wholesale Foods Ltd",
    "Cooking Oil": "Freetown Wholesale Foods Ltd",
    "Spices & Seasonings": "Freetown Wholesale Foods Ltd",
    "Canned Foods": "Freetown Wholesale Foods Ltd",
    "Beverages": "SL Beverages Distributors",
    "Water & Soft Drinks": "SL Beverages Distributors",
    "Tea & Coffee": "SL Beverages Distributors",
    "Dairy Products": "West Africa Dairy & Bakery Supplies",
    "Bread & Bakery": "West Africa Dairy & Bakery Supplies",
    "Biscuits & Snacks": "National Snacks & Confectionery Co.",
    "Confectionery": "National Snacks & Confectionery Co.",
    "Frozen Foods": "CoolChain Frozen Foods Ltd",
    "Personal Care": "PureCare Personal & Toiletries Ltd",
    "Toiletries": "PureCare Personal & Toiletries Ltd",
    "Health & Wellness": "PureCare Personal & Toiletries Ltd",
    "Baby Products": "Little Ones Baby Supplies",
    "Cleaning Supplies": "CleanHome Household Supplies Ltd",
    "Household Essentials": "CleanHome Household Supplies Ltd",
    "Stationery": "Freetown Stationery & Office Supplies",
}

# ---------------------------------------------------------------------------
# Products
# Each tuple: (name, description, unit_price, online_price, stock, reorder,
#              is_available_online)
# Prices in Leones (New Leone scale, consistent with existing loyalty tier
# thresholds of Le0-10,000+ lifetime spending).
# ---------------------------------------------------------------------------

PRODUCTS_BY_CATEGORY = {
    "Rice & Grains": [
        ("Local Rice 50kg Bag", "Locally grown parboiled rice, 50kg bag.", 450.00, 480.00, 40, 10, False),
        ("Perfumed Rice 25kg Bag", "Imported fragrant long-grain rice, 25kg bag.", 260.00, 285.00, 50, 10, True),
        ("Basmati Rice 5kg", "Premium basmati rice, 5kg pack.", 65.00, 75.00, 60, 15, True),
        ("Brown Rice 5kg", "Whole grain brown rice, 5kg pack.", 55.00, 65.00, 35, 10, True),
        ("Garri (Cassava Flakes) 5kg", "Roasted cassava flakes, 5kg pack.", 40.00, 48.00, 70, 15, True),
    ],
    "Flour": [
        ("Self-Raising Flour 2kg", "All-purpose self-raising wheat flour, 2kg.", 18.00, 22.00, 80, 20, True),
        ("Plain Flour 2kg", "Plain wheat flour, 2kg pack.", 17.00, 20.00, 75, 20, True),
        ("Wheat Flour 10kg Bag", "Bulk wheat flour, 10kg bag for bakeries.", 80.00, 90.00, 25, 8, False),
        ("Corn Flour 1kg", "Fine corn flour, 1kg pack.", 12.00, 15.00, 60, 15, True),
        ("Cassava Flour 2kg", "Fine cassava flour, 2kg pack.", 20.00, 24.00, 55, 15, True),
    ],
    "Sugar": [
        ("White Granulated Sugar 1kg", "Fine white granulated sugar, 1kg.", 15.00, 18.00, 100, 25, True),
        ("Brown Sugar 1kg", "Unrefined brown sugar, 1kg.", 17.00, 20.00, 60, 15, True),
        ("Sugar Cubes 500g", "Sugar cubes for tea and coffee, 500g box.", 10.00, 13.00, 45, 10, True),
        ("Icing Sugar 500g", "Fine icing sugar for baking, 500g.", 12.00, 15.00, 30, 10, True),
        ("Sugar 5kg Bulk Bag", "Bulk white sugar, 5kg bag.", 65.00, 75.00, 30, 10, True),
    ],
    "Cooking Oil": [
        ("Palm Oil 1L", "Pure red palm oil, 1 litre bottle.", 22.00, 26.00, 70, 15, True),
        ("Vegetable Oil 1L", "Refined vegetable cooking oil, 1 litre.", 20.00, 24.00, 80, 15, True),
        ("Groundnut Oil 1L", "Pure groundnut cooking oil, 1 litre.", 25.00, 29.00, 50, 12, True),
        ("Sunflower Oil 1L Premium", "Premium cold-pressed sunflower oil, 1 litre.", 35.00, 42.00, 30, 8, True),
        ("Olive Oil 500ml Premium", "Extra virgin olive oil, premium import, 500ml.", 55.00, 65.00, 20, 5, True),
    ],
    "Spices & Seasonings": [
        ("Maggi Cubes Pack of 10", "Seasoning cubes, pack of 10.", 8.00, 10.00, 100, 25, True),
        ("Curry Powder 100g", "Blended curry powder, 100g.", 9.00, 11.00, 60, 15, True),
        ("Black Pepper 100g", "Ground black pepper, 100g.", 14.00, 17.00, 40, 10, True),
        ("Ginger Powder 100g", "Dried ground ginger, 100g.", 10.00, 12.00, 35, 10, True),
        ("Onion & Garlic Seasoning Mix 200g", "Blended onion and garlic seasoning, 200g.", 13.00, 16.00, 45, 12, True),
    ],
    "Canned Foods": [
        ("Canned Sardines 125g", "Sardines in vegetable oil, 125g tin.", 8.00, 10.00, 90, 20, True),
        ("Canned Corned Beef 340g", "Corned beef, 340g tin.", 22.00, 26.00, 60, 15, True),
        ("Canned Tomatoes 400g", "Chopped tomatoes in juice, 400g tin.", 9.00, 11.00, 80, 20, True),
        ("Canned Baked Beans 400g", "Baked beans in tomato sauce, 400g tin.", 10.00, 12.00, 70, 18, True),
        ("Canned Mackerel 155g", "Mackerel in tomato sauce, 155g tin.", 9.00, 11.00, 65, 15, True),
    ],
    "Beverages": [
        ("Malta Guinness 330ml", "Non-alcoholic malt drink, 330ml bottle.", 9.00, 11.00, 90, 20, True),
        ("Tampico Juice 1L", "Tropical fruit juice drink, 1 litre.", 14.00, 17.00, 60, 15, True),
        ("Ribena Blackcurrant 1L", "Blackcurrant fruit juice drink, 1 litre.", 18.00, 22.00, 45, 12, True),
        ("Vimto Juice 1L", "Fruit-flavoured juice drink, 1 litre.", 15.00, 18.00, 50, 12, True),
    ],
    "Water & Soft Drinks": [
        ("Coca-Cola 500ml", "Chilled cola soft drink, 500ml bottle.", 10.00, 12.00, 50, 10, True),
        ("Fanta Orange 500ml", "Chilled orange-flavoured soft drink, 500ml bottle.", 10.00, 12.00, 40, 10, True),
        ("Bottled Water 1.5L", "Still drinking water, 1.5 litre bottle.", 5.00, 6.00, 80, 15, True),
        ("Sprite 500ml", "Chilled lemon-lime soft drink, 500ml bottle.", 10.00, 12.00, 45, 10, True),
        ("Bottled Water 500ml", "Still drinking water, 500ml bottle, single serve.", 3.00, 4.00, 100, 20, True),
    ],
    "Dairy Products": [
        ("Fresh Milk 1L", "Pasteurized fresh cow milk, 1 litre.", 20.00, 24.00, 40, 10, True),
        ("Powdered Milk 400g", "Full cream powdered milk, 400g tin.", 28.00, 33.00, 60, 15, True),
        ("Evaporated Milk 170g", "Evaporated milk, 170g tin.", 6.00, 8.00, 90, 20, True),
        ("Butter 250g", "Salted dairy butter, 250g pack.", 24.00, 28.00, 35, 10, True),
        ("Cheese Spread 200g", "Processed cheese spread, 200g tub.", 20.00, 24.00, 30, 8, True),
    ],
    "Bread & Bakery": [
        ("Sliced White Bread 600g", "Fresh sliced white loaf, 600g.", 12.00, 14.00, 40, 15, True),
        ("Whole Wheat Bread 600g", "Fresh sliced whole wheat loaf, 600g.", 14.00, 16.00, 30, 10, True),
        ("Dinner Rolls Pack of 6", "Soft dinner rolls, pack of 6.", 10.00, 12.00, 35, 10, True),
        ("Meat Pie Pack of 4", "Savoury meat pies, pack of 4.", 18.00, 21.00, 25, 8, True),
        ("Doughnuts Pack of 6", "Fresh glazed doughnuts, pack of 6.", 15.00, 18.00, 25, 8, True),
    ],
    "Biscuits & Snacks": [
        ("Digestive Biscuits 200g", "Wholewheat digestive biscuits, 200g pack.", 9.00, 11.00, 60, 15, True),
        ("Cream Crackers 200g", "Plain cream crackers, 200g pack.", 8.00, 10.00, 55, 15, True),
        ("Chin Chin Snack Pack 250g", "Sweet fried pastry snack, 250g pack.", 11.00, 13.00, 45, 12, True),
        ("Plantain Chips 150g", "Crispy fried plantain chips, 150g pack.", 8.00, 10.00, 70, 18, True),
        ("Groundnut Snack Pack 200g", "Roasted salted groundnuts, 200g pack.", 7.00, 9.00, 65, 15, True),
    ],
    "Tea & Coffee": [
        ("Lipton Tea Bags Pack of 25", "Black tea bags, pack of 25.", 12.00, 15.00, 60, 15, True),
        ("Green Tea Bags Pack of 25", "Green tea bags, pack of 25.", 15.00, 18.00, 40, 10, True),
        ("Instant Coffee 200g", "Instant coffee granules, 200g jar.", 30.00, 35.00, 35, 10, True),
        ("Milo 400g", "Chocolate malt drink powder, 400g tin.", 26.00, 30.00, 55, 15, True),
        ("Ovaltine 400g", "Malted milk drink powder, 400g tin.", 27.00, 31.00, 30, 8, True),
    ],
    "Frozen Foods": [
        ("Frozen Chicken Drumsticks 1kg", "Frozen chicken drumsticks, 1kg pack.", 45.00, 52.00, 30, 10, True),
        ("Frozen Fish (Bonga) 1kg", "Frozen bonga fish, 1kg pack.", 25.00, 30.00, 40, 12, True),
        ("Frozen Mixed Vegetables 500g", "Frozen mixed vegetables, 500g pack.", 18.00, 22.00, 35, 10, True),
        ("Frozen French Fries 1kg", "Frozen potato fries, 1kg pack.", 22.00, 26.00, 25, 8, True),
        ("Ice Cream Tub 1L", "Vanilla ice cream, 1 litre tub.", 35.00, 42.00, 20, 6, True),
    ],
    "Personal Care": [
        ("Bar Soap Pack of 3", "Antibacterial bar soap, pack of 3.", 9.00, 11.00, 90, 20, True),
        ("Body Lotion 400ml", "Moisturizing body lotion, 400ml bottle.", 18.00, 22.00, 50, 12, True),
        ("Shower Gel 250ml", "Refreshing shower gel, 250ml bottle.", 15.00, 18.00, 45, 12, True),
        ("Toothpaste 100ml", "Fluoride toothpaste, 100ml tube.", 10.00, 12.00, 80, 20, True),
        ("Toothbrush Pack of 2", "Medium-bristle toothbrushes, pack of 2.", 6.00, 8.00, 70, 18, True),
    ],
    "Toiletries": [
        ("Toilet Tissue Pack of 4", "Soft toilet tissue rolls, pack of 4.", 12.00, 15.00, 70, 18, True),
        ("Sanitary Pads Pack of 10", "Absorbent sanitary pads, pack of 10.", 14.00, 17.00, 60, 15, True),
        ("Shaving Razor Pack of 3", "Disposable shaving razors, pack of 3.", 8.00, 10.00, 50, 12, True),
        ("Deodorant Spray 150ml", "Long-lasting deodorant spray, 150ml.", 16.00, 19.00, 45, 12, True),
        ("Hand Sanitizer 250ml", "Alcohol-based hand sanitizer, 250ml.", 12.00, 15.00, 60, 15, True),
    ],
    "Baby Products": [
        ("Baby Diapers Pack of 30 (Size 3)", "Disposable baby diapers, size 3, pack of 30.", 45.00, 52.00, 40, 10, True),
        ("Baby Formula 400g", "Infant milk formula, 400g tin.", 60.00, 68.00, 30, 8, True),
        ("Baby Wipes Pack of 80", "Gentle baby wipes, pack of 80.", 15.00, 18.00, 55, 12, True),
        ("Baby Lotion 200ml", "Gentle moisturizing baby lotion, 200ml.", 14.00, 17.00, 40, 10, True),
        ("Baby Cereal 250g", "Fortified infant cereal, 250g pack.", 22.00, 26.00, 35, 10, True),
    ],
    "Cleaning Supplies": [
        ("Liquid Detergent 1L", "Multi-surface liquid detergent, 1 litre.", 16.00, 19.00, 60, 15, True),
        ("Bar Washing Soap Pack of 3", "Laundry bar soap, pack of 3.", 10.00, 12.00, 70, 18, True),
        ("Bleach 1L", "Household bleach, 1 litre bottle.", 9.00, 11.00, 55, 15, True),
        ("Dishwashing Liquid 500ml", "Grease-cutting dishwashing liquid, 500ml.", 12.00, 15.00, 60, 15, True),
        ("All-Purpose Cleaner Spray 500ml", "Multi-surface cleaner spray, 500ml.", 14.00, 17.00, 45, 12, True),
    ],
    "Household Essentials": [
        ("Matches Pack of 10 Boxes", "Safety matches, pack of 10 boxes.", 5.00, 6.00, 80, 20, True),
        ("Candles Pack of 6", "Household candles, pack of 6.", 8.00, 10.00, 60, 15, True),
        ("Insecticide Spray 300ml", "Insect-killing spray, 300ml can.", 18.00, 22.00, 40, 10, True),
        ("Trash Bags Roll of 30", "Heavy-duty trash bags, roll of 30.", 12.00, 15.00, 50, 12, True),
        ("Kitchen Foil Roll", "Aluminium kitchen foil, standard roll.", 10.00, 12.00, 45, 12, True),
    ],
    "Stationery": [
        ("Exercise Books Pack of 5", "Ruled exercise books, pack of 5.", 8.00, 10.00, 70, 18, True),
        ("Ballpoint Pens Pack of 10", "Blue ink ballpoint pens, pack of 10.", 6.00, 8.00, 80, 20, True),
        ("A4 Printing Paper Ream", "A4 printing paper, 500 sheets.", 25.00, 30.00, 40, 10, True),
        ("Pencils Pack of 12", "HB graphite pencils, pack of 12.", 5.00, 7.00, 60, 15, True),
        ("Correction Fluid", "White correction fluid, single bottle.", 4.00, 5.00, 50, 12, True),
    ],
    "Health & Wellness": [
        ("Multivitamin Tablets Pack of 30", "Daily multivitamin supplement, 30 tablets.", 20.00, 24.00, 40, 10, True),
        ("Paracetamol Tablets Pack of 20", "Pain relief tablets, pack of 20.", 6.00, 8.00, 90, 20, True),
        ("Oral Rehydration Salts Pack of 10", "Rehydration salts sachets, pack of 10.", 10.00, 12.00, 60, 15, True),
        ("First Aid Plasters Pack of 20", "Adhesive plasters, pack of 20.", 7.00, 9.00, 55, 12, True),
        ("Antiseptic Liquid 250ml", "Antiseptic disinfectant liquid, 250ml.", 14.00, 17.00, 40, 10, True),
    ],
    "Confectionery": [
        ("Assorted Chocolate Bars Pack of 5", "Assorted milk chocolate bars, pack of 5.", 18.00, 22.00, 45, 12, True),
        ("Boiled Sweets 250g", "Assorted fruit-flavoured boiled sweets, 250g.", 9.00, 11.00, 60, 15, True),
        ("Chewing Gum Pack of 10", "Mint chewing gum, pack of 10.", 6.00, 8.00, 70, 18, True),
        ("Lollipops Pack of 20", "Assorted fruit lollipops, pack of 20.", 8.00, 10.00, 50, 12, True),
        ("Marshmallows 200g", "Soft vanilla marshmallows, 200g pack.", 10.00, 12.00, 35, 10, True),
    ],
}


class Command(BaseCommand):
    help = "Seeds a realistic ~100-product Sierra Leone retail catalog. Safe to re-run — never creates duplicates."

    @transaction.atomic
    def handle(self, *args, **options):
        cat_created = cat_skipped = 0
        sup_created = sup_skipped = 0
        prod_created = prod_updated = prod_skipped = 0

        # --- Categories ---------------------------------------------------
        category_map = {}
        for name in CATEGORIES:
            category, created = Category.objects.get_or_create(category_name=name)
            category_map[name] = category
            if created:
                cat_created += 1
            else:
                cat_skipped += 1

        # --- Suppliers ------------------------------------------------------
        supplier_map = {}
        for data in SUPPLIERS:
            supplier, created = Supplier.objects.get_or_create(
                supplier_name=data["supplier_name"],
                defaults={
                    "phone": data["phone"],
                    "email": data["email"],
                    "address": data["address"],
                },
            )
            supplier_map[data["supplier_name"]] = supplier
            if created:
                sup_created += 1
            else:
                sup_skipped += 1

        # --- Products ---------------------------------------------------
        for category_name, items in PRODUCTS_BY_CATEGORY.items():
            category = category_map[category_name]
            supplier_name = CATEGORY_SUPPLIER_MAP[category_name]
            supplier = supplier_map[supplier_name]

            for (name, description, unit_price, online_price, stock,
                 reorder, is_available_online) in items:

                product, created = Product.objects.get_or_create(
                    product_name=name,
                    defaults={
                        "category": category,
                        "supplier": supplier,
                        "description": description,
                        "unit_price": Decimal(str(unit_price)),
                        "online_price": Decimal(str(online_price)),
                        "quantity_in_stock": stock,
                        "reorder_level": reorder,
                        "is_active": True,
                        "is_available_online": is_available_online,
                    },
                )

                if created:
                    prod_created += 1
                    continue

                # Already exists (possibly entered manually) — only fill in
                # fields that are currently missing/blank. Never overwrite
                # a value that's already set.
                changed = False
                if product.category_id is None:
                    product.category = category
                    changed = True
                if product.supplier_id is None:
                    product.supplier = supplier
                    changed = True
                if not product.description:
                    product.description = description
                    changed = True
                if product.online_price is None:
                    product.online_price = Decimal(str(online_price))
                    changed = True

                if changed:
                    product.save()
                    prod_updated += 1
                else:
                    prod_skipped += 1

        # --- Summary ---------------------------------------------------
        self.stdout.write(self.style.SUCCESS("\n=== Catalog Seed Summary ==="))
        self.stdout.write(f"Categories: {cat_created} created, {cat_skipped} already existed")
        self.stdout.write(f"Suppliers:  {sup_created} created, {sup_skipped} already existed")
        self.stdout.write(
            f"Products:   {prod_created} created, {prod_updated} updated, "
            f"{prod_skipped} already complete (skipped)"
        )
        self.stdout.write(self.style.SUCCESS("Done.\n"))