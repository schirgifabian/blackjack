import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pytz
import requests
import urllib.parse
import uuid
import logging

# --- 1. CORE CONFIG ---
st.set_page_config(page_title="Blackjack Bank", page_icon="♠️", layout="centered")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("bjbank")

# Constants
VALID_PLAYERS = sorted(["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi"])
CHIP_VALUES = [5, 10, 20, 50, 100]
TZ = pytz.timezone('Europe/Berlin')

# Session-Cutoff: Buchungen vor 6 Uhr morgens zählen zum Vortag
SESSION_HOUR_CUTOFF = 6
UNDO_WINDOW_SECONDS = 60

# --- SESSION STATE SETUP ---
if 'trans_amount' not in st.session_state:
    st.session_state.trans_amount = 10.0
if 'last_booking' not in st.session_state:
    st.session_state.last_booking = None  # {'id': ..., 'time': datetime, 'summary': str}
if 'active_session_id' not in st.session_state:
    st.session_state.active_session_id = None
if 'reset_amount' not in st.session_state:
    st.session_state.reset_amount = False
if 'fast_mode_active' not in st.session_state:
    st.session_state.fast_mode_active = False
if 'fast_mode_player' not in st.session_state:
    st.session_state.fast_mode_player = None

if st.session_state.reset_amount:
    st.session_state.trans_amount = 10.0
    st.session_state.reset_amount = False

def set_amount(val):
    st.session_state.trans_amount = float(val)

def get_session_date(dt):
    """Verschiebt Buchungen vor 6 Uhr morgens auf den Vortag."""
    if pd.isna(dt) or dt is None:
        return datetime.now(TZ).date()
    if hasattr(dt, 'tz_localize') and dt.tzinfo is None:
        pass  # naive datetime ist ok
    return dt.date() - timedelta(days=1) if dt.hour < SESSION_HOUR_CUTOFF else dt.date()

# --- 2. LUXURY CSS ENGINE ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@500;700&display=swap');

    .stApp {
        background: radial-gradient(circle at top left, #F8FAFC, #E2E8F0);
        font-family: 'Inter', sans-serif;
        color: #0F172A;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(255, 255, 255, 0.7);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.5);
        border-radius: 24px;
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.07);
        padding: 24px !important;
        margin-bottom: 20px;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] > div { padding: 0 !important; }

    .glass-card {
        background: rgba(255, 255, 255, 0.7);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.5);
        border-radius: 24px;
        padding: 24px;
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.07);
        margin-bottom: 20px;
        transition: transform 0.2s;
    }

    .vault-display {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        color: white;
        padding: 35px 20px;
        border-radius: 28px;
        text-align: center;
        margin-bottom: 25px;
        box-shadow: 0 20px 40px -10px rgba(15, 23, 42, 0.4);
    }
    .vault-label {
        text-transform: uppercase;
        letter-spacing: 3px;
        font-size: 11px;
        opacity: 0.6;
        margin-bottom: 8px;
        font-weight: 700;
    }
    .vault-amount {
        font-family: 'JetBrains Mono', monospace;
        font-size: 60px;
        font-weight: 700;
        letter-spacing: -2px;
    }
    .vault-meta {
        font-size: 12px;
        opacity: 0.5;
        margin-top: 10px;
        letter-spacing: 1px;
    }

    .metric-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 24px;
        font-weight: 700;
    }
    .metric-label {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 1px;
        opacity: 0.7;
    }

    div[data-testid="column"] button {
        border-radius: 16px;
        height: 70px;
        font-size: 18px;
        width: 100%;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        border: 1px solid #E2E8F0;
        background: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.04);
        transition: all 0.2s;
    }
    div[data-testid="column"] button:hover {
        border-color: #0F172A;
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(0,0,0,0.1);
    }
    div[data-testid="column"] button:focus {
        background: #F1F5F9;
        color: #0F172A;
        border-color: #0F172A;
    }

    button[kind="primary"] {
        border-radius: 16px;
        height: 80px;
        font-size: 20px;
        font-weight: 600;
        box-shadow: 0 6px 16px rgba(0,0,0,0.1);
    }
    button[kind="secondary"] {
        border-radius: 16px;
        height: 80px;
        font-size: 20px;
        font-weight: 600;
        border: 1px solid #E2E8F0;
        background: rgba(255,255,255,0.8);
    }

    #MainMenu, footer {visibility: hidden;}

    header button[data-testid="baseButton-header"],
    [data-testid="stSidebarCollapsed"],
    [data-testid="stSidebar"] > div:first-child button {
        visibility: visible !important;
        opacity: 1 !important;
        display: block !important;
        z-index: 999999 !important;
    }

    .stApp > header {
        background: radial-gradient(circle at top left, #F8FAFC, #E2E8F0) !important;
        background-color: transparent !important;
    }

    header .stButton button[title*="GitHub"],
    header .stButton button[title*="Share"],
    header button[kind="header"]:not([data-testid="baseButton-header"]) {
        display: none !important;
        visibility: hidden !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        background: rgba(255,255,255,0.5);
        padding: 5px;
        border-radius: 16px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px;
        border: none;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background: white !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }

    .badge-pill {
        display: inline-block;
        padding: 4px 12px;
        margin: 2px 4px 2px 0;
        background: rgba(15, 23, 42, 0.05);
        border-radius: 999px;
        font-size: 12px;
        font-weight: 600;
    }

    @media (pointer: coarse) {
        div[data-testid="stSidebarCollapsed"] {
            visibility: visible !important;
            width: auto !important;
        }
        button[kind="header"] { z-index: 999999 !important; }
        .stApp { padding-top: 60px; }
    }

    @media (display-mode: standalone) {
        .stApp { padding-top: 70px !important; }
    }
</style>
""", unsafe_allow_html=True)

# --- 3. LOGIC & DATA ---

def get_qr(name, iban, amount, purpose):
    data = f"BCD\n002\n1\nSCT\n\n{name}\n{iban.replace(' ', '')}\nEUR{amount:.2f}\n\n\n{purpose}"
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(data)}"

def calc_netto(row):
    b = row["Betrag"]
    a = str(row["Aktion"]).lower()
    return -b if (("ausgabe" in a or "auszahlung" in a) and b > 0) else b

def get_conn():
    """Connection-Objekt – NICHT cachen (nicht pickle-fähig)."""
    return st.connection("gsheets", type=GSheetsConnection)


@st.cache_data(ttl=30)
def load_data():
    """Daten laden und aufbereiten. Gibt nur den DataFrame zurück (cachebar)."""
    conn = get_conn()
    try:
        df = conn.read(worksheet="Buchungen", ttl=0)
        rename_map = {"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"}
        df = df.rename(columns=rename_map)

        expected_cols = ["Datum", "Name", "Aktion", "Betrag", "Zeitstempel", "Session_ID", "Booking_ID"]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = None

        if not df.empty:
            df["Betrag"] = pd.to_numeric(
                df["Betrag"].astype(str).str.replace(',', '.', regex=False),
                errors='coerce'
            ).fillna(0)
            df['Full_Date'] = pd.to_datetime(
                df['Datum'].astype(str) + ' ' + df['Zeitstempel'].fillna('00:00').astype(str),
                format='%d.%m.%Y %H:%M', errors='coerce'
            )
            df['Full_Date'] = df['Full_Date'].fillna(
                pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce')
            )
            df["Netto"] = df.apply(calc_netto, axis=1)
            df["Session_Date"] = df["Full_Date"].apply(get_session_date)
            return df.sort_values("Full_Date", ascending=False).reset_index(drop=True)
    except Exception as e:
        log.error(f"load_data failed: {e}")
    return pd.DataFrame(columns=[
        "Datum", "Zeitstempel", "Name", "Aktion", "Betrag", "Netto",
        "Full_Date", "Session_Date", "Session_ID", "Booking_ID"
    ])


def write_booking(conn, name, typ, amount, session_id):
    """Buchung ans Sheet anhängen. Gibt Booking_ID zurück."""
    now = datetime.now(TZ)
    booking_id = uuid.uuid4().hex[:12]
    new_entry = pd.DataFrame([{
        "Datum": now.strftime("%d.%m.%Y"),
        "Zeit": now.strftime("%H:%M"),
        "Spieler": name,
        "Typ": typ,
        "Betrag": amount,
        "Session_ID": session_id or "",
        "Booking_ID": booking_id,
    }])
    raw = conn.read(worksheet="Buchungen", ttl=0)
    # Sicherstellen, dass die neuen Spalten existieren
    for col in ["Session_ID", "Booking_ID"]:
        if col not in raw.columns:
            raw[col] = ""
    updated = pd.concat([raw, new_entry], ignore_index=True)
    conn.update(worksheet="Buchungen", data=updated)
    return booking_id, now


def delete_booking(conn, booking_id):
    """Letzte Buchung anhand Booking_ID entfernen."""
    raw = conn.read(worksheet="Buchungen", ttl=0)
    if "Booking_ID" not in raw.columns or raw.empty:
        return False
    before = len(raw)
    filtered = raw[raw["Booking_ID"].astype(str) != str(booking_id)]
    if len(filtered) == before:
        return False
    conn.update(worksheet="Buchungen", data=filtered)
    return True


def send_ntfy(title, msg, tag="moneybag"):
    try:
        requests.post(
            "https://ntfy.sh/bj-boys-dashboard",
            data=msg.encode('utf-8'),
            headers={"Title": title.encode('utf-8'), "Tags": tag},
            timeout=2
        )
    except Exception as e:
        log.warning(f"ntfy failed: {e}")


# --- DEBT NETTING (Splitwise-Style) ---
def settle_debts(balances: dict):
    """
    balances: {name: amount}  positiv = bekommt Geld, negativ = schuldet
    Returns: list of (debtor, creditor, amount) – minimale Zahlungen
    """
    creditors = sorted(
        [(n, v) for n, v in balances.items() if v > 0.01],
        key=lambda x: -x[1]
    )
    debtors = sorted(
        [(n, -v) for n, v in balances.items() if v < -0.01],
        key=lambda x: -x[1]
    )

    transactions = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        d_name, d_amt = debtors[i]
        c_name, c_amt = creditors[j]
        pay = min(d_amt, c_amt)
        transactions.append((d_name, c_name, round(pay, 2)))
        d_amt -= pay
        c_amt -= pay
        if d_amt < 0.01:
            i += 1
        else:
            debtors[i] = (d_name, d_amt)
        if c_amt < 0.01:
            j += 1
        else:
            creditors[j] = (c_name, c_amt)
    return transactions


# --- ACHIEVEMENTS ---
def compute_achievements(df_all, player):
    """Achievements für einen Spieler berechnen."""
    badges = []
    df_p = df_all[
        (df_all["Name"] == player)
        & (~df_all["Aktion"].astype(str).str.contains("Bank", case=False, na=False))
    ].copy()
    if df_p.empty:
        return badges

    df_p["Profit"] = -df_p["Netto"]
    lifetime = df_p["Profit"].sum()

    sessions = df_p.groupby("Session_Date")["Profit"].sum().reset_index()
    n_sessions = len(sessions)
    wins = (sessions["Profit"] > 0).sum()
    best = sessions["Profit"].max() if not sessions.empty else 0
    worst = sessions["Profit"].min() if not sessions.empty else 0

    # Streak: max consecutive winning sessions
    sessions_sorted = sessions.sort_values("Session_Date")
    max_streak = cur_streak = 0
    for p in sessions_sorted["Profit"]:
        if p > 0:
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
        else:
            cur_streak = 0

    # Buy-ins (Anzahl Einzahlungen in einer Session = Re-buys)
    buyins = df_p[df_p["Aktion"].astype(str).str.contains("Einzahlung", case=False, na=False)]
    max_buyins_session = buyins.groupby("Session_Date").size().max() if not buyins.empty else 0

    rules = [
        (lifetime >= 100, "🦈 Hai", "100€+ Lifetime"),
        (lifetime >= 500, "👑 Legende", "500€+ Lifetime"),
        (lifetime <= -100, "💸 Sponsor", "Trägt die Runde"),
        (best >= 100, "🚀 Moonshot", "100€+ in einer Session"),
        (best >= 250, "💎 Diamant", "250€+ in einer Session"),
        (worst <= -100, "💀 Tilt", "100€+ verloren"),
        (max_streak >= 3, f"🔥 Streak x{max_streak}", f"{max_streak} Wins in Folge"),
        (max_streak >= 5, "⚡ On Fire", "5+ Wins in Folge"),
        (n_sessions >= 10, "🎲 Stammgast", "10+ Sessions"),
        (n_sessions >= 25, "🏛️ Veteran", "25+ Sessions"),
        (wins >= 10, "🏆 Winner", "10+ gewonnene Sessions"),
        (max_buyins_session >= 4, "🩸 Bluter", "4+ Re-buys in einer Session"),
        (max_buyins_session >= 7, "🌋 All-In", "7+ Re-buys in einer Session"),
    ]
    for cond, label, desc in rules:
        if cond:
            badges.append((label, desc))
    return badges


def player_streak(df_all, player):
    """Aktueller Win/Loss-Streak."""
    df_p = df_all[
        (df_all["Name"] == player)
        & (~df_all["Aktion"].astype(str).str.contains("Bank", case=False, na=False))
    ].copy()
    if df_p.empty:
        return 0, "neutral"
    df_p["Profit"] = -df_p["Netto"]
    sessions = df_p.groupby("Session_Date")["Profit"].sum().sort_index(ascending=False)
    if sessions.empty:
        return 0, "neutral"
    streak = 0
    direction = "win" if sessions.iloc[0] > 0 else ("loss" if sessions.iloc[0] < 0 else "neutral")
    for p in sessions:
        if direction == "win" and p > 0:
            streak += 1
        elif direction == "loss" and p < 0:
            streak += 1
        else:
            break
    return streak, direction


# --- LOAD ---
conn = get_conn()
df = load_data()
balance = df["Netto"].sum() if not df.empty else 0.0


# --- 4. NAVIGATION ---
with st.sidebar:
    st.markdown("### ♠️ Navigation")
    page = st.radio(
        "Go to",
        ["Übersicht", "Transaktion", "Statistik", "Achievements", "Kassensturz"],
        label_visibility="collapsed"
    )
    st.markdown("---")

    # Session-Steuerung
    st.markdown("#### 🎰 Session")
    if st.session_state.active_session_id:
        st.success(f"Aktiv: `{st.session_state.active_session_id[:8]}`")
        if st.button("⚡ Fast Mode öffnen", use_container_width=True, type="primary"):
            st.session_state.fast_mode_active = True
            st.rerun()
        if st.button("⏹️ Session beenden", use_container_width=True):
            st.session_state.active_session_id = None
            st.session_state.fast_mode_active = False
            st.toast("Session beendet")
            st.rerun()
    else:
        if st.button("▶️ Session starten", use_container_width=True, type="primary"):
            st.session_state.active_session_id = uuid.uuid4().hex[:12]
            st.session_state.fast_mode_active = True
            st.session_state.fast_mode_player = None
            st.toast(f"Session gestartet: {st.session_state.active_session_id[:8]}")
            st.rerun()

    st.markdown("---")
    if st.button("🔄 Sync", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# --- FAST MODE OVERLAY ---
if st.session_state.get("fast_mode_active"):
    st.markdown("""
    <style>
        /* iPad Touch-Optimierungen */
        * {
            -webkit-tap-highlight-color: transparent !important;
            user-select: none !important;
            -webkit-user-select: none !important;
        }

        button {
            touch-action: manipulation !important; /* Verhindert Double-Tap Zoom */
        }

        /* Vollbild-Modus: Alles ausblenden */
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stHeader"] { display: none !important; }
        [data-testid="stToolbar"] { display: none !important; }
        #MainMenu { display: none !important; }
        footer { display: none !important; }

        .block-container {
            padding: 2rem !important;
            max-width: 100% !important;
        }

        /* Zurück / Close Buttons (außerhalb Grid) */
        div.stButton > button {
            height: 90px !important;
            font-size: 28px !important;
            font-weight: 700 !important;
            border-radius: 24px !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05) !important;
        }

        /* ALLE Buttons in Spalten → quadratisch & riesig (Kassen-Style) */
        div[data-testid="column"] div.stButton > button {
            aspect-ratio: 1 / 1 !important;
            height: auto !important;
            min-height: 0 !important;
            font-size: 56px !important; /* Deutlich größer für iPad */
            font-weight: 800 !important;
            font-family: 'Inter', sans-serif !important;
            border-radius: 32px !important;
            border: 4px solid #CBD5E1 !important;
            background: white !important;
            color: #0F172A !important;
            box-shadow: 0 12px 30px rgba(0,0,0,0.08) !important;
            transition: all 0.1s ease !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            padding: 24px !important; /* Viel Padding für Touch-Target */
            width: 100% !important;
        }
        
        @media (max-width: 800px) {
            div[data-testid="column"] div.stButton > button {
                font-size: 32px !important; /* Fallback für kleine Screens */
                border-radius: 20px !important;
                padding: 12px !important;
            }
        }

        div[data-testid="column"] div.stButton > button:hover {
            border-color: #10B981 !important;
            background: #F0FDF4 !important;
            transform: scale(1.02) !important;
            box-shadow: 0 20px 40px rgba(16,185,129,0.2) !important;
        }
        div[data-testid="column"] div.stButton > button:active {
            transform: scale(0.95) !important;
            background: #D1FAE5 !important;
            border-color: #059669 !important;
            box-shadow: 0 4px 10px rgba(0,0,0,0.1) !important;
        }

        /* Spalten-Abstand vergrößern */
        div[data-testid="stHorizontalBlock"] {
            gap: 2rem !important; /* Größere Gaps zwischen den Quadraten */
            margin-bottom: 2rem !important;
        }
    </style>
    """, unsafe_allow_html=True)

    p_name = st.session_state.get("fast_mode_player")

    # Header als reines HTML + separate Streamlit-Buttons (NICHT in columns)
    back_label = f"⬅️ {p_name}" if p_name else ""
    st.markdown(f"""
    <div style="display: flex; align-items: center; justify-content: space-between; padding: 4px 0; margin-bottom: 20px;">
        <div style="font-size: 26px; color: #64748B; font-weight: 600;">{back_label}</div>
        <h1 style="margin: 0; font-size: 42px;">⚡ Fast Booking</h1>
        <div style="width: 100px;"></div>
    </div>
    """, unsafe_allow_html=True)

    # Zurück / Close als normale Streamlit Buttons (klein, ohne Spalten)
    if p_name is not None:
        if st.button("⬅️ Zurück zur Spielerauswahl", key="back_fast", use_container_width=True):
            st.session_state.fast_mode_player = None
            st.rerun()
    else:
        if st.button("✖ Fast Booking schließen", key="close_fast", use_container_width=True):
            st.session_state.fast_mode_active = False
            st.rerun()

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    if p_name is None:
        players = VALID_PLAYERS + ["Alle"]
        for row in range(2):
            cols = st.columns(4, gap="large")
            for col_idx in range(4):
                idx = row * 4 + col_idx
                if idx < len(players):
                    p = players[idx]
                    with cols[col_idx]:
                        if st.button(p, key=f"fp_{p}", use_container_width=True):
                            st.session_state.fast_mode_player = p
                            st.rerun()
            if row == 0:
                st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
    else:
        fast_amounts = [5, 10, 15, 20, 30, 40, 50, 100]
        for row in range(2):
            cols = st.columns(4, gap="large")
            for col_idx in range(4):
                idx = row * 4 + col_idx
                if idx < len(fast_amounts):
                    amt = fast_amounts[idx]
                    with cols[col_idx]:
                        if st.button(f"{amt} €", key=f"fa_{amt}", use_container_width=True):
                            with st.spinner("Buche..."):
                                if p_name == "Alle":
                                    for p in VALID_PLAYERS:
                                        write_booking(
                                            conn, p, "Einzahlung", float(amt), st.session_state.active_session_id
                                        )
                                    st.session_state.last_booking = None  # Undo für Sammelbuchung deaktivieren
                                    if amt >= 50:
                                        send_ntfy("Sammel-Einzahlung", f"ALLE (7x): {amt:.2f}€", "moneybag")
                                    st.toast(f"✅ {amt:.2f}€ für ALLE ({len(VALID_PLAYERS)}x) verbucht!", icon="♠️")
                                else:
                                    booking_id, now = write_booking(
                                        conn, p_name, "Einzahlung", float(amt), st.session_state.active_session_id
                                    )
                                    st.session_state.last_booking = {
                                        'id': booking_id,
                                        'time': now,
                                        'summary': f"Einzahlung · {p_name} · {amt:.2f}€"
                                    }
                                    if amt >= 100:
                                        send_ntfy("Einzahlung", f"{p_name}: {amt:.2f}€", "moneybag")
                                    st.toast(f"✅ {amt:.2f}€ für {p_name} eingezahlt", icon="♠️")
                                
                                st.session_state.fast_mode_player = None
                                st.cache_data.clear()
                                st.rerun()
    st.stop()


# --- HEADER ---
if page == "Übersicht":
    # Session-Info
    today_session = get_session_date(datetime.now(TZ))
    df_today = df[df["Session_Date"] == today_session] if not df.empty else df
    n_today = len(df_today)
    vol_today = df_today["Betrag"].sum() if not df_today.empty else 0

    st.markdown(f"""
    <div class="vault-display">
        <div class="vault-label">BANK HOLDINGS</div>
        <div class="vault-amount">{balance:,.2f} €</div>
        <div class="vault-meta">{n_today} Buchungen heute · {vol_today:,.0f}€ Volumen</div>
    </div>
    """, unsafe_allow_html=True)


# --- PAGE 1: DASHBOARD ---
if page == "Übersicht":
    if df.empty:
        st.info("Das Casino ist eröffnet. Bitte erste Buchung tätigen.")
    else:
        # UNDO-Banner falls letzte Buchung im Fenster
        if st.session_state.last_booking:
            elapsed = (datetime.now(TZ) - st.session_state.last_booking['time']).total_seconds()
            if elapsed < UNDO_WINDOW_SECONDS:
                remaining = int(UNDO_WINDOW_SECONDS - elapsed)
                c_undo1, c_undo2 = st.columns([3, 1])
                with c_undo1:
                    st.warning(f"⏪ {st.session_state.last_booking['summary']} · {remaining}s zum Rückgängigmachen")
                with c_undo2:
                    if st.button("Undo", type="primary", use_container_width=True):
                        if delete_booking(conn, st.session_state.last_booking['id']):
                            st.toast("✅ Buchung rückgängig gemacht")
                            st.session_state.last_booking = None
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("Konnte Buchung nicht finden")
            else:
                st.session_state.last_booking = None

        st.markdown("##### 📡 Live Feed")
        for _, row in df.head(5).iterrows():
            icon = "📥" if "Einzahlung" in str(row["Aktion"]) else "📤" if "Auszahlung" in str(row["Aktion"]) else "🏦"
            color = "#10B981" if row["Netto"] > 0 else "#EF4444"
            sign = "+" if row["Netto"] > 0 else ""
            st.markdown(f"""
            <div class="glass-card" style="padding: 16px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                <div style="display:flex; align-items:center; gap:15px;">
                    <div style="font-size:24px;">{icon}</div>
                    <div>
                        <div style="font-weight:700; font-size:15px;">{row['Name']}</div>
                        <div style="font-size:12px; color:#64748B;">{row['Zeitstempel']} • {row['Aktion']}</div>
                    </div>
                </div>
                <div style="font-family:'JetBrains Mono'; font-weight:700; color:{color}; font-size:16px;">
                    {sign}{abs(row['Netto']):.2f} €
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("##### 👑 Leaderboard")
        df_p = df[~df["Aktion"].astype(str).str.contains("Bank", case=False, na=False)]
        if not df_p.empty:
            lb = df_p.groupby("Name")["Netto"].sum().mul(-1).sort_values(ascending=False).head(3)
            cols = st.columns(3)
            for idx, (name, val) in enumerate(lb.items()):
                badges = ["🥇", "🥈", "🥉"]
                color = "#10B981" if val >= 0 else "#EF4444"
                streak, direction = player_streak(df, name)
                streak_emoji = "🔥" if direction == "win" and streak >= 2 else ("❄️" if direction == "loss" and streak >= 2 else "")
                streak_label = f"{streak_emoji} {streak}" if streak_emoji else ""
                with cols[idx]:
                    st.markdown(f"""
                    <div class="glass-card" style="text-align:center; padding:15px;">
                        <div style="font-size:24px; margin-bottom:5px;">{badges[idx]}</div>
                        <div style="font-weight:bold; font-size:14px; margin-bottom:5px;">{name}</div>
                        <div style="font-family:'JetBrains Mono'; color:{color}; font-weight:bold;">{val:+.0f}€</div>
                        <div style="font-size:11px; opacity:0.7; margin-top:4px;">{streak_label}</div>
                    </div>
                    """, unsafe_allow_html=True)


# --- PAGE 2: TRANSAKTION ---
elif page == "Transaktion":
    st.markdown("### 🎲 Quick Action")

    if not st.session_state.active_session_id:
        st.info("💡 Tipp: Starte links eine Session, damit Buchungen sauber zugeordnet werden.")

    # 1. PLAYER
    with st.container(border=True):
        st.caption("👤 SPIELER WÄHLEN")
        p_sel = st.pills(
            "Name",
            VALID_PLAYERS + ["Sonstiges"],
            selection_mode="single",
            default=VALID_PLAYERS[0],
            key="player_select",
            label_visibility="collapsed"
        )
        final_name = p_sel
        if p_sel == "Sonstiges":
            final_name = st.text_input("Name/Zweck", placeholder="Name oder Zweck eingeben", key="custom_name_input")

    # 2. BETRAG
    with st.container(border=True):
        st.caption("💰 BETRAG")
        cols = st.columns(len(CHIP_VALUES))
        for i, val in enumerate(CHIP_VALUES):
            cols[i].button(f"{val}", key=f"btn_{val}", on_click=set_amount, args=(val,), use_container_width=True)
        st.write("")
        amount = st.number_input("Betrag (€)", key="trans_amount", step=5.0, format="%.2f", label_visibility="collapsed")

    # 3. AKTION
    with st.container(border=True):
        st.caption("⚡ AKTION")
        c1, c2 = st.columns(2)
        action_triggered = False
        typ = None
        ntfy_tag = "moneybag"

        with c1:
            if st.button("📥 Einzahlen (Kaufen)", type="primary", use_container_width=True):
                typ, ntfy_tag, action_triggered = "Einzahlung", "moneybag", True
            if st.button("📈 Bank Gewinn", type="secondary", use_container_width=True):
                typ, ntfy_tag, action_triggered = "Bank Einnahme", "moneybag", True
        with c2:
            if st.button("📤 Auszahlen (Tauschen)", type="primary", use_container_width=True):
                typ, ntfy_tag, action_triggered = "Auszahlung", "chart_with_downwards_trend", True
            if st.button("💸 Bank Verlust", type="secondary", use_container_width=True):
                typ, ntfy_tag, action_triggered = "Bank Ausgabe", "chart_with_downwards_trend", True

        if action_triggered:
            if not final_name:
                st.error("⚠️ Bitte Name wählen!")
            elif amount <= 0:
                st.error("⚠️ Betrag > 0 erforderlich!")
            else:
                with st.spinner(f"Buche {typ}..."):
                    try:
                        booking_id, now = write_booking(
                            conn, final_name, typ, amount, st.session_state.active_session_id
                        )
                        st.session_state.last_booking = {
                            'id': booking_id,
                            'time': now,
                            'summary': f"{typ} · {final_name} · {amount:.2f}€"
                        }

                        # Push bei Bank-Buchungen oder großen Beträgen (>100)
                        if "Bank" in typ or amount >= 100:
                            send_ntfy(typ, f"{final_name}: {amount:.2f}€", ntfy_tag)

                        st.toast(f"✅ {typ}: {amount:.2f}€", icon="♠️")
                        if "Einnahme" in typ:
                            st.balloons()

                        # Reset Betrag auf Default
                        st.session_state.reset_amount = True
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        log.error(f"booking failed: {e}")
                        st.error(f"Fehler: {e}")


# --- PAGE 3: STATISTIK ---
elif page == "Statistik":
    st.markdown("### 📊 Deep Analytics")

    df_calc = df.sort_values("Full_Date").copy() if not df.empty else df.copy()
    if not df_calc.empty:
        df_calc["Balance"] = df_calc["Netto"].cumsum()
    else:
        df_calc = pd.DataFrame(columns=[
            "Datum", "Zeitstempel", "Name", "Aktion", "Betrag", "Netto",
            "Full_Date", "Session_Date", "Balance"
        ])

    filter_options = ["Aktuelle Session", "Gesamt", "Dieser Monat", "Benutzerdefiniert"]
    scope = st.pills("Zeitraum", filter_options, default="Aktuelle Session")
    today = datetime.now(TZ).date()

    if scope == "Aktuelle Session":
        current_session_date = get_session_date(datetime.now(TZ))
        df_s = df_calc[df_calc["Session_Date"] == current_session_date] if not df_calc.empty else df_calc
    elif scope == "Gesamt":
        df_s = df_calc
    elif scope == "Dieser Monat":
        df_s = df_calc[
            (df_calc["Full_Date"].dt.month == today.month) & (df_calc["Full_Date"].dt.year == today.year)
        ] if not df_calc.empty else df_calc
    else:  # Benutzerdefiniert
        d_range = st.date_input(
            "Wähle Zeitraum:",
            value=(today - timedelta(days=7), today),
            format="DD.MM.YYYY"
        )
        if isinstance(d_range, tuple) and len(d_range) == 2:
            df_s = df_calc[
                (df_calc["Full_Date"].dt.date >= d_range[0]) & (df_calc["Full_Date"].dt.date <= d_range[1])
            ]
        elif isinstance(d_range, tuple) and len(d_range) == 1:
            df_s = df_calc[df_calc["Full_Date"].dt.date == d_range[0]]
        else:
            df_s = df_calc

    t1, t2, t3, t4, t5 = st.tabs(["Performance", "Timeline", "Kalender", "Vergleich", "Profil"])

    # --- TAB 1: Performance ---
    with t1:
        df_p = df_s[~df_s["Aktion"].astype(str).str.contains("Bank", case=False, na=False)] if not df_s.empty else df_s
        if not df_p.empty:
            agg = df_p.groupby("Name")["Netto"].sum().mul(-1).reset_index(name="Profit").sort_values("Profit", ascending=False)
            agg["Color"] = agg["Profit"].apply(lambda x: '#10B981' if x >= 0 else '#EF4444')
            fig = px.bar(agg, x="Profit", y="Name", orientation='h', text="Profit")
            fig.update_traces(
                marker_color=agg["Color"],
                texttemplate='%{text:+.2f} €',
                textposition='outside',
                textfont_family="JetBrains Mono"
            )
            fig.update_layout(
                template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                height=400, yaxis_title=None, xaxis_title=None
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Keine Daten im gewählten Zeitraum.")

    # --- TAB 2: Timeline ---
    with t2:
        if not df_s.empty:
            df_h = df_s.sort_values("Full_Date")
            fig_l = px.area(df_h, x="Full_Date", y="Balance")
            min_y, max_y = df_h["Balance"].min(), df_h["Balance"].max()
            padding = (max_y - min_y) * 0.1 if max_y != min_y else 10
            fig_l.update_yaxes(range=[min_y - padding, max_y + padding])
            fig_l.update_traces(line_color='#0F172A', fill='tozeroy', fillcolor='rgba(15, 23, 42, 0.1)')
            fig_l.update_layout(
                template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                height=350, yaxis_title=None, xaxis_title=None
            )
            st.plotly_chart(fig_l, use_container_width=True)
        else:
            st.info("Keine Transaktionen in diesem Zeitraum.")

    # --- TAB 3: Kalender-Heatmap ---
    with t3:
        if not df.empty:
            year_options = sorted(df["Full_Date"].dt.year.dropna().unique().astype(int).tolist(), reverse=True)
            if year_options:
                sel_year = st.selectbox("Jahr", year_options, key="cal_year")
                df_y = df[df["Full_Date"].dt.year == sel_year].copy()

                # Aktivität pro Tag (Anzahl Buchungen)
                daily = df_y.groupby(df_y["Session_Date"]).size().reset_index(name="Count")
                daily["Session_Date"] = pd.to_datetime(daily["Session_Date"])

                # Volle Jahresgrid bauen
                start = pd.Timestamp(sel_year, 1, 1)
                end = pd.Timestamp(sel_year, 12, 31)
                all_days = pd.DataFrame({"Date": pd.date_range(start, end)})
                merged = all_days.merge(daily, left_on="Date", right_on="Session_Date", how="left")
                merged["Count"] = merged["Count"].fillna(0)
                merged["Week"] = merged["Date"].dt.isocalendar().week
                merged["DayOfWeek"] = merged["Date"].dt.dayofweek
                merged["Month"] = merged["Date"].dt.month

                # Plotly Heatmap
                pivot = merged.pivot_table(index="DayOfWeek", columns="Week", values="Count", aggfunc="sum").fillna(0)
                fig_cal = go.Figure(data=go.Heatmap(
                    z=pivot.values,
                    x=[f"W{w}" for w in pivot.columns],
                    y=["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
                    colorscale=[[0, "#F1F5F9"], [0.3, "#94A3B8"], [1, "#0F172A"]],
                    showscale=True,
                    hoverongaps=False,
                    colorbar=dict(title="Buchungen", thickness=10),
                ))
                fig_cal.update_layout(
                    template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    height=250, margin=dict(l=20, r=20, t=20, b=20),
                )
                st.plotly_chart(fig_cal, use_container_width=True)

                # Stats
                play_days = (merged["Count"] > 0).sum()
                total_book = int(merged["Count"].sum())
                c1, c2, c3 = st.columns(3)
                c1.metric("Spieltage", play_days)
                c2.metric("Buchungen gesamt", total_book)
                c3.metric("Ø pro Spieltag", f"{(total_book / play_days):.1f}" if play_days else "0")
            else:
                st.info("Keine Daten verfügbar.")
        else:
            st.info("Keine Daten verfügbar.")

    # --- TAB 4: Year-over-Year Vergleich ---
    with t4:
        if not df.empty:
            df_yoy = df[~df["Aktion"].astype(str).str.contains("Bank", case=False, na=False)].copy()
            df_yoy["Year"] = df_yoy["Full_Date"].dt.year
            df_yoy["Profit"] = -df_yoy["Netto"]

            years = sorted(df_yoy["Year"].dropna().unique().astype(int).tolist(), reverse=True)
            if len(years) >= 1:
                col_a, col_b = st.columns(2)
                with col_a:
                    y1 = st.selectbox("Jahr A", years, index=0, key="yoy_a")
                with col_b:
                    y2 = st.selectbox(
                        "Jahr B",
                        years,
                        index=1 if len(years) > 1 else 0,
                        key="yoy_b"
                    )

                def year_summary(year):
                    sub = df_yoy[df_yoy["Year"] == year]
                    return {
                        "Buchungen": len(sub),
                        "Sessions": sub["Session_Date"].nunique(),
                        "Volumen": sub["Betrag"].sum(),
                        "Top Verlierer": (sub.groupby("Name")["Profit"].sum().idxmin()
                                          if not sub.empty else "—"),
                        "Top Gewinner": (sub.groupby("Name")["Profit"].sum().idxmax()
                                          if not sub.empty else "—"),
                    }

                s1, s2 = year_summary(y1), year_summary(y2)

                cmp_df = pd.DataFrame({
                    "Metrik": list(s1.keys()),
                    f"{y1}": list(s1.values()),
                    f"{y2}": list(s2.values()),
                })
                st.dataframe(cmp_df, use_container_width=True, hide_index=True)

                # Profit pro Spieler im Vergleich
                pivot = df_yoy[df_yoy["Year"].isin([y1, y2])].groupby(["Name", "Year"])["Profit"].sum().unstack(fill_value=0)
                if not pivot.empty:
                    fig_yoy = go.Figure()
                    for yr in pivot.columns:
                        fig_yoy.add_trace(go.Bar(name=str(yr), x=pivot.index, y=pivot[yr]))
                    fig_yoy.update_layout(
                        barmode='group', template="plotly_white",
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        height=350, yaxis_title="Profit (€)", xaxis_title=None,
                    )
                    st.plotly_chart(fig_yoy, use_container_width=True)
            else:
                st.info("Mindestens ein Jahr nötig.")
        else:
            st.info("Keine Daten verfügbar.")

    # --- TAB 5: Profil ---
    with t5:
        st.markdown("##### 👤 Spieler-Profil")
        sel_player = st.selectbox("Spieler wählen", VALID_PLAYERS)

        if sel_player and not df.empty:
            df_play = df[df["Name"] == sel_player].copy()
            if not df_play.empty:
                df_play["Player_Profit"] = -df_play["Netto"]
                lifetime = df_play["Player_Profit"].sum()
                df_sess = df_play.groupby("Session_Date")["Player_Profit"].sum().reset_index()
                best_s = df_sess["Player_Profit"].max() if not df_sess.empty else 0
                worst_s = df_sess["Player_Profit"].min() if not df_sess.empty else 0
                n_sess = len(df_sess)
                wins = (df_sess["Player_Profit"] > 0).sum()
                wr = (wins / n_sess * 100) if n_sess else 0

                streak, direction = player_streak(df, sel_player)
                streak_label = ""
                if streak >= 2:
                    streak_label = f"🔥 {streak} Wins" if direction == "win" else f"❄️ {streak} Losses"

                if streak_label:
                    st.caption(f"Aktueller Streak: {streak_label}")

                c1, c2, c3, c4 = st.columns(4)
                col_data = [
                    (c1, "Lifetime", f"{lifetime:+.2f} €"),
                    (c2, "Best Session", f"{best_s:+.2f} €"),
                    (c3, "Worst Session", f"{worst_s:+.2f} €"),
                    (c4, "Win Rate", f"{wr:.0f}%"),
                ]
                for col, label, val_str in col_data:
                    color_val = lifetime if label == "Lifetime" else (best_s if "Best" in label else (worst_s if "Worst" in label else 0))
                    c_color = "#10B981" if color_val >= 0 else "#EF4444"
                    if label == "Win Rate":
                        c_color = "#0F172A"
                    with col:
                        st.markdown(f"""
                        <div class="glass-card" style="padding:15px; text-align:center;">
                            <div class="metric-label">{label}</div>
                            <div class="metric-value" style="color:{c_color}">{val_str}</div>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("Keine Daten für diesen Spieler.")


# --- PAGE 4: ACHIEVEMENTS ---
elif page == "Achievements":
    st.markdown("### 🏆 Hall of Fame")

    if df.empty:
        st.info("Noch keine Daten – sammelt erst ein paar Sessions.")
    else:
        for player in VALID_PLAYERS:
            badges = compute_achievements(df, player)
            streak, direction = player_streak(df, player)
            streak_pill = ""
            if streak >= 2:
                emoji = "🔥" if direction == "win" else "❄️"
                streak_pill = f'<span class="badge-pill">{emoji} Streak x{streak}</span>'

            badge_html = "".join([
                f'<span class="badge-pill" title="{desc}">{label}</span>'
                for label, desc in badges
            ])
            if not badge_html and not streak_pill:
                badge_html = '<span style="opacity:0.4; font-size:13px;">Noch keine Badges</span>'

            st.markdown(f"""
            <div class="glass-card" style="padding:18px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <div style="font-weight:700; font-size:17px;">{player}</div>
                    <div style="font-size:12px; opacity:0.6;">{len(badges)} Badge{"s" if len(badges)!=1 else ""}</div>
                </div>
                <div>{streak_pill}{badge_html}</div>
            </div>
            """, unsafe_allow_html=True)


# --- PAGE 5: KASSENSTURZ ---
elif page == "Kassensturz":
    st.markdown("### 🏁 Abrechnung")

    secrets_iban = st.secrets.get("bank", {}).get("iban", "")
    secrets_owner = st.secrets.get("bank", {}).get("owner", "Bank")
    if not secrets_iban:
        secrets_iban = st.text_input("IBAN eingeben:", placeholder="DE...")
        secrets_owner = st.text_input("Empfänger:", value="Casino Bank")

    mode = st.radio(
        "Abrechnungs-Modus",
        ["An die Bank zahlen", "Untereinander netten (Splitwise)"],
        horizontal=True
    )

    today = datetime.now(TZ).date()
    if not df.empty:
        df["Full_Date"] = pd.to_datetime(df["Full_Date"], errors='coerce')
        mask_date = (df["Full_Date"].notna()) & (df["Session_Date"].isin([today, today - timedelta(days=1)]))
        mask_name = df["Name"].isin(VALID_PLAYERS)
        df_sess = df[mask_date & mask_name].copy()
    else:
        df_sess = df

    if df_sess.empty:
        st.info("Keine offenen Sessions für Heute oder Gestern.")
    else:
        # Bilanz: positiv = Spieler hat gewonnen (bekommt Geld), negativ = Spieler schuldet
        bilanz = df_sess.groupby("Name")["Netto"].sum().mul(-1).to_dict()

        if mode == "An die Bank zahlen":
            debtors = {n: v for n, v in bilanz.items() if v < -0.01}
            if not debtors:
                st.balloons()
                st.success("Niemand hat Schulden! 🎉")
            else:
                if secrets_iban:
                    st.markdown(
                        f"**Empfänger:** {secrets_owner}<br>"
                        f"<span style='font-family:monospace'>{secrets_iban}</span>",
                        unsafe_allow_html=True
                    )
                st.markdown("---")
                for name, amount in sorted(debtors.items(), key=lambda x: x[1]):
                    abs_amount = abs(amount)
                    st.markdown(f"""
                    <div class="glass-card" style="padding: 0px; overflow: hidden; margin-bottom: 10px;">
                        <div style="background: rgba(239, 68, 68, 0.1); padding: 15px; border-bottom: 1px solid rgba(255,255,255,0.5);">
                            <span style="font-weight:bold; font-size:18px;">🔴 {name}</span>
                            <span style="float:right; font-family:'JetBrains Mono'; font-weight:bold;">{abs_amount:.2f} €</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if secrets_iban:
                        with st.expander(f"📱 QR Code für {name} anzeigen"):
                            qr = get_qr(secrets_owner, secrets_iban, abs_amount, f"BJ {name}")
                            c1, c2 = st.columns([1, 2])
                            with c1:
                                st.image(qr, width=200)
                            with c2:
                                st.info("Scanne diesen Code mit deiner Banking App.")
        else:
            # Splitwise-Modus
            st.caption("Minimale Anzahl Zahlungen zwischen den Spielern – ohne Bank-Umweg.")
            transactions = settle_debts(bilanz)
            if not transactions:
                st.balloons()
                st.success("Alles ausgeglichen! 🎉")
            else:
                st.markdown(f"**{len(transactions)} Zahlung(en) lösen alles auf:**")
                st.markdown("---")
                for debtor, creditor, amt in transactions:
                    st.markdown(f"""
                    <div class="glass-card" style="padding: 14px 18px; margin-bottom:10px; display:flex; align-items:center; justify-content:space-between;">
                        <div style="display:flex; align-items:center; gap:12px;">
                            <span style="font-weight:700; color:#EF4444;">{debtor}</span>
                            <span style="opacity:0.5;">→</span>
                            <span style="font-weight:700; color:#10B981;">{creditor}</span>
                        </div>
                        <div style="font-family:'JetBrains Mono'; font-weight:700; font-size:16px;">{amt:.2f} €</div>
                    </div>
                    """, unsafe_allow_html=True)
