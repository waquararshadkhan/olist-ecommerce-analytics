# Raw data quality report

Source: [Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
(9 CSV files, Sep 2016 – Oct 2018). Loaded with `scripts/load_raw.py`, checked with
`scripts/check_raw_quality.py`. Every column was loaded as text so nothing was coerced before
these checks.

## Row counts

| Table | Rows | Grain (one row per…) |
|---|---:|---|
| orders | 99,441 | order |
| customers | 99,441 | customer *per order* (see below) |
| order_items | 112,650 | item line within an order |
| order_payments | 103,886 | payment within an order |
| order_reviews | 99,224 | review–order pair |
| products | 32,951 | product |
| sellers | 3,095 | seller |
| geolocation | 1,000,163 | zip prefix × lat/lng point (many per zip) |
| category_translation | 71 | category |

## What is clean

- Primary keys are unique for orders, customers, order items, payments, products and sellers.
- **Every foreign key resolves**: no item, payment, review or order points to a missing parent.
- No prices ≤ 0; no review answered before it was created; no delivery before purchase.

## Issues found and how the staging layer will handle them

| # | Finding | Size | Decision |
|---|---|---:|---|
| 1 | `customer_id` is a **new id per order**. The real person is `customer_unique_id`. | 96,096 people, 2,997 with 2+ orders | All customer and repeat-purchase analysis uses `customer_unique_id`. |
| 2 | Orders with **no items** — almost all `unavailable` or `canceled`. | 775 | Kept in the orders model, excluded from revenue. |
| 3 | `review_id` is **not unique**: the same review is attached to several orders. `(review_id, order_id)` is unique. | 814 | Key reviews on `(review_id, order_id)`. |
| 4 | Some orders have **more than one review**. | 547 orders | Use the **latest** review per order for order-level scores. |
| 5 | Delivered orders missing a delivery date (8); non-delivered orders that have one (6). | 14 | Flag; on-time analysis uses only orders with both dates. |
| 6 | Handed to the carrier **before** approval or purchase. | 1,359 / 166 | Timestamp noise. Don't use carrier date for stage timings where it's out of order. |
| 7 | Delivered to customer before handed to the carrier. | 23 | Same — exclude from stage-level timings. |
| 8 | Deliveries over 60 days. | 298 | Kept (real, and part of the story) but checked as outliers. |
| 9 | **Thin edge months**: Sep–Dec 2016 (329 orders total, Nov 2016 missing) and Sep–Oct 2018 (20 orders). | — | Time-series analysis uses **Jan 2017 – Aug 2018** only. |
| 10 | Products with no category (and no name/description/photo counts). | 610 | Category set to `unknown`. |
| 11 | Two categories have no English translation: `pc_gamer`, `portateis_cozinha_e_preparadores_de_alimentos`. | 2 | Add translations manually in a dbt seed. |
| 12 | Product weight/dimensions missing (2) or zero (4). | 6 | Set to null; not used for freight analysis. |
| 13 | `payment_type = not_defined`; payment value 0; installments 0. | 3 / 9 / 2 | Keep; flag as data error. |
| 14 | Payments differ from item price + freight by more than R$1. | 249 orders | Revenue uses **item price + freight** (order_items), not payments. |
| 15 | Free shipping (freight = 0). | 383 items | Valid — keep. |
| 16 | Geolocation has 261,831 exact duplicate rows and many points per zip. 42 points fall outside Brazil. | — | Deduplicate, drop out-of-Brazil points, take one average point per zip prefix. |
| 17 | Zip prefixes not in geolocation: 157 customer, 7 seller. | — | Lat/lng left null for those. |
| 18 | City names have spelling variants (8,011 in geolocation vs 4,119 in customers). | — | Analyse by **state**, not city. |
| 19 | Review comments mostly empty (title 88%, message 59%). | — | Expected; scores are complete. |

## First look at the project question

Delivered orders with a review, split by whether they arrived after the estimated date:

| Arrived | Orders | Avg review score | Share of 1–2 star reviews |
|---|---:|---:|---:|
| Late | 6,381 | **2.27** | **62.4%** |
| On time or early | 89,443 | 4.29 | 9.2% |

Late delivery is linked to scores almost 2 points lower, and 1–2 star reviews are about 7× more
common. This is a raw, unadjusted comparison; the analysis step will check whether it holds
within categories, states and sellers.
