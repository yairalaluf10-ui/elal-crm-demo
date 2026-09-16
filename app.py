"""EL AL CRM — מערכת לסוכני נסיעות. הרצה: streamlit run app.py"""
import random
import sqlite3
import string
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
BOOKING_HE = {
    "Confirmed": "✅ מאושרת", "CheckedIn": "🛄 צ'ק-אין בוצע", "Completed": "⚪ הושלמה",
    "Cancelled": "🔴 מבוטלת", "NoShow": "⛔ לא הופיע",
}
TIER_HE = {
    "Basic": "Basic", "Silver": "🥈 Silver", "Gold": "🥇 Gold",
    "Platinum": "💎 Platinum", "Top Platinum": "👑 Top Platinum",
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


def write(sql, params=()):
    """כתיבה ל-DB. מנקה את ה-cache כדי שהמסכים יציגו את המצב החדש."""
    with sqlite3.connect(DB) as conn:
        conn.execute(sql, params)
        conn.commit()
    st.cache_data.clear()


def scalar(sql, params=()):
    with sqlite3.connect(DB) as conn:
        row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


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
       f.seats_business, f.seats_economy, f.price_business, f.price_economy,
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


# ── פעולות על הזמנות ────────────────────────────────────────────────
PNR_CHARS = string.ascii_uppercase + string.digits


def new_pnr():
    while True:
        pnr = "".join(random.choice(PNR_CHARS) for _ in range(6))
        if scalar("SELECT 1 FROM bookings WHERE pnr = ?", (pnr,)) is None:
            return pnr


def free_seat(flight_id, cabin, flight):
    """המושב הפנוי הראשון בתא המבוקש, או None אם התא מלא."""
    taken = set(q("SELECT seat FROM bookings WHERE flight_id = ? AND status <> 'Cancelled'",
                  (int(flight_id),))["seat"].dropna())
    if cabin == "Business":
        letters, rows = "ABCD", range(1, int(flight["seats_business"]) // 4 + 3)
    else:
        letters, rows = "ABCDEF", range(10, 10 + int(flight["seats_economy"]) // 6 + 3)
    for r in rows:
        for letter in letters:
            if f"{r}{letter}" not in taken:
                return f"{r}{letter}"
    return None


def seats_left(flight_id, cabin, flight):
    capacity = int(flight["seats_business"] if cabin == "Business" else flight["seats_economy"])
    used = scalar("SELECT COUNT(*) FROM bookings WHERE flight_id = ? AND cabin_class = ?"
                  " AND status <> 'Cancelled'", (int(flight_id), cabin)) or 0
    return capacity - used


def create_booking(customer_id, flight, cabin, baggage, notes):
    seat = free_seat(flight["flight_id"], cabin, flight)
    if seat is None:
        return None, "אין מושבים פנויים בתא זה."
    price = float(flight["price_business"] if cabin == "Business" else flight["price_economy"])
    pnr = new_pnr()
    write("""INSERT INTO bookings (pnr, customer_id, flight_id, booking_date, cabin_class,
                                   seat, baggage_count, price_paid, status, agent_notes)
             VALUES (?,?,?,?,?,?,?,?,'Confirmed',?)""",
          (pnr, int(customer_id), int(flight["flight_id"]), NOW.isoformat(sep=" "),
           cabin, seat, int(baggage), price, notes or None))
    return pnr, seat


def set_booking_status(booking_id, status):
    write("UPDATE bookings SET status = ? WHERE booking_id = ?", (status, int(booking_id)))


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

    st.markdown("##### 👥 רשימת נוסעים")
    pax = q("""SELECT b.pnr, c.first_name || ' ' || c.last_name AS name, c.passport,
                      c.matmid_tier, b.cabin_class, b.seat, b.baggage_count, b.status
               FROM bookings b JOIN customers c ON c.customer_id = b.customer_id
               WHERE b.flight_id = ?
               ORDER BY CASE b.cabin_class WHEN 'Business' THEN 0 ELSE 1 END, b.seat""",
            (int(f["flight_id"]),))

    name_filter = st.text_input("סינון לפי שם או דרכון", key="pax_filter", placeholder="כהן")
    if name_filter:
        needle = name_filter.strip()
        pax = pax[pax["name"].str.contains(needle, na=False) |
                  pax["passport"].str.contains(needle, na=False)]

    live = pax[pax["status"] != "Cancelled"]
    st.caption(f"{len(live):,} נוסעים · "
               f"{int((live['status'] == 'CheckedIn').sum()):,} עברו צ'ק-אין · "
               f"{int((live['cabin_class'] == 'Business').sum()):,} במחלקת עסקים · "
               f"{int((pax['status'] == 'Cancelled').sum()):,} ביטולים")

    show = pax.assign(cabin=pax["cabin_class"].map({"Business": "עסקים", "Economy": "תיירים"}),
                      tier=pax["matmid_tier"].map(TIER_HE),
                      status_he=pax["status"].map(BOOKING_HE))[
        ["pnr", "name", "passport", "tier", "cabin", "seat", "baggage_count", "status_he"]]
    show.columns = ["PNR", "שם", "דרכון", "מועדון", "מחלקה", "מושב", "כבודה", "סטטוס"]
    st.dataframe(show, hide_index=True, width="stretch", height=300)


# ── עמוד: לקוחות והזמנות ────────────────────────────────────────────
SEARCH_SQL = """
SELECT DISTINCT c.customer_id, c.first_name, c.last_name, c.email, c.phone,
       c.passport, c.country, c.matmid_tier, c.matmid_points
FROM customers c LEFT JOIN bookings b ON b.customer_id = c.customer_id
WHERE c.first_name || ' ' || c.last_name LIKE ?
   OR c.email LIKE ? OR c.passport LIKE ? OR b.pnr LIKE ?
ORDER BY c.last_name, c.first_name
LIMIT 50
"""


def flash(msg, kind="success"):
    st.session_state["flash"] = (kind, msg)
    st.rerun()


def show_flash():
    if "flash" in st.session_state:
        kind, msg = st.session_state.pop("flash")
        {"success": st.success, "warning": st.warning, "error": st.error}[kind](msg)


def page_customers(fl):
    st.title("👤 לקוחות והזמנות")
    show_flash()

    term = st.text_input("חיפוש לפי שם, אימייל, דרכון או PNR",
                         placeholder="כהן · user42@gmail.com · 12345678 · AB12CD")
    if not term.strip():
        st.caption("הקלד כדי לחפש לקוח.")
        return

    like = f"%{term.strip()}%"
    results = q(SEARCH_SQL, (like, like, like, like))
    if results.empty:
        st.warning("לא נמצא לקוח תואם.")
        return

    st.caption(f"{len(results)} תוצאות" + (" (50 הראשונות)" if len(results) == 50 else ""))
    listing = results.assign(name=results["first_name"] + " " + results["last_name"],
                             tier=results["matmid_tier"].map(TIER_HE))[
        ["name", "passport", "email", "phone", "country", "tier", "matmid_points"]]
    listing.columns = ["שם", "דרכון", "אימייל", "טלפון", "מדינה", "מועדון", "נקודות"]
    picked = st.dataframe(listing, hide_index=True, width="stretch", height=200,
                          on_select="rerun", selection_mode="single-row")

    rows = picked.selection["rows"]
    if not rows:
        st.caption("בחר לקוח מהרשימה.")
        return
    customer_card(results.iloc[rows[0]], fl)


def customer_card(cust, fl):
    cid = int(cust["customer_id"])
    st.divider()
    st.subheader(f"{cust['first_name']} {cust['last_name']}")
    st.caption(f"דרכון {cust['passport']} · {cust['phone']} · {cust['email']} · {cust['country']}")

    hist = q("""SELECT b.booking_id, b.pnr, f.flight_number, f.origin, f.destination,
                       f.departure_time, b.cabin_class, b.seat, b.baggage_count,
                       b.price_paid, b.status, b.agent_notes
                FROM bookings b JOIN flights f ON f.flight_id = b.flight_id
                WHERE b.customer_id = ?
                ORDER BY f.departure_time DESC""", (cid,))
    hist["departure_time"] = pd.to_datetime(hist["departure_time"])
    active = hist[hist["status"] != "Cancelled"]
    upcoming = active[active["departure_time"] >= NOW]

    k = st.columns(4)
    k[0].metric("מועדון", TIER_HE[cust["matmid_tier"]])
    k[1].metric("נקודות", f"{int(cust['matmid_points']):,}")
    k[2].metric("סה\"כ טיסות", len(active))
    k[3].metric("סה\"כ הוצאה", shekel(active["price_paid"].sum()))

    tab_hist, tab_new = st.tabs([f"🎫 הזמנות ({len(hist)})", "➕ הזמנה חדשה"])
    with tab_hist:
        booking_history(hist, upcoming)
    with tab_new:
        new_booking_form(cid, fl)


def booking_history(hist, upcoming):
    st.caption(f"{len(upcoming)} טיסות עתידיות")
    view = hist.assign(route=hist["origin"] + " → " + hist["destination"],
                       cabin=hist["cabin_class"].map({"Business": "עסקים", "Economy": "תיירים"}),
                       status_he=hist["status"].map(BOOKING_HE),
                       notes=hist["agent_notes"].fillna(""))[
        ["pnr", "flight_number", "route", "departure_time", "cabin", "seat",
         "baggage_count", "price_paid", "status_he", "notes"]]
    view.columns = ["PNR", "טיסה", "מסלול", "המראה", "מחלקה", "מושב",
                    "כבודה", "מחיר", "סטטוס", "הערות"]

    picked = st.dataframe(view, hide_index=True, width="stretch", height=280,
                          on_select="rerun", selection_mode="single-row",
                          column_config={
                              "המראה": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
                              "מחיר": st.column_config.NumberColumn(format="₪%d")})

    rows = picked.selection["rows"]
    if not rows:
        st.caption("בחר הזמנה כדי לבצע עליה פעולה.")
        return

    b = hist.iloc[rows[0]]
    st.markdown(f"**{b['pnr']}** · טיסה {b['flight_number']} · "
                f"{b['origin']} → {b['destination']} · {b['departure_time']:%d/%m/%Y %H:%M}")

    past = b["departure_time"] < NOW
    can_checkin = b["status"] == "Confirmed" and not past
    can_cancel = b["status"] in ("Confirmed", "CheckedIn") and not past

    c1, c2, _ = st.columns([1, 1, 3])
    if c1.button("🛄 בצע צ'ק-אין", disabled=not can_checkin, width="stretch"):
        set_booking_status(b["booking_id"], "CheckedIn")
        flash(f"בוצע צ'ק-אין להזמנה {b['pnr']} · מושב {b['seat']}.")
    if c2.button("🔴 בטל הזמנה", disabled=not can_cancel, width="stretch"):
        set_booking_status(b["booking_id"], "Cancelled")
        flash(f"הזמנה {b['pnr']} בוטלה. המושב {b['seat']} שוחרר.", "warning")

    if past:
        st.caption("הטיסה כבר יצאה — לא ניתן לשנות את ההזמנה.")
    elif b["status"] == "Cancelled":
        st.caption("ההזמנה מבוטלת.")


def new_booking_form(cid, fl):
    available = fl[(fl["departure_time"] >= NOW) & (fl["status"] != "Cancelled")]
    if available.empty:
        st.warning("אין טיסות עתידיות זמינות.")
        return

    c1, c2 = st.columns(2)
    dest = c1.selectbox("יעד", sorted(available["destination"].unique()))
    cabin = c2.radio("מחלקה", ["Economy", "Business"],
                     format_func=lambda x: "תיירים" if x == "Economy" else "עסקים",
                     horizontal=True)

    options = available[available["destination"] == dest].sort_values("departure_time")
    labels = {int(r.flight_id): f"{r.flight_number} · {r.origin} → {r.destination} · "
                                f"{r.departure_time:%d/%m/%Y %H:%M}"
              for r in options.itertuples()}
    flight_id = st.selectbox("טיסה", list(labels), format_func=lambda i: labels[i])
    flight = options[options["flight_id"] == flight_id].iloc[0]

    left = seats_left(flight_id, cabin, flight)
    price = float(flight["price_business"] if cabin == "Business" else flight["price_economy"])
    i1, i2 = st.columns(2)
    i1.metric("מושבים פנויים במחלקה", left)
    i2.metric("מחיר", shekel(price))

    baggage = st.number_input("מזוודות", min_value=0, max_value=3, value=1)
    notes = st.text_input("הערות סוכן", placeholder="ארוחה כשרה, כיסא גלגלים…")

    if st.button("✅ צור הזמנה", type="primary", disabled=left <= 0):
        pnr, seat = create_booking(cid, flight, cabin, baggage, notes)
        if pnr is None:
            st.error(seat)
        else:
            flash(f"נוצרה הזמנה **{pnr}** · טיסה {flight['flight_number']} · מושב {seat} · "
                  f"{shekel(price)}.")
    if left <= 0:
        st.warning("המחלקה מלאה. בחר מחלקה או טיסה אחרת.")


# ── ניווט ───────────────────────────────────────────────────────────
if not DB.exists():
    st.error("מסד הנתונים לא נמצא. הרץ תחילה: `python generate_data.py`")
    st.stop()

flights = load_flights()
st.sidebar.title("✈️ EL AL CRM")
page = st.sidebar.radio("ניווט", ["📊 דשבורד", "🛫 לוח טיסות", "👤 לקוחות והזמנות"],
                        label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.caption("נתונים סינטטיים להדגמה בלבד.")

if page == "📊 דשבורד":
    page_dashboard(flights)
elif page == "🛫 לוח טיסות":
    page_flights(flights)
else:
    page_customers(flights)
