# Evaluation Notes — Which Data Supports Which Capability

This file documents which exported datasets support which implemented
system capabilities, and why. Only relationships confirmed from the
actual implementation (model relationships and service-layer code
inspected during export preparation) are documented here.

## products.csv

Dataset -> Product catalogue -> supports:
- Demand Forecasting (forecasting.DemandForecast has a required foreign
  key to Product)
- AI Shopping Assistant / shopping recommendations (operates over
  Product records)
- Visual product search (operates over Product records; embeddings are
  generated from product images, not included in this dataset)
- Inventory tracking (quantity_in_stock, reorder_level fields)

## customers.csv

Dataset -> Synthetic customer base -> supports:
- Customer Intelligence Engine (customer_insights.CustomerInsightSnapshot
  has a required foreign key to OnlineCustomer)
- Smart Credit and Loyalty Assistant (credit_limit, credit_balance,
  trust_score fields live directly on this model)
- AI Shopping Assistant customer-facing personalisation

## online_orders.csv

Dataset -> Order-level transaction detail -> supports:
- Smart Credit and Loyalty Assistant (payment_method includes "credit";
  credit affordability is checked against OnlineCustomer.credit_balance
  at order time)
- Delivery/logistics evaluation (delivery_zone, delivery_status,
  delivery_method, delivery_fee fields)
- Customer Intelligence Engine (record_confirmed_order(), the single
  entry point for updating a customer's lifetime_spending,
  total_orders, and preferred_categories, is called once per confirmed
  OnlineOrder — confirmed by direct inspection of
  ecommerce/models.py)

## sales.csv + sale_items.csv

Dataset -> Full-catalogue transaction history -> supports:
- Demand Forecasting (forecasting.services.generate_forecasts_for_all()
  is the data source for DemandForecast; walk-in Sale/SaleItem records
  extend forecasting coverage to products that are not sold online,
  per the explicit design note in seed_retail_data.py)
- Sales analysis / top-seller and slow-mover reporting on the
  dashboard app

Note: Sale has no direct foreign key to OnlineCustomer. Customer-linked
transactions are reconstructed via online_orders.csv -> linked_sale_id,
not via sales.csv alone.

## stock_receipts.csv + inventory_adjustments.csv

Dataset -> Inventory movement history -> supports:
- Inventory intelligence / stock-level reporting
- Indirectly, Demand Forecasting: seed_retail_data.py inflates stock
  buffers via InventoryAdjustment specifically so historical sales
  generation would not be artificially constrained by stock-outs; this
  is a data-generation mechanism, not evaluation evidence for
  forecasting accuracy itself

## expenses.csv

Dataset -> Operating expense history -> supports:
- AI Business Advisor (expense trends are one of the inputs an advisor
  reviewing business health would consider; the advisor app's
  recommendation logic was not traced field-by-field for this note, so
  this relationship is stated at a general level, not a verified
  code-level dependency)

## demand_forecasts.csv

Dataset -> Forecast output records -> supports:
- Demand Forecasting: this is the direct evaluation evidence for this
  capability. Each row is a real output of
  forecasting.services (scikit-learn LinearRegression, per
  DemandForecast.model_version). Only the latest forecast per product
  is included; see README for why.

## customer_insights.csv

Dataset -> Generated customer-intelligence output -> supports:
- Customer Intelligence Engine: this is the direct evaluation evidence
  for this capability, not an intermediate/cache table. Each row is the
  output of customer_insights.services.generate_customer_insight(),
  confirmed by direct inspection of customer_insights/models.py
  (CustomerInsightSnapshot's docstring explicitly states it is only
  ever created via that function). Only the latest snapshot per
  customer is included; see README for why.

## customer_events.csv

Dataset -> Browsing behaviour input -> supports:
- Customer Intelligence Engine: confirmed as a direct input, not merely
  related data. customer_insights/services.py imports CustomerEvent
  and queries it directly when computing insight snapshots (confirmed
  by grep of that file during export preparation, not assumed from the
  model's docstring alone).

## What is NOT included in this dataset, and why

- CustomerEvent.session_key values and product-image embeddings for
  Visual Search are not included; embeddings are binary/derived data,
  not raw evaluation records, and were judged out of scope for a CSV
  export package.
- delivery.DeliveryZone records are referenced by ID in
  online_orders.csv but not exported as their own file, since they were
  not part of the originally agreed file list and are reference/lookup
  data rather than evaluation evidence in themselves.
- products.Category, products.Supplier, and expenses.ExpenseCategory
  are referenced by ID but not exported as separate lookup files, for
  the same reason.
- Full DemandForecast and CustomerInsightSnapshot history (523 and 173
  rows respectively in the live database, versus 122 and 170 in this
  export) is not included; see README for the reasoning.
