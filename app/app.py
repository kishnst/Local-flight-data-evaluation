"""
BLR (Kempegowda International Airport) Airline Performance Dashboard.
Run: streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import (
    WindowType,
    fetch_airline_rankings,
    fetch_congestion_by_hour,
    fetch_overview_kpis,
    fetch_peak_windows,
    fetch_route_performance,
    format_timestamp,
    list_airlines,
    search_flights,
    utc_now,
)

REFRESH_TTL = 60

st.set_page_config(
    page_title="BLR Airline Performance",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Cached data loaders (60s TTL)
# ---------------------------------------------------------------------------


@st.cache_data(ttl=REFRESH_TTL, show_spinner=False)
def cached_overview(window: str, airline: str) -> dict:
    return fetch_overview_kpis(window, airline)  # type: ignore[arg-type]


@st.cache_data(ttl=REFRESH_TTL, show_spinner=False)
def cached_rankings(window: str, airline: str) -> pd.DataFrame:
    return fetch_airline_rankings(window, airline)  # type: ignore[arg-type]


@st.cache_data(ttl=REFRESH_TTL, show_spinner=False)
def cached_routes(window: str, airline: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    return fetch_route_performance(window, airline)  # type: ignore[arg-type]


@st.cache_data(ttl=REFRESH_TTL, show_spinner=False)
def cached_congestion(window: str, airline: str) -> pd.DataFrame:
    return fetch_congestion_by_hour(window, airline)  # type: ignore[arg-type]


@st.cache_data(ttl=REFRESH_TTL, show_spinner=False)
def cached_airlines(window: str) -> list[str]:
    return list_airlines(window)  # type: ignore[arg-type]


@st.cache_data(ttl=REFRESH_TTL, show_spinner=False)
def cached_search(window: str, airline: str, query: str) -> pd.DataFrame:
    return search_flights(query, window, airline)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------


def style_rankings_table(df: pd.DataFrame):
    if df.empty or "OTA %" not in df.columns:
        return df

    def row_style(row: pd.Series) -> list[str]:
        ota = row.get("OTA %")
        if pd.isna(ota):
            return [""] * len(row)
        if ota > 85:
            return ["background-color: #d4edda"] * len(row)
        if ota >= 70:
            return ["background-color: #fff3cd"] * len(row)
        return ["background-color: #f8d7da"] * len(row)

    return df.style.apply(row_style, axis=1)  # type: ignore[return-value]


def plot_congestion_heatmap(hourly: pd.DataFrame) -> go.Figure:
    hours = list(range(24))
    rows: list[list[float | None]] = []
    y_labels: list[str] = []

    for leg, label in [("dep", "Departure (BLR)"), ("arr", "Arrival (BLR)")]:
        subset = hourly[hourly["leg"] == leg].set_index("hour")
        delays = [
            float(subset.loc[h, "avg_delay_min"]) if h in subset.index else None
            for h in hours
        ]
        rows.append(delays)
        y_labels.append(label)

    fig = go.Figure(
        data=go.Heatmap(
            z=rows,
            x=[f"{h:02d}" for h in hours],
            y=y_labels,
            colorscale="YlOrRd",
            zmin=0,
            zmax=60,
            colorbar=dict(title="Avg delay (min)"),
            hovertemplate="%{y}<br>Hour %{x}<br>Avg delay: %{z:.1f} min<extra></extra>",
        )
    )
    fig.update_layout(
        title="Hour of day vs average delay (0–60 min scale)",
        height=320,
        margin=dict(l=40, r=40, t=60, b=40),
        xaxis_title="Hour of day (UTC)",
    )
    return fig


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Filters")
    window: WindowType = st.radio(
        "Time window",
        options=["24h", "7d", "30d"],
        horizontal=True,
        help="Aggregation window for all metrics",
    )
    airline_options = cached_airlines(window)
    airline = st.selectbox("Airline", airline_options, index=0)
    st.divider()
    page = st.radio(
        "Navigate",
        [
            "Overview",
            "Airline Rankings",
            "Route Analysis",
            "Congestion Heatmap",
            "Flight Search",
        ],
    )
    st.caption(f"Auto-refresh every {REFRESH_TTL}s")

loaded_at = utc_now()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

header_l, header_r = st.columns([3, 1])
with header_l:
    st.title("BLR Airline Performance Dashboard")
    st.caption("Kempegowda International Airport (BLR) · Flight analytics")
with header_r:
    st.metric("Data window", window)
    st.caption(f"Last updated: {format_timestamp(loaded_at)}")

st.divider()

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

if page == "Overview":
    st.subheader("Overview")
    kpis = cached_overview(window, airline)

    c1, c2, c3, c4 = st.columns(4)
    ota = kpis["ota_pct"]
    avg_delay = kpis["avg_arrival_delay_min"]

    def _kpi_html(label: str, value: str, color: str) -> str:
        return (
            f'<div style="padding:0.5rem 0;">'
            f'<div style="color:#666;font-size:0.85rem;">{label}</div>'
            f'<div style="color:{color};font-size:2rem;font-weight:700;">{value}</div>'
            f"</div>"
        )

    ota_color_hex = (
        "#28a745"
        if ota is not None and ota > 85
        else "#dc3545"
        if ota is not None and ota < 75
        else "#f0ad4e"
        if ota is not None
        else "#666"
    )
    delay_color_hex = (
        "#28a745"
        if avg_delay is not None and avg_delay <= 15
        else "#dc3545"
        if avg_delay is not None and avg_delay >= 30
        else "#f0ad4e"
        if avg_delay is not None
        else "#666"
    )

    with c1:
        st.markdown(
            _kpi_html(
                "Overall On-Time Arrival %",
                f"{ota:.1f}%" if ota is not None else "N/A",
                ota_color_hex,
            ),
            unsafe_allow_html=True,
        )
        st.caption("Target: >85% green · <75% red")

    with c2:
        st.markdown(
            _kpi_html(
                "Average Arrival Delay",
                f"{avg_delay:.1f} min" if avg_delay is not None else "N/A",
                delay_color_hex,
            ),
            unsafe_allow_html=True,
        )
        st.caption("≤15 min green · ≥30 min red")

    with c3:
        st.metric(
            "Total Flights",
            f"{kpis['total_flights']:,}",
            help=f"Flights touching BLR in the selected {window} window",
        )

    with c4:
        st.metric(
            "Cancellation Rate %",
            f"{kpis['cancellation_rate_pct']:.2f}%",
            help="Cancelled / total flights in window",
        )

    st.info(
        f"Showing **{window}** window"
        + (f" for **{airline}**" if airline != "All Airlines" else " (all airlines)")
    )

elif page == "Airline Rankings":
    st.subheader("Airline Rankings")
    rankings = cached_rankings(window, airline)

    sort_col = st.selectbox("Sort by", ["Rank", "OTA %", "Flights", "Score"], index=0)
    ascending = sort_col == "Rank"
    if not rankings.empty:
        rankings = rankings.sort_values(sort_col, ascending=ascending, na_position="last")

    st.dataframe(
        style_rankings_table(rankings),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Rank": st.column_config.NumberColumn("Rank", width="small"),
            "Airline Name": st.column_config.TextColumn("Airline Name", width="medium"),
            "Flights": st.column_config.NumberColumn("Flights", format="%d"),
            "OTA %": st.column_config.NumberColumn("OTA %", format="%.1f"),
            "OTD %": st.column_config.NumberColumn("OTD %", format="%.1f"),
            "Avg Delay": st.column_config.NumberColumn("Avg Delay (min)", format="%.1f"),
            "Score": st.column_config.NumberColumn("Score", format="%.1f"),
        },
    )
    st.caption("Row color: green OTA >85%, yellow 70–85%, red <70%. Minimum 5 flights per airline.")

elif page == "Route Analysis":
    st.subheader("Route Analysis")
    best, worst = cached_routes(window, airline)

    left, right = st.columns(2)
    with left:
        st.markdown("#### Top 10 most punctual routes")
        st.dataframe(
            best,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Route": st.column_config.TextColumn("Route"),
                "Flights": st.column_config.NumberColumn("Flights"),
                "On-Time %": st.column_config.ProgressColumn(
                    "On-Time %", min_value=0, max_value=100, format="%.1f%%"
                ),
                "Avg Delay": st.column_config.NumberColumn("Avg Delay (min)", format="%.1f"),
            },
        )
    with right:
        st.markdown("#### Worst 5 performing routes")
        st.dataframe(
            worst,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Route": st.column_config.TextColumn("Route"),
                "Flights": st.column_config.NumberColumn("Flights"),
                "On-Time %": st.column_config.ProgressColumn(
                    "On-Time %", min_value=0, max_value=100, format="%.1f%%"
                ),
                "Avg Delay": st.column_config.NumberColumn("Avg Delay (min)", format="%.1f"),
            },
        )

elif page == "Congestion Heatmap":
    st.subheader("Congestion Heatmap")
    hourly = cached_congestion(window, airline)
    peaks = fetch_peak_windows(hourly)

    if hourly.empty:
        st.warning("No delay data available for the selected filters.")
    else:
        st.plotly_chart(plot_congestion_heatmap(hourly), use_container_width=True)
        p1, p2 = st.columns(2)
        with p1:
            st.metric("Peak departure window", peaks["departure"])
        with p2:
            st.metric("Peak arrival window", peaks["arrival"])

        with st.expander("Hourly detail table"):
            st.dataframe(hourly, use_container_width=True, hide_index=True)

elif page == "Flight Search":
    st.subheader("Flight Search")
    query = st.text_input(
        "Search by flight number, airline, or route",
        placeholder="e.g. 6E1419, IndiGo, BLR-DEL",
    )
    results = cached_search(window, airline, query)
    st.caption(f"Showing up to 20 most recent matches · {window} window")
    st.dataframe(
        results,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Flight": st.column_config.TextColumn("Flight"),
            "Airline": st.column_config.TextColumn("Airline"),
            "Route": st.column_config.TextColumn("Route"),
            "Status": st.column_config.TextColumn("Status"),
            "Dep Delay (min)": st.column_config.NumberColumn("Dep delay", format="%.1f"),
            "Arr Delay (min)": st.column_config.NumberColumn("Arr delay", format="%.1f"),
            "Sched Dep": st.column_config.DatetimeColumn("Sched dep"),
            "Actual Dep": st.column_config.DatetimeColumn("Actual dep"),
            "Sched Arr": st.column_config.DatetimeColumn("Sched arr"),
            "Actual Arr": st.column_config.DatetimeColumn("Actual arr"),
        },
    )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
footer_l, footer_r = st.columns([2, 1])
with footer_l:
    st.caption(
        "Data source: PostgreSQL `flight_kpi_base` · "
        f"Auto-refresh TTL {REFRESH_TTL}s"
    )
with footer_r:
    st.caption(f"Last updated: {loaded_at.astimezone().strftime('%H:%M:%S')}")
