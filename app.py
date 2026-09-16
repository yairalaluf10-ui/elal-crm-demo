"""EL AL CRM — מערכת לסוכני נסיעות. הרצה: streamlit run app.py"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

DB = Path(__file__).parent / "elal_crm.db"
NOW = datetime(2026, 9, 16, 9, 0)   # "עכשיו" של הדאטה הסינטטי

BLUE = "#2a78d6"      # צבע הסדרה היחידה בגרפים
STATUS_HE = {
    "Scheduled": "🟢 מתוכננת", "Boarding": "🟢 עלייה למטוס", "Delayed": "🟡 מעוכבת",
    "Departed": "🔵 בטיסה", "Landed": "⚪ נחתה", "Cancelled": "🔴 מבוטלת",
}

st.set_page_config(page_title="EL AL CRM", page_icon="✈️", layout="wide")
st.markdown("""<style>
  .stApp { direction: rtl; }
  [data-testid="stMetricValue"] { direction: ltr; text-align: right; }
</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def q(sql, params=()):
    with sqlite3.connect(DB) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def shekel(x):
    return f"₪{x:,.0f}"


def shekel_short(x):
    if x >= 1e6:
        return f"₪{x / 1e6:.1f}M"
    if x >= 1e3:
        return f"₪{x / 1e3:.0f}K"
    return f"₪{x:,.0f}"


# ── שאילתת הליבה: טיסה + תפוסה ─────────────────────────────────────
FLIGHTS_SQL = """
SELECT f.flight_id, f.flight_number, f.origin, f.destination,
       f.departure_time, f.arrival_time, f.aircraft_type, f.gate, f.status,
       f.seats_business + f.seats_economy          AS capacity,
       COUNT(b.booking_id)                         AS booked,
       COALESCE(SUM(b.price_paid), 0)              AS revenue
FROM flights f
LEFT JOIN bookings b ON b.flight_id = f.flight_id AND b.status <> 'Cancelled'
GROUP BY f.flight_id
"""


def load_flights():
    df = q(FLIGHTS_SQL)
    df["departure_time"] = pd.to_datetime(df["departure_time"])
    df["arrival_time"] = pd.to_datetime(df["arrival_time"])
    df["occupancy"] = (df["booked"] / df["capacity"]).clip(upper=1.0)
    return df


def style_fig(fig, height=320):
    fig.update_layout(height=height, margin=dict(t=10, b=10, l=10, r=10),
                      xaxis_title=None, yaxis_title=None,
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


# ── עמוד: דשבורד ────────────────────────────────────────────────────
def page_dashboard(fl):
    st.title("✈️ דשבורד תפעולי")
    st.caption(f"נכון ל־{NOW:%d/%m/%Y %H:%M}")

    today = fl[fl["departure_time"].dt.date == NOW.date()]
    upcoming = fl[(fl["departure_time"] >= NOW) & (fl["status"] != "Cancelled")]
    last30 = fl[(fl["departure_time"] < NOW) & (fl["departure_time"] >= NOW - timedelta(days=30))]
    needs_attention = int(((fl["departure_time"] >= NOW) &
                           fl["status"].isin(["Delayed", "Cancelled"])).sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("טיסות היום", len(today))
    c2.metric("נוסעים היום", f"{int(today['booked'].sum()):,}")
    c3.metric("תפוסה ממוצעת", f"{upcoming['occupancy'].mean():.0%}")
    c4.metric("הכנסות 30 יום", shekel_short(last30["revenue"].sum()),
              help=shekel(last30["revenue"].sum()))
    c5.metric("דורש טיפול", needs_attention, help="טיסות עתידיות מעוכבות או מבוטלות")

    st.divider()
    left, right = st.columns([3, 2])

    with left:
        st.subheader("נוסעים לפי יום")
        st.caption("שבוע אחורה · שבועיים קדימה")
        window = fl[(fl["status"] != "Cancelled") &
                    (fl["departure_time"] >= NOW - timedelta(days=7)) &
                    (fl["departure_time"] < NOW + timedelta(days=14))]
        daily = window.groupby(window["departure_time"].dt.date)["booked"].sum().reset_index()
        daily.columns = ["תאריך", "נוסעים"]
        fig = px.bar(daily, x="תאריך", y="נוסעים")
        fig.update_traces(marker_color=BLUE, marker_line_width=0)
        fig.add_vline(x=NOW.timestamp() * 1000, line_width=1,
                      line_dash="dot", line_color="#898781")
        style_fig(fig)
        fig.update_xaxes(showgrid=False, dtick=86400000 * 3, tickformat="%d/%m")
        fig.update_yaxes(gridcolor="#e1e0d9", zeroline=False)
        st.plotly_chart(fig, width="stretch")

    with right:
        st.subheader("יעדים מובילים (מ־TLV)")
        dest = (fl[(fl["origin"] == "TLV") & (fl["status"] != "Cancelled")]
                .groupby("destination")["booked"].sum()
                .nlargest(8).sort_values().reset_index())
        fig = px.bar(dest, x="booked", y="destination", orientation="h", text="booked")
        fig.update_traces(marker_color=BLUE, texttemplate="%{text:,}",
                          textposition="outside", cliponaxis=False)
        style_fig(fig)
        fig.update_layout(xaxis_visible=False)
        st.plotly_chart(fig, width="stretch")

    st.subheader("⚠️ טיסות שדורשות טיפול")
    issues = fl[(fl["departure_time"] >= NOW) &
                fl["status"].isin(["Delayed", "Cancelled"])].sort_values("departure_time")
    if issues.empty:
        st.success("אין טיסות עתידיות מעוכבות או מבוטלות.")
    else:
        show = issues.assign(status_he=issues["status"].map(STATUS_HE))[
            ["flight_number", "origin", "destination", "departure_time", "booked", "status_he"]]
        show.columns = ["טיסה", "מוצא", "יעד", "המראה", "נוסעים", "סטטוס"]
        st.dataframe(show, hide_index=True, width="stretch", column_config={
            "המראה": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})


# ── עמוד: לוח טיסות ─────────────────────────────────────────────────
def page_flights(fl):
    st.title("🛫 לוח טיסות")

    f1, f2, f3, f4 = st.columns(4)
    preset = f1.selectbox("טווח", ["היום", "7 הימים הקרובים", "30 הימים הקרובים", "היסטוריה", "הכל"])
    dests = f2.multiselect("יעד / מוצא", sorted(set(fl["origin"]) | set(fl["destination"])),
                           placeholder="הכל")
    statuses = f3.multiselect("סטטוס", list(STATUS_HE), format_func=lambda s: STATUS_HE[s],
                              placeholder="הכל")
    search = f4.text_input("חיפוש מספר טיסה", placeholder="LY315")

    d = fl
    if preset == "היום":
        d = d[d["departure_time"].dt.date == NOW.date()]
    elif preset == "7 הימים הקרובים":
        d = d[(d["departure_time"] >= NOW) & (d["departure_time"] < NOW + timedelta(days=7))]
    elif preset == "30 הימים הקרובים":
        d = d[(d["departure_time"] >= NOW) & (d["departure_time"] < NOW + timedelta(days=30))]
    elif preset == "היסטוריה":
        d = d[d["departure_time"] < NOW]
    if dests:
        d = d[d["origin"].isin(dests) | d["destination"].isin(dests)]
    if statuses:
        d = d[d["status"].isin(statuses)]
    if search:
        d = d[d["flight_number"].str.contains(search.strip(), case=False, na=False)]
    d = d.sort_values("departure_time").reset_index(drop=True)

    st.caption(f"{len(d):,} טיסות · {int(d['booked'].sum()):,} נוסעים · {shekel(d['revenue'].sum())}")

    view = d.assign(status_he=d["status"].map(STATUS_HE),
                    gate=d["gate"].fillna("—"),
                    route=d["origin"] + " → " + d["destination"])[
        ["flight_number", "route", "departure_time", "arrival_time", "aircraft_type",
         "gate", "status_he", "occupancy", "booked", "capacity", "revenue"]]
    view.columns = ["טיסה", "מסלול", "המראה", "נחיתה", "מטוס", "שער", "סטטוס",
                    "תפוסה", "נוסעים", "מושבים", "הכנסות"]

    event = st.dataframe(
        view, hide_index=True, width="stretch", height=430,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "המראה": st.column_config.DatetimeColumn(format="DD/MM HH:mm"),
            "נחיתה": st.column_config.DatetimeColumn(format="DD/MM HH:mm"),
            "תפוסה": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
            "הכנסות": st.column_config.NumberColumn(format="₪%d"),
        })

    rows = event.selection["rows"]
    if not rows:
        st.caption("בחר שורה בטבלה כדי לראות את פרטי הטיסה.")
        return

    f = d.iloc[rows[0]]
    st.divider()
    st.subheader(f"טיסה {f['flight_number']} · {f['origin']} → {f['destination']}")
    m = st.columns(5)
    m[0].metric("סטטוס", STATUS_HE[f["status"]])
    m[1].metric("המראה", f"{f['departure_time']:%d/%m %H:%M}")
    m[2].metric("שער", f["gate"] or "—")
    m[3].metric("תפוסה", f"{f['occupancy']:.0%}")
    m[3].caption(f"{f['booked']} מתוך {f['capacity']} מושבים")
    m[4].metric("הכנסות", shekel(f["revenue"]))
    st.info("רשימת הנוסעים וניהול ההזמנות יתווספו ב־Phase 3.")


# ── ניווט ───────────────────────────────────────────────────────────
if not DB.exists():
    st.error("מסד הנתונים לא נמצא. הרץ תחילה: `python generate_data.py`")
    st.stop()

flights = load_flights()
st.sidebar.title("✈️ EL AL CRM")
page = st.sidebar.radio("ניווט", ["📊 דשבורד", "🛫 לוח טיסות"], label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.caption("נתונים סינטטיים להדגמה בלבד.")

if page == "📊 דשבורד":
    page_dashboard(flights)
else:
    page_flights(flights)
