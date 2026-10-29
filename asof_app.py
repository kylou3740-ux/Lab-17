
"""
FIN 43900 — Lab 17: Point-in-Time Audit
Run: py -m streamlit run asof_app.py
"""

from datetime import date
from io import StringIO

import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="Lab 17 — Point-in-Time Audit",
    layout="wide"
)

FRED_CSV = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
)

ALFRED_CSV = (
    "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
    "?id={}&vintage_date={}"
)

DEFAULT_SERIES = {
    "BAA": "Moody's Baa corporate bond yield",
    "FEDFUNDS": "Effective federal funds rate",
    "DGS10": "10-year Treasury yield",
    "MORTGAGE30US": "30-year fixed mortgage rate",
}


@st.cache_data(ttl=3600)
def download_data(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text))

    if len(df.columns) < 2:
        raise ValueError("Unexpected CSV format.")

    df = df.iloc[:, :2].copy()
    df.columns = ["date", "value"]

    df["date"] = pd.to_datetime(
        df["date"], errors="coerce"
    )
    df["value"] = pd.to_numeric(
        df["value"].replace(".", pd.NA),
        errors="coerce"
    )

    return (
        df.dropna(subset=["date"])
        .sort_values("date")
    )


def last_observation(df):
    valid = df.dropna(subset=["value"])

    if valid.empty:
        return None, None

    row = valid.iloc[-1]
    return row["date"], float(row["value"])


def count_revisions(historical, current):
    old = (
        historical.dropna(subset=["value"])
        .set_index("date")["value"]
    )
    new = (
        current.dropna(subset=["value"])
        .set_index("date")["value"]
    )

    comparison = pd.concat(
        [old.rename("old"), new.rename("new")],
        axis=1
    ).dropna()

    if comparison.empty:
        return 0

    return int(
        (
            (comparison["old"] - comparison["new"])
            .abs() > 1e-9
        ).sum()
    )


def fmt(value):
    if value is None or pd.isna(value):
        return "—"

    return f"{value:,.4f}".rstrip("0").rstrip(".")


st.title("Lab 17 — Point-in-Time Audit")

st.caption(
    "Data audit using FRED and ALFRED. "
    
)

with st.sidebar:
    st.header("Settings")

    selected = st.multiselect(
        "Select series",
        options=list(DEFAULT_SERIES.keys()),
        default=list(DEFAULT_SERIES.keys()),
        format_func=lambda sid:
            f"{sid} — {DEFAULT_SERIES[sid]}"
    )

    extra_id = st.text_input(
        "Add another FRED series ID",
        value="PAYEMS"
    ).strip().upper()

    start_date = st.date_input(
        "Chart start date",
        value=date(2020, 1, 1)
    )

    as_known_date = st.date_input(
        "As known on",
        value=date.today()
    )

series_ids = list(dict.fromkeys(
    selected + ([extra_id] if extra_id else [])
))

if not series_ids:
    st.info("Select at least one series.")
    st.stop()

st.write(f"**As known on:** {as_known_date.isoformat()}")

results = []

for series_id in series_ids:
    name = DEFAULT_SERIES.get(
        series_id,
        "All Employees: Total Nonfarm"
        if series_id == "PAYEMS"
        else series_id
    )

    st.subheader(f"{series_id} — {name}")

    try:
        with st.spinner(f"Loading {series_id}..."):
            current = download_data(
                FRED_CSV.format(series_id)
            )

            historical = download_data(
                ALFRED_CSV.format(
                    series_id,
                    as_known_date.isoformat()
                )
            )

        chart = current[
            (current["date"] >= pd.Timestamp(start_date))
            & current["value"].notna()
        ].set_index("date")[["value"]]

        if not chart.empty:
            st.line_chart(chart.rename(
                columns={"value": series_id}
            ))
        else:
            st.warning("No observations in the selected period.")

        old_date, old_value = last_observation(historical)
        new_date, new_value = last_observation(current)

        if old_date is not None:
            st.write(
                "**Last observation known then:** "
                f"{old_date:%Y-%m-%d} — {fmt(old_value)}"
            )
        else:
            st.write("**Last observation known then:** None")

        if new_date is not None:
            st.write(
                "**Latest observation today:** "
                f"{new_date:%Y-%m-%d} — {fmt(new_value)}"
            )
        else:
            st.write("**Latest observation today:** None")

        later_count = 0

        if old_date is not None:
            later_count = int(
                (
                    current.dropna(subset=["value"])["date"]
                    > old_date
                ).sum()
            )

        revisions = count_revisions(historical, current)

        results.append({
            "Series ID": series_id,
            "Last date known then":
                old_date.strftime("%Y-%m-%d")
                if old_date is not None else "None",
            "Value known then": fmt(old_value),
            "Latest date today":
                new_date.strftime("%Y-%m-%d")
                if new_date is not None else "None",
            "Latest value today": fmt(new_value),
            "Later observations": later_count,
            "Overlapping values revised": revisions,
            "FRED page":
                f"https://fred.stlouisfed.org/series/{series_id}"
        })

        st.markdown(
            f"[Open {series_id} on FRED]"
            f"(https://fred.stlouisfed.org/series/{series_id})"
        )

    except Exception as exc:
        st.error(
            f"Could not load {series_id}: "
            f"{type(exc).__name__}: {exc}"
        )

st.header("Point-in-Time Comparison")

if results:
    st.dataframe(
        pd.DataFrame(results),
        use_container_width=True,
        hide_index=True
    )

st.caption(
    "An observation date is not necessarily its publication date. "
    
)
