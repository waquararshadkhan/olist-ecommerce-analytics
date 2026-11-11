"""Step 5 analysis: how late deliveries hurt reviews, and where they come from.

Reads the dbt marts in olist.duckdb, prints every number quoted in
docs/findings.md and saves the charts to docs/images/.

Usage:  python analysis/analysis.py        (after `dbt build`)
"""
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.proportion import proportion_confint, proportions_ztest

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "images"
IMG.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(ROOT / "olist.duckdb"), read_only=True)
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)

# Delivered orders with a date, purchased Jan 2017 - Aug 2018 (see data_quality.md)
DELIVERED = """
    select * from marts.fct_orders
    where is_delivered_with_date and is_in_analysis_window
"""

BLUE, RED, GREY, DARK = "#2E6DB4", "#C8433A", "#B8BCC2", "#2B2F33"
plt.rcParams.update({
    "figure.dpi": 150, "font.size": 10, "axes.spines.top": False,
    "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlesize": 12,
    "axes.titlelocation": "left",
})


def header(text: str) -> None:
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


def top_n_or_other(series: pd.Series, n: int) -> pd.Series:
    keep = series.value_counts().head(n).index
    return series.where(series.isin(keep), "other")


def save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(IMG / name, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved docs/images/{name}")


# --------------------------------------------------------------------------- #
# Q1. Does a late delivery lower the review score, after controlling for
#     category, state, order value, size and how long delivery took?
# --------------------------------------------------------------------------- #
def q1_reviews(orders: pd.DataFrame) -> None:
    header("Q1  Late delivery vs review score")
    d = orders[orders.has_review].copy()
    d["bad"] = d.is_bad_review.astype(int)

    by_bucket = (d.groupby("lateness_bucket")
                  .agg(orders=("order_id", "size"), avg_score=("review_score", "mean"),
                       bad_rate=("bad", "mean")))
    print(by_bucket.round(3))

    late, on_time = d[d.is_late], d[~d.is_late]
    excess_bad = len(late) * (late.bad.mean() - on_time.bad.mean())
    print(f"\n  late share of orders:       {d.is_late.mean():.1%}")
    print(f"  late share of 1-2 star:     {late.bad.sum() / d.bad.sum():.1%}")
    print(f"  bad reviews caused by lateness (excess over on-time rate): "
          f"{excess_bad:,.0f} of {d.bad.sum():,} ({excess_bad / d.bad.sum():.1%})")

    # Consistency: does the drop appear inside every big category and state?
    top_cats = d.category.value_counts().head(15).index
    cat = d[d.category.isin(top_cats)].pivot_table(
        index="category", columns="is_late", values="review_score", aggfunc="mean")
    cat_drop = cat[False] - cat[True]
    st = d.groupby(["customer_state", "is_late"]).review_score.agg(["mean", "size"]).unstack()
    st = st[st[("size", True)] >= 50]
    st_drop = st[("mean", False)] - st[("mean", True)]
    print(f"\n  top-15 categories: drop ranges {cat_drop.min():.2f} to {cat_drop.max():.2f} stars "
          f"({(cat_drop > 1).sum()}/{len(cat_drop)} drop by more than 1 star)")
    print(f"  states with 50+ late orders ({len(st_drop)}): drop ranges "
          f"{st_drop.min():.2f} to {st_drop.max():.2f} stars")

    # Speed vs promise: same delivery time, late or not
    d["speed"] = pd.cut(d.delivery_days, [-1, 7, 14, 21, 30, 999],
                        labels=["0-7 days", "8-14", "15-21", "22-30", "30+"])
    speed = d.pivot_table(index="speed", columns="is_late", values="review_score",
                          aggfunc=["mean", "size"], observed=True)
    print("\n  avg score by delivery time, late vs on time:")
    print(speed.round(2))

    # Regression with controls
    d["log_value"] = np.log1p(d.order_value)
    d["cat"] = top_n_or_other(d.category, 30)
    ols = smf.ols("review_score ~ is_late + delivery_days + C(cat) + C(customer_state)"
                  " + log_value + item_count + is_multi_seller", data=d).fit(cov_type="HC1")
    lo, hi = ols.conf_int().loc["is_late[T.True]"]
    print(f"\n  OLS (controls: category, state, value, items, multi-seller, delivery days):")
    print(f"    late       {ols.params['is_late[T.True]']:+.2f} stars  (95% CI {lo:+.2f} to {hi:+.2f})")
    print(f"    +1 day     {ols.params['delivery_days']:+.3f} stars")
    print(f"    multi-seller order {ols.params['is_multi_seller[T.True]']:+.2f} stars")
    logit = smf.logit("bad ~ is_late + delivery_days + C(cat) + C(customer_state)"
                      " + log_value + item_count + is_multi_seller", data=d).fit(disp=0)
    odds = np.exp(logit.params["is_late[T.True]"])
    olo, ohi = np.exp(logit.conf_int().loc["is_late[T.True]"])
    print(f"  Logit: late orders have {odds:.1f}x the odds of a 1-2 star review "
          f"(95% CI {olo:.1f}-{ohi:.1f})")

    # Chart 1
    labels = ["On time", "1-3 days\nlate", "4-7 days\nlate", "8-14 days\nlate", "15+ days\nlate"]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    colors = [BLUE] + [RED] * 4
    bars = ax.bar(labels, by_bucket.bad_rate * 100, color=colors, width=0.62)
    for b, (_, r) in zip(bars, by_bucket.iterrows()):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5,
                f"{r.bad_rate:.0%}\n{r.avg_score:.1f}★", ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Share of 1-2 star reviews (%)")
    ax.set_title("One late day is enough: bad reviews jump from 9% to 32%")
    ax.text(0, -0.2, "Labels: share of 1-2 star reviews and average score. "
            "Delivered orders, Jan 2017 - Aug 2018.",
            transform=ax.transAxes, fontsize=8, color="grey")
    save(fig, "01_lateness_vs_reviews.png")


# --------------------------------------------------------------------------- #
# Q2. Is it the seller or the courier?
# --------------------------------------------------------------------------- #
def q2_cause(orders: pd.DataFrame) -> None:
    header("Q2  Seller or courier?")
    d = orders[~orders.has_timestamp_anomaly & orders.seller_missed_ship_limit.notna()].copy()
    stages = d.groupby("is_late").agg(
        orders=("order_id", "size"),
        median_handling_days=("seller_handling_days", "median"),
        median_carrier_days=("carrier_days", "median"),
        median_promised_days=("promised_days", "median"),
        missed_ship_limit=("seller_missed_ship_limit", "mean"),
        median_distance_km=("distance_km", "median"),
        same_state=("is_same_state", "mean"),
    )
    print(stages.round(2))
    late = d[d.is_late]
    seller_share = late.seller_missed_ship_limit.mean()
    print(f"\n  late orders where the seller shipped on time: {1 - seller_share:.1%}")
    print(f"  late orders where the seller missed its ship-by date: {seller_share:.1%}")
    rate = d.groupby("seller_missed_ship_limit").is_late.mean()
    print(f"  late rate if seller ships on time: {rate[False]:.1%}; "
          f"if seller misses ship-by date: {rate[True]:.1%}")

    monthly = (orders.groupby("purchase_month")
                     .agg(orders=("order_id", "size"), late_rate=("is_late", "mean"),
                          promised=("promised_days", "median"), actual=("delivery_days", "median")))
    print("\n  monthly late rate:")
    print(monthly.round(3).to_string())

    # Chart 2: where the time goes
    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    rows = [("Late orders", stages.loc[True]), ("On-time orders", stages.loc[False])]
    for y, (label, r) in enumerate(rows):
        ax.barh(y, r.median_handling_days, color=GREY, height=0.5)
        ax.barh(y, r.median_carrier_days, left=r.median_handling_days,
                color=RED if label.startswith("Late") else BLUE, height=0.5)
        ax.text(r.median_handling_days / 2, y, f"{r.median_handling_days:.1f}d",
                ha="center", va="center", fontsize=9)
        ax.text(r.median_handling_days + r.median_carrier_days / 2, y,
                f"courier {r.median_carrier_days:.1f}d", ha="center", va="center",
                fontsize=9, color="white", fontweight="bold")
    ax.set_yticks([0, 1], [r[0] for r in rows])
    ax.set_xlabel("Median days (grey = seller handling, colour = courier)")
    ax.set_title(f"{1 - seller_share:.0%} of late orders left the seller on time; "
                 "the courier leg is what blows up")
    save(fig, "02_where_the_time_goes.png")

    # Chart 3: monthly late rate
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    x = monthly.index.astype(str).str[:7]
    ax.bar(x, monthly.late_rate * 100, color=[RED if v > 0.10 else BLUE for v in monthly.late_rate])
    ax.set_ylabel("Late deliveries (%)")
    ax.set_title("Lateness is not steady: three months drive the problem")
    ax.tick_params(axis="x", rotation=60, labelsize=8)
    for i, (m, r) in enumerate(monthly.iterrows()):
        if r.late_rate > 0.10:
            ax.text(i, r.late_rate * 100 + 0.4, f"{r.late_rate:.0%}", ha="center", fontsize=8)
    save(fig, "03_monthly_late_rate.png")


# --------------------------------------------------------------------------- #
# Q3. Which regions and sellers?
# --------------------------------------------------------------------------- #
def q3_where(orders: pd.DataFrame) -> None:
    header("Q3  Which states and sellers?")
    st = (orders.groupby("customer_state")
                .agg(orders=("order_id", "size"), late=("is_late", "sum"),
                     late_rate=("is_late", "mean"), promised=("promised_days", "median"),
                     actual=("delivery_days", "median"), km=("distance_km", "median"),
                     score=("review_score", "mean")))
    st["share_of_orders"] = st.orders / st.orders.sum()
    st["share_of_late"] = st.late / st.late.sum()
    st = st.sort_values("late_rate", ascending=False)
    print(st.round(3).to_string())

    same = orders.groupby("is_same_state").is_late.mean()
    print(f"\n  late rate same-state: {same[True]:.1%}; cross-state: {same[False]:.1%}")
    km = pd.cut(orders.distance_km, [0, 100, 500, 1000, 2000, 9999],
                labels=["<100 km", "100-500", "500-1000", "1000-2000", "2000+"])
    print(orders.groupby(km, observed=True).agg(
        orders=("order_id", "size"), late_rate=("is_late", "mean"),
        promised=("promised_days", "median"), actual=("delivery_days", "median")).round(3))

    sellers = (orders.groupby("seller_id")
                     .agg(n=("order_id", "size"), late=("is_late", "sum"))
                     .sort_values("late", ascending=False))
    cum_late = sellers.late.cumsum() / sellers.late.sum()
    cum_orders = sellers.n.cumsum() / sellers.n.sum()
    print(f"\n  {len(sellers):,} sellers; {(sellers.late > 0).sum():,} had at least one late order")
    for k in (10, 50, 100, 200):
        print(f"  top {k:>3} sellers by late orders: {cum_late.iloc[k - 1]:.1%} of late orders, "
              f"{cum_orders.iloc[k - 1]:.1%} of orders")

    dim = con.execute("select * from marts.dim_sellers where has_enough_orders").df()
    print(f"\n  sellers with 30+ delivered orders: {len(dim)}")
    print(f"  corr(late rate, bad-review rate) = {dim.late_rate.corr(dim.bad_review_rate):.2f}")
    dim["band"] = pd.cut(dim.late_rate, [-0.01, 0.03, 0.06, 0.10, 0.15, 1],
                         labels=["0-3%", "3-6%", "6-10%", "10-15%", "15%+"])
    print(dim.groupby("band", observed=True).agg(
        sellers=("seller_id", "size"), orders=("order_count", "sum"),
        avg_score=("avg_review_score", "mean"), bad_rate=("bad_review_rate", "mean"),
        handling_days=("avg_handling_days", "mean")).round(2))

    # Chart 4: states
    big = st[st.orders >= 300].sort_values("late_rate")
    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    colors = [RED if s == "RJ" else (DARK if r > 0.10 else GREY)
              for s, r in zip(big.index, big.late_rate)]
    ax.barh(big.index, big.late_rate * 100, color=colors)
    rj = big.loc["RJ"]
    ax.annotate(f"RJ: {rj.share_of_orders:.0%} of orders, {rj.share_of_late:.0%} of late ones,\n"
                f"only ~{rj.km:.0f} km from sellers",
                xy=(rj.late_rate * 100, list(big.index).index("RJ")),
                xytext=(13.5, list(big.index).index("RJ") - 5), fontsize=9,
                arrowprops=dict(arrowstyle="->", color=RED), color=RED)
    ax.axvline(orders.is_late.mean() * 100, color="grey", ls="--", lw=1)
    ax.text(orders.is_late.mean() * 100 + 0.2, 0, "overall", color="grey", fontsize=8)
    ax.set_xlabel("Late deliveries (%)")
    ax.set_title("Rio de Janeiro and the North-East get late orders most often")
    ax.text(0, -0.1, "Customer states with 300+ delivered orders.",
            transform=ax.transAxes, fontsize=8, color="grey")
    save(fig, "04_late_rate_by_state.png")


# --------------------------------------------------------------------------- #
# Q4. Does a late first order stop customers coming back?
# --------------------------------------------------------------------------- #
def q4_repeat() -> None:
    header("Q4  Late first order vs repeat purchase")
    # First orders before Mar 2018, so every customer has 6+ months to come back
    d = con.execute("""
        select * from marts.dim_customers
        where first_order_in_analysis_window
          and first_order_was_late is not null
          and first_order_at < '2018-03-01'
    """).df()
    g = d.groupby("first_order_was_late").is_repeat_customer.agg(["sum", "size"])
    g["rate"] = g["sum"] / g["size"]
    z, p = proportions_ztest(g["sum"].values, g["size"].values)
    print(f"  customers: {len(d):,}; overall repeat rate {d.is_repeat_customer.mean():.2%}")
    for late, r in g.iterrows():
        lo, hi = proportion_confint(r["sum"], r["size"], method="wilson")
        print(f"  first order {'late   ' if late else 'on time'}: {r.rate:.2%} came back "
              f"(95% CI {lo:.2%}-{hi:.2%}, n={int(r['size']):,})")
    print(f"  two-proportion z-test: z={z:.2f}, p={p:.4f}")

    d["rep"] = d.is_repeat_customer.astype(int)
    d["logv"] = np.log1p(d.first_order_value)
    d["cat"] = top_n_or_other(d.first_order_category, 20)
    d["st"] = top_n_or_other(d.state, 15)
    m = smf.logit("rep ~ first_order_was_late + C(cat) + C(st) + logv + C(first_order_month)",
                  data=d).fit(disp=0)
    orr = np.exp(m.params["first_order_was_late[T.True]"])
    lo, hi = np.exp(m.conf_int().loc["first_order_was_late[T.True]"])
    print(f"  logit with controls: odds ratio {orr:.2f} (95% CI {lo:.2f}-{hi:.2f}), "
          f"p={m.pvalues['first_order_was_late[T.True]']:.3f}")

    # Chart 5
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    labels = ["First order\non time", "First order\nlate"]
    rates = [g.loc[False, "rate"] * 100, g.loc[True, "rate"] * 100]
    cis = [proportion_confint(g.loc[k, "sum"], g.loc[k, "size"], method="wilson") for k in (False, True)]
    err = [[r - lo * 100 for r, (lo, _) in zip(rates, cis)],
           [hi * 100 - r for r, (_, hi) in zip(rates, cis)]]
    ax.bar(labels, rates, color=[BLUE, RED], width=0.5, yerr=err, capsize=5)
    for i, (r, (_, hi)) in enumerate(zip(rates, cis)):
        ax.text(i, hi * 100 + 0.15, f"{r:.1f}%", ha="center", va="bottom",
                fontsize=10, fontweight="bold")
    ax.set_ylim(0, 5.5)
    ax.set_ylabel("Customers who ordered again (%)")
    ax.set_title("A late first order: fewer come back,\nbut almost nobody comes back anyway")
    save(fig, "05_repeat_after_first_order.png")


if __name__ == "__main__":
    orders = con.execute(DELIVERED).df()
    print(f"Delivered orders in analysis window: {len(orders):,}")
    q1_reviews(orders)
    q2_cause(orders)
    q3_where(orders)
    q4_repeat()
    con.close()
