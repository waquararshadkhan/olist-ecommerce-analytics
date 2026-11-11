"""Olist delivery & reviews dashboard.

Run locally:  streamlit run app/streamlit_app.py
Data:         app/data/orders.parquet (made by app/export_data.py from the dbt marts)
"""
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA = Path(__file__).parent / "data" / "orders.parquet"
BLUE, RED, GREY = "#2E6DB4", "#C8433A", "#B8BCC2"
BUCKET_LABELS = {
    "0 on time": "On time",
    "1 late 1-3 days": "1-3 days late",
    "2 late 4-7 days": "4-7 days late",
    "3 late 8-14 days": "8-14 days late",
    "4 late 15+ days": "15+ days late",
}
MIN_SELLER_ORDERS = 30

st.set_page_config(page_title="Olist: Late Deliveries & Reviews", page_icon="📦", layout="wide")


@st.cache_data
def load() -> pd.DataFrame:
    df = pd.read_parquet(DATA)
    df["purchase_month"] = pd.to_datetime(df["purchase_month"])
    df["bucket"] = df["lateness_bucket"].map(BUCKET_LABELS)
    return df


def pct(x: float) -> str:
    return "–" if pd.isna(x) else f"{x:.1%}"


orders = load()

# ------------------------------------------------------------------ filters
st.sidebar.header("Filters")
months = sorted(orders.purchase_month.dt.strftime("%Y-%m").unique())
start, end = st.sidebar.select_slider("Purchase month", options=months, value=(months[0], months[-1]))
states = st.sidebar.multiselect("Customer state", sorted(orders.customer_state.unique()),
                                placeholder="All states")
top_categories = orders.category.value_counts().index.tolist()
categories = st.sidebar.multiselect("Category", top_categories, placeholder="All categories")
st.sidebar.caption("Delivered orders purchased Jan 2017 – Aug 2018. "
                   "'Late' = delivered after the date promised at checkout.")

mask = orders.purchase_month.dt.strftime("%Y-%m").between(start, end)
if states:
    mask &= orders.customer_state.isin(states)
if categories:
    mask &= orders.category.isin(categories)
df = orders[mask]
reviewed = df[df.has_review]

st.title("📦 Late deliveries & review scores")
st.markdown("How much do late deliveries hurt Olist's reviews, and where do they come from? "
            "Full write-up: `docs/findings.md`.")

if df.empty:
    st.warning("No orders match these filters.")
    st.stop()

# ------------------------------------------------------------------ KPIs
late_bad_share = (reviewed.is_late & reviewed.is_bad_review).sum() / max(reviewed.is_bad_review.sum(), 1)
k = st.columns(5)
k[0].metric("Delivered orders", f"{len(df):,}")
k[1].metric("Late rate", pct(df.is_late.mean()))
k[2].metric("Avg review score", f"{reviewed.review_score.mean():.2f} ★")
k[3].metric("1–2 star reviews", pct(reviewed.is_bad_review.mean()))
k[4].metric("…of which from late orders", pct(late_bad_share),
            help="Share of all 1–2 star reviews that came from late orders")

tab_reviews, tab_trend, tab_regions, tab_cause, tab_sellers = st.tabs(
    ["Reviews", "Trend", "Regions", "Seller vs courier", "Sellers"])

# ------------------------------------------------------------------ reviews
with tab_reviews:
    by_bucket = (reviewed.groupby("bucket")
                         .agg(orders=("order_id", "size"), score=("review_score", "mean"),
                              bad=("is_bad_review", "mean"))
                         .reindex(BUCKET_LABELS.values()).dropna())
    c1, c2 = st.columns(2)
    fig = px.bar(by_bucket, x=by_bucket.index, y=by_bucket.bad * 100,
                 text=[f"{b:.0%}<br>{s:.1f}★" for b, s in zip(by_bucket.bad, by_bucket.score)],
                 color=by_bucket.index == "On time",
                 color_discrete_map={True: BLUE, False: RED})
    fig.update_layout(title="Share of 1–2 star reviews by lateness", showlegend=False,
                      xaxis_title=None, yaxis_title="1–2 star reviews (%)", yaxis_range=[0, 100])
    c1.plotly_chart(fig, use_container_width=True)

    speed = reviewed.assign(speed=pd.cut(reviewed.delivery_days, [-1, 7, 14, 21, 30, 999],
                                         labels=["0-7", "8-14", "15-21", "22-30", "30+"]))
    sp = (speed.groupby(["speed", "is_late"], observed=True).review_score.mean()
               .reset_index().replace({"is_late": {True: "Late", False: "On time"}}))
    fig = px.bar(sp, x="speed", y="review_score", color="is_late", barmode="group",
                 color_discrete_map={"Late": RED, "On time": BLUE},
                 labels={"speed": "Days to deliver", "review_score": "Avg score", "is_late": ""})
    fig.update_layout(title="Same delivery time: late orders still score far lower",
                      yaxis_range=[1, 5])
    c2.plotly_chart(fig, use_container_width=True)
    st.caption("Customers judge the delivery against the promised date, not raw speed.")

# ------------------------------------------------------------------ trend
with tab_trend:
    monthly = (df.groupby("purchase_month")
                 .agg(orders=("order_id", "size"), late=("is_late", "mean"))
                 .reset_index())
    m_scores = reviewed.groupby("purchase_month").review_score.mean().reset_index()
    monthly = monthly.merge(m_scores, on="purchase_month", how="left")
    fig = go.Figure()
    fig.add_bar(x=monthly.purchase_month, y=monthly.late * 100, name="Late rate (%)",
                marker_color=[RED if v > 0.10 else BLUE for v in monthly.late])
    fig.add_scatter(x=monthly.purchase_month, y=monthly.review_score, name="Avg score",
                    yaxis="y2", mode="lines+markers", line_color="#2B2F33")
    fig.update_layout(title="Monthly late rate vs average review score",
                      yaxis=dict(title="Late rate (%)"),
                      yaxis2=dict(title="Avg score", overlaying="y", side="right", range=[3, 5]),
                      legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("When the late rate spikes (red), the average score drops in the same month.")

# ------------------------------------------------------------------ regions
with tab_regions:
    by_state = (df.groupby("customer_state")
                  .agg(orders=("order_id", "size"), late_orders=("is_late", "sum"),
                       late_rate=("is_late", "mean"), promised=("promised_days", "median"),
                       actual=("delivery_days", "median"), km=("distance_km", "median"))
                  .join(reviewed.groupby("customer_state").review_score.mean().rename("avg_score")))
    by_state["share_of_orders"] = by_state.orders / by_state.orders.sum()
    by_state["share_of_late"] = by_state.late_orders / max(by_state.late_orders.sum(), 1)
    big = by_state[by_state.orders >= 100].sort_values("late_rate")
    c1, c2 = st.columns([3, 2])
    fig = px.bar(big, x=big.late_rate * 100, y=big.index, orientation="h",
                 color=big.late_rate > df.is_late.mean(),
                 color_discrete_map={True: RED, False: GREY},
                 labels={"x": "Late rate (%)", "y": ""})
    fig.update_layout(title="Late rate by customer state (100+ orders)", showlegend=False,
                      height=600)
    c1.plotly_chart(fig, use_container_width=True)
    c2.markdown("**Where the late orders are**")
    c2.dataframe(
        by_state.sort_values("late_orders", ascending=False)
                [["orders", "late_rate", "share_of_orders", "share_of_late", "promised", "actual", "avg_score"]],
        column_config={
            "late_rate": st.column_config.NumberColumn("Late rate", format="percent"),
            "share_of_orders": st.column_config.NumberColumn("% of orders", format="percent"),
            "share_of_late": st.column_config.NumberColumn("% of late", format="percent"),
            "promised": st.column_config.NumberColumn("Promised days", format="%d"),
            "actual": st.column_config.NumberColumn("Actual days", format="%d"),
            "avg_score": st.column_config.NumberColumn("Avg score", format="%.2f"),
        },
        height=560,
    )

# ------------------------------------------------------------------ cause
with tab_cause:
    timed = df[df.seller_missed_ship_limit.notna()]
    late = timed[timed.is_late]
    stages = timed.groupby("is_late")[["seller_handling_days", "carrier_days"]].median()
    c1, c2 = st.columns([3, 2])
    fig = go.Figure()
    for col, name, color in [("seller_handling_days", "Seller handling", GREY),
                             ("carrier_days", "Courier", RED)]:
        fig.add_bar(y=["On-time orders", "Late orders"],
                    x=[stages.loc[False, col] if False in stages.index else None,
                       stages.loc[True, col] if True in stages.index else None],
                    name=name, orientation="h", marker_color=color,
                    texttemplate="%{x:.1f} d", textposition="inside")
    fig.update_layout(barmode="stack", title="Median days with the seller vs the courier",
                      xaxis_title="Days", legend=dict(orientation="h", y=-0.25), height=320)
    c1.plotly_chart(fig, use_container_width=True)
    if len(late):
        c2.metric("Late orders shipped on time by the seller",
                  pct(1 - late.seller_missed_ship_limit.mean()))
        rate = timed.groupby("seller_missed_ship_limit").is_late.mean()
        c2.metric("Late rate when seller misses ship-by date", pct(rate.get(True)),
                  delta=f"vs {pct(rate.get(False))} when on time", delta_color="off")

# ------------------------------------------------------------------ sellers
with tab_sellers:
    sellers = (df.groupby("seller_id")
                 .agg(state=("seller_state", "first"), main_category=("category", lambda s: s.mode().iat[0]),
                      orders=("order_id", "size"), late_rate=("is_late", "mean"),
                      handling_days=("seller_handling_days", "mean"),
                      missed_ship_by=("seller_missed_ship_limit", "mean"),
                      avg_score=("review_score", "mean"), bad_rate=("is_bad_review", "mean")))
    sellers = sellers[sellers.orders >= MIN_SELLER_ORDERS].sort_values("late_rate", ascending=False)
    st.markdown(f"**{len(sellers):,} sellers with {MIN_SELLER_ORDERS}+ delivered orders** "
                "in the current filters, worst late rate first.")
    if len(sellers) >= 5:
        fig = px.scatter(sellers, x=sellers.late_rate * 100, y="avg_score", size="orders",
                         color="handling_days", color_continuous_scale="Reds",
                         hover_data={"state": True, "main_category": True, "orders": True},
                         labels={"x": "Late rate (%)", "avg_score": "Avg review score",
                                 "handling_days": "Handling days"})
        fig.update_layout(title="Sellers that deliver late get worse reviews", height=420)
        st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        sellers.reset_index(),
        column_config={
            "seller_id": st.column_config.TextColumn("Seller", width="small"),
            "late_rate": st.column_config.NumberColumn("Late rate", format="percent"),
            "handling_days": st.column_config.NumberColumn("Handling days", format="%.1f"),
            "missed_ship_by": st.column_config.NumberColumn("Missed ship-by", format="percent"),
            "avg_score": st.column_config.NumberColumn("Avg score", format="%.2f"),
            "bad_rate": st.column_config.NumberColumn("1–2 star", format="percent"),
        },
        hide_index=True,
        use_container_width=True,
    )
