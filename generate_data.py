"""גנרטור דאטה סינטטי למערכת ה-CRM של אל על.

הרצה:  python generate_data.py
יוצר את elal_crm.db מחדש (מוחק קיים) עם לקוחות, טיסות והזמנות.
"""
import random
import sqlite3
import string
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
DB_PATH = Path(__file__).parent / "elal_crm.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

N_CUSTOMERS = 8000
DAYS_BACK = 30
DAYS_FORWARD = 60
FLIGHTS_PER_DAY = (4, 8)

random.seed(SEED)
NOW = datetime(2026, 9, 16, 9, 0)

# יעד -> (שם, שעות טיסה, מקדם מחיר)
DESTINATIONS = {
    "JFK": ("ניו יורק", 11.5, 2.6), "EWR": ("ניוארק", 11.5, 2.5),
    "LAX": ("לוס אנג'לס", 14.5, 3.0), "MIA": ("מיאמי", 12.5, 2.7),
    "BOS": ("בוסטון", 11.0, 2.5), "LHR": ("לונדון", 5.0, 1.2),
    "CDG": ("פריז", 4.5, 1.1), "FCO": ("רומא", 3.5, 0.9),
    "MXP": ("מילאנו", 4.0, 1.0), "ATH": ("אתונה", 2.0, 0.6),
    "BER": ("ברלין", 4.0, 1.0), "MUC": ("מינכן", 3.8, 1.0),
    "AMS": ("אמסטרדם", 4.7, 1.1), "ZRH": ("ציריך", 4.0, 1.0),
    "VIE": ("וינה", 3.5, 0.9), "PRG": ("פראג", 3.5, 0.9),
    "BCN": ("ברצלונה", 4.8, 1.1), "MAD": ("מדריד", 5.2, 1.2),
    "BUD": ("בודפשט", 3.2, 0.8), "WAW": ("ורשה", 3.5, 0.9),
    "LCA": ("לרנקה", 1.0, 0.4), "DXB": ("דובאי", 3.3, 0.9),
    "BKK": ("בנגקוק", 10.0, 2.2), "NRT": ("טוקיו", 12.5, 2.8),
    "BOM": ("מומבאי", 6.5, 1.5), "MLE": ("מלדיביים", 8.0, 2.0),
    "TBS": ("טביליסי", 3.0, 0.8), "LIS": ("ליסבון", 6.0, 1.3),
}

# דגם -> (מושבי עסקים, מושבי תיירים, טווח שעות מקסימלי)
AIRCRAFT = [
    ("B737-800", 16, 138, 6.0),
    ("B737-900", 16, 156, 6.5),
    ("B787-8", 32, 206, 16.0),
    ("B787-9", 32, 250, 16.0),
    ("B777-200ER", 36, 243, 15.0),
]

FIRST_NAMES = ["דוד", "יוסף", "משה", "אברהם", "יצחק", "נועה", "תמר", "שירה", "מיכל", "רונית",
               "איתי", "עומר", "ליאור", "גיא", "אורי", "יעל", "דנה", "הילה", "מאיה", "עדי",
               "ניר", "אלון", "רועי", "עידן", "אסף", "שני", "ענבל", "רותם", "סיון", "כרמל"]
LAST_NAMES = ["כהן", "לוי", "מזרחי", "פרץ", "ביטון", "דהן", "אברהם", "פרידמן", "שפירא", "אזולאי",
              "גבאי", "חדד", "מלכה", "אוחיון", "ברוך", "שרון", "רוזנברג", "כץ", "אדלר", "בן דוד",
              "גולן", "הראל", "טל", "ניר", "סגל", "עמר", "פלד", "צור", "קפלן", "שמש"]
COUNTRIES = ["ישראל"] * 12 + ["ארה\"ב"] * 4 + ["צרפת", "בריטניה", "קנדה", "גרמניה", "רוסיה"]
TIERS = ["Basic"] * 50 + ["Silver"] * 25 + ["Gold"] * 15 + ["Platinum"] * 8 + ["Top Platinum"] * 2


def seat_labels(count, start_row, letters):
    """תוויות מושב ייחודיות: 1A, 1B, ... כמו במפת המושבים באפליקציה."""
    labels, row = [], start_row
    while len(labels) < count:
        for letter in letters:
            labels.append(f"{row}{letter}")
            if len(labels) == count:
                break
        row += 1
    return labels


def rand_pnr(used):
    chars = string.ascii_uppercase + string.digits
    while True:
        pnr = "".join(random.choice(chars) for _ in range(6))
        if pnr not in used:
            used.add(pnr)
            return pnr


def make_customers():
    rows, emails, passports = [], set(), set()
    for cid in range(1, N_CUSTOMERS + 1):
        fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        email = f"user{cid}@{random.choice(['gmail.com', 'walla.co.il', 'outlook.com', 'yahoo.com'])}"
        while email in emails:
            email = f"user{cid}x@gmail.com"
        emails.add(email)
        pp = f"{random.randint(10000000, 39999999)}"
        while pp in passports:
            pp = f"{random.randint(10000000, 39999999)}"
        passports.add(pp)
        tier = random.choice(TIERS)
        points = {"Basic": (0, 8000), "Silver": (8000, 30000), "Gold": (30000, 80000),
                  "Platinum": (80000, 200000), "Top Platinum": (200000, 500000)}[tier]
        birth = NOW - timedelta(days=random.randint(18 * 365, 80 * 365))
        created = NOW - timedelta(days=random.randint(1, 2500))
        rows.append((cid, fn, ln, email, f"05{random.randint(0,9)}-{random.randint(1000000,9999999)}",
                     pp, random.choice(COUNTRIES), birth.strftime("%Y-%m-%d"), tier,
                     random.randint(*points), created.strftime("%Y-%m-%d")))
    return rows


def make_flights():
    rows = []
    fid = 0
    used_numbers = {}
    day = NOW.date() - timedelta(days=DAYS_BACK)
    end = NOW.date() + timedelta(days=DAYS_FORWARD)
    while day <= end:
        for _ in range(random.randint(*FLIGHTS_PER_DAY)):
            dest = random.choice(list(DESTINATIONS))
            _, hours, price_factor = DESTINATIONS[dest]
            candidates = [a for a in AIRCRAFT if a[3] >= hours]
            ac, sb, se, _ = random.choice(candidates)
            outbound = random.random() < 0.5
            origin, destination = ("TLV", dest) if outbound else (dest, "TLV")

            if dest not in used_numbers:
                used_numbers[dest] = random.choice([1, 3, 5, 7]) * 100 + random.randint(1, 60)
            base_num = used_numbers[dest]
            flight_number = f"LY{base_num + (0 if outbound else 1):03d}"

            dep = datetime.combine(day, datetime.min.time()) + timedelta(
                hours=random.randint(0, 23), minutes=random.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]))
            arr = dep + timedelta(hours=hours, minutes=random.randint(0, 40))

            # סטטוס נגזר מהזמן ביחס ל"עכשיו"
            if random.random() < 0.02:
                status = "Cancelled"
            elif arr < NOW:
                status = "Landed"
            elif dep < NOW < arr:
                status = "Departed"
            elif dep - NOW < timedelta(minutes=60):
                status = "Boarding"
            elif random.random() < 0.08:
                status = "Delayed"
            else:
                status = "Scheduled"

            gate = None if origin != "TLV" else f"{random.choice('BCDEG')}{random.randint(1, 12)}"
            # מחירים בשקלים (₪)
            p_eco = round(1100 + 1050 * price_factor * random.uniform(0.8, 1.4), 2)
            p_biz = round(p_eco * random.uniform(2.8, 4.2), 2)

            fid += 1
            rows.append((fid, flight_number, origin, destination, dep.isoformat(sep=" "),
                         arr.isoformat(sep=" "), ac, sb, se, p_biz, p_eco, gate, status))
        day += timedelta(days=1)
    return rows


def make_bookings(customers, flights):
    rows = []
    used_pnr = set()
    bid = 0
    cust_ids = [c[0] for c in customers]
    for f in flights:
        fid, _, _, _, dep_s, _, _, sb, se, p_biz, p_eco, _, f_status = f
        dep = datetime.fromisoformat(dep_s)
        load = random.uniform(0.55, 0.95)
        n_eco = int(se * load)
        n_biz = int(sb * random.uniform(0.4, 0.95))
        # מושבים ייחודיים לכל תא — בלי הקצאה כפולה
        seat_pool_biz = random.sample(seat_labels(sb, 1, "ABCD"), n_biz)
        seat_pool_eco = random.sample(seat_labels(se, 10, "ABCDEF"), n_eco)

        for cabin, count, seats, price in (("Business", n_biz, seat_pool_biz, p_biz),
                                           ("Economy", n_eco, seat_pool_eco, p_eco)):
            for i in range(count):
                cid = random.choice(cust_ids)
                booked = dep - timedelta(days=random.randint(1, 120), hours=random.randint(0, 23))
                if f_status == "Cancelled":
                    status = "Cancelled"
                elif random.random() < 0.04:
                    status = "Cancelled"
                elif f_status in ("Landed", "Departed"):
                    status = "NoShow" if random.random() < 0.02 else "Completed"
                elif f_status == "Boarding" or dep - NOW < timedelta(hours=24):
                    status = "CheckedIn" if random.random() < 0.7 else "Confirmed"
                else:
                    status = "Confirmed"

                seat = seats[i]
                paid = round(price * random.uniform(0.85, 1.25), 2)
                bid += 1
                rows.append((bid, rand_pnr(used_pnr), cid, fid, booked.isoformat(sep=" "),
                             cabin, seat, random.randint(0, 3), paid, status, None))
    return rows


def main():
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    customers = make_customers()
    flights = make_flights()
    bookings = make_bookings(customers, flights)

    conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?,?)", customers)
    conn.executemany("INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", flights)
    conn.executemany("INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,?,?,?)", bookings)
    conn.commit()

    print(f"נוצר {DB_PATH}")
    print(f"  לקוחות: {len(customers):,}")
    print(f"  טיסות:  {len(flights):,}")
    print(f"  הזמנות: {len(bookings):,}")
    conn.close()


if __name__ == "__main__":
    main()
