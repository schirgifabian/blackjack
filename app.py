import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import pytz
import requests
import urllib.parse
import time

# --- 1. CORE CONFIG ---
st.set_page_config(page_title="Blackjack Bank", page_icon="♠️", layout="centered")

# Constants
VALID_PLAYERS = sorted(["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi"])
CHIP_VALUES = [5, 10, 20, 50, 100]

# --- SESSION STATE SETUP (Fix für die Transaktions-Seite) ---
if 'trans_amount' not in st.session_state:
    st.session_state.trans_amount = 10.0

def set_amount(val):
    st.session_state.trans_amount = float(val)

# --- 2. LUXURY CSS ENGINE ---
st.markdown("""
<style>
    /* IMPORTS */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@500;700&display=swap');

    /* GLOBAL THEME */
    .stApp {
        background: radial-gradient(circle at top left, #F8FAFC, #E2E8F0);
        font-family: 'Inter', sans-serif;
        color: #0F172A;
    }
    
    /* GLASSMORPHISM CARD */
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
    
    /* VAULT DISPLAY (Header) */
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
    
    /* CHIP BUTTONS STYLING (Streamlit Buttons hacken) */
    div[data-testid="column"] button {
        border-radius: 50%;
        height: 60px;
        width: 60px;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        border: 2px solid #E2E8F0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: all 0.2s;
    }
    div[data-testid="column"] button:focus {
        border-color: #0F172A;
        color: #0F172A;
        background: #F1F5F9;
    }

    /* HIDE DECORATIONS */
    #MainMenu, footer, header {visibility: hidden;}
    
    /* TABS */
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
</style>
""", unsafe_allow_html=True)

# --- 3. LOGIC ---

def get_qr(name, iban, amount, purpose):
    data = f"BCD\n002\n1\nSCT\n\n{name}\n{iban.replace(' ', '')}\nEUR{amount:.2f}\n\n\n{purpose}"
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(data)}"

def calc_netto(row):
    b, a = row["Betrag"], str(row["Aktion"]).lower()
    return -b if (("ausgabe" in a or "auszahlung" in a) and b > 0) else b

@st.cache_data(ttl=0)
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(worksheet="Buchungen", ttl=0)
        df = df.rename(columns={"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"})
        if not df.empty:
            df["Betrag"] = pd.to_numeric(df["Betrag"].astype(str).str.replace(',', '.', regex=False), errors='coerce').fillna(0)
            df['Full_Date'] = pd.to_datetime(df['Datum'] + ' ' + df['Zeitstempel'].fillna('00:00'), format='%d.%m.%Y %H:%M', errors='coerce')
            df['Full_Date'] = df['Full_Date'].fillna(pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce'))
            df["Netto"] = df.apply(calc_netto, axis=1)
            return df.sort_values("Full_Date", ascending=False).reset_index(drop=True), conn
    except: pass
    return pd.DataFrame(), conn

df, conn = load_data()
balance = df["Netto"].sum() if not df.empty else 0.0

# --- 4. NAVIGATION ---
with st.sidebar:
    st.markdown("### ♠️ Navigation")
    page = st.radio("Go to", ["Übersicht", "Transaktion", "Statistik", "Kassensturz"], label_visibility="collapsed")
    st.markdown("---")
    if st.button("🔄 Sync", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- HEADER (Sticky-like) ---
if page == "Übersicht":
    st.markdown(f"""
    <div class="vault-display">
        <div class="vault-label">BANK HOLDINGS</div>
        <div class="vault-amount">{balance:,.2f} €</div>
    </div>
    """, unsafe_allow_html=True)

# --- PAGE 1: DASHBOARD ---
if page == "Übersicht":
    if df.empty:
        st.info("Das Casino ist eröffnet. Bitte erste Buchung tätigen.")
    else:
        # LIVE FEED
        st.markdown("##### 📡 Live Feed")
        
        for i, row in df.head(5).iterrows():
            icon = "📥" if "Einzahlung" in row["Aktion"] else "📤" if "Auszahlung" in row["Aktion"] else "🏦"
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

        # MINI LEADERBOARD
        st.markdown("##### 👑 Leaderboard")
        df_p = df[~df["Aktion"].str.contains("Bank", case=False)]
        if not df_p.empty:
            lb = df_p.groupby("Name")["Netto"].sum().mul(-1).sort_values(ascending=False).head(3)
            cols = st.columns(3)
            for idx, (name, val) in enumerate(lb.items()):
                badges = ["🥇", "🥈", "🥉"]
                color = "green" if val >= 0 else "red"
                with cols[idx]:
                    st.markdown(f"""
                    <div class="glass-card" style="text-align:center; padding:15px;">
                        <div style="font-size:24px; margin-bottom:5px;">{badges[idx]}</div>
                        <div style="font-weight:bold; font-size:14px; margin-bottom:5px;">{name}</div>
                        <div style="font-family:'JetBrains Mono'; color:{color}; font-weight:bold;">{val:+.0f}</div>
                    </div>
                    """, unsafe_allow_html=True)

# --- PAGE 2: QUICK TRANSACTION (FIXED) ---
elif page == "Transaktion":
    st.markdown("### 🎲 Quick Action")
    
    with st.container():
        # 1. PLAYER
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.caption("SPIELER")
        p_sel = st.pills("Name", VALID_PLAYERS + ["Sonstiges"], selection_mode="single", default=VALID_PLAYERS[0], label_visibility="collapsed")
        final_name = st.text_input("Name/Zweck", placeholder="Pizza") if p_sel == "Sonstiges" else p_sel
        st.markdown('</div>', unsafe_allow_html=True)

        # 2. CHIP SELECTOR (Callback Logic - Fixed)
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.caption("BETRAG WÄHLEN")
        
        # Chip Buttons Grid
        cols = st.columns(len(CHIP_VALUES))
        for i, val in enumerate(CHIP_VALUES):
            # WICHTIG: on_click verwendet, um Session State sicher zu updaten
            cols[i].button(f"{val}", key=f"btn_{val}", on_click=set_amount, args=(val,), use_container_width=True)

        st.write("")
        # Input Field linked to session_state key 'trans_amount'
        amount = st.number_input("Betrag (€)", key="trans_amount", step=5.0, format="%.2f", label_visibility="visible")
        st.markdown('</div>', unsafe_allow_html=True)

        # 3. ACTION & SUBMIT
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.caption("AKTION")
        
        col_act1, col_act2 = st.columns(2)
        
        # Init Variables
        typ = None
        sign = 0
        
        with col_act1:
            if st.button("📥 KAUFEN (Einzahlen)", type="secondary", use_container_width=True):
                typ, sign = "Einzahlung", 1
            if st.button("📈 BANK GEWINN", use_container_width=True):
                typ, sign = "Bank Einnahme", 1
                
        with col_act2:
            if st.button("📤 TAUSCHEN (Auszahlen)", type="secondary", use_container_width=True):
                typ, sign = "Auszahlung", -1
            if st.button("💸 BANK VERLUST", use_container_width=True):
                typ, sign = "Bank Ausgabe", -1
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # PROCESSING
        if typ and final_name:
            tz = pytz.timezone('Europe/Berlin')
            now = datetime.now(tz)
            
            new_entry = pd.DataFrame([{
                "Datum": now.strftime("%d.%m.%Y"),
                "Zeit": now.strftime("%H:%M"),
                "Spieler": final_name,
                "Typ": typ,
                "Betrag": amount
            }])
            
            try:
                raw = conn.read(worksheet="Buchungen", ttl=0)
                conn.update(worksheet="Buchungen", data=pd.concat([raw, new_entry], ignore_index=True))
                
                # Notify
                if "Bank" in typ:
                    try:
                        tq = "moneybag" if sign > 0 else "chart_with_downwards_trend"
                        requests.post("https://ntfy.sh/bj-boys-dashboard", 
                            data=f"{final_name}: {amount}€".encode('utf-8'),
                            headers={"Title": "Update".encode('utf-8'), "Tags": tq})
                    except: pass

                st.toast(f"✅ {typ}: {amount}€", icon="♠️")
                
                # Visual Feedback & Reset
                if typ == "Bank Einnahme": st.balloons()
                time.sleep(0.8)
                st.cache_data.clear()
                st.rerun()
                
            except Exception as e:
                st.error(f"Fehler: {e}")
        elif typ and not final_name:
            st.warning("Bitte Namen wählen!")

# --- PAGE 3: STATS ---
elif page == "Statistik":
    st.markdown("### 📊 Deep Analytics")
    
    scope = st.pills("Zeitraum", ["Aktuelle Session", "Gesamt"], default="Aktuelle Session")
    
    df_s = df.copy()
    if scope == "Aktuelle Session":
        today = datetime.now().date()
        df_s = df_s[df_s["Full_Date"].dt.date.isin([today, today - timedelta(days=1)])]

    t1, t2 = st.tabs(["Performance", "Timeline"])
    
    with t1:
        df_p = df_s[~df_s["Aktion"].str.contains("Bank", case=False)]
        if not df_p.empty:
            agg = df_p.groupby("Name")["Netto"].sum().mul(-1).reset_index(name="Profit").sort_values("Profit", ascending=False)
            agg["Color"] = agg["Profit"].apply(lambda x: '#10B981' if x >= 0 else '#EF4444')
            
            fig = px.bar(agg, x="Profit", y="Name", orientation='h', text="Profit")
            fig.update_traces(marker_color=agg["Color"], texttemplate='%{text:+.2f} €', textposition='outside', textfont_family="JetBrains Mono")
            fig.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=400, yaxis_title=None, xaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)
            
    with t2:
        if not df_s.empty:
            df_h = df_s.sort_values("Full_Date")
            df_h["Balance"] = df_h["Netto"].cumsum()
            fig_l = px.area(df_h, x="Full_Date", y="Balance")
            fig_l.update_traces(line_color='#0F172A', fill_color='rgba(15, 23, 42, 0.1)')
            fig_l.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=350, yaxis_title=None, xaxis_title=None)
            st.plotly_chart(fig_l, use_container_width=True)

# --- PAGE 4: SETTLEMENT ---
elif page == "Kassensturz":
    st.markdown("### 🏁 Abrechnung")
    
    secrets_iban = st.secrets.get("bank", {}).get("iban", "")
    secrets_owner = st.secrets.get("bank", {}).get("owner", "Bank")
    
    if not secrets_iban: secrets_iban = st.text_input("IBAN eingeben:")
    
    today = datetime.now().date()
    df_sess = df[df["Full_Date"].dt.date.isin([today, today - timedelta(days=1)]) & df["Name"].isin(VALID_PLAYERS)]
    
    if df_sess.empty:
        st.info("Keine Daten für Session.")
    else:
        bilanz = df_sess.groupby("Name")["Netto"].sum()
        debtors = bilanz[bilanz > 0]
        
        if debtors.empty:
            st.success("Niemand hat Schulden.")
        else:
            st.markdown(f"**Empfänger:** {secrets_owner}<br><span style='font-family:monospace'>{secrets_iban}</span>", unsafe_allow_html=True)
            st.markdown("---")
            
            for name, amount in debtors.items():
                qr = get_qr(secrets_owner, secrets_iban, amount, f"BJ {name}")
                with st.expander(f"🔴 {name} schuldet {amount:.2f} €"):
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.image(qr, width=150)
                    with c2:
                        st.markdown(f"### {amount:.2f} €")
                        st.caption("Scan to Pay via Banking App")
