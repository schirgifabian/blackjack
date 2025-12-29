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

# --- SESSION STATE SETUP ---
if 'trans_amount' not in st.session_state:
    st.session_state.trans_amount = 10.0
if 'selected_player' not in st.session_state:
    st.session_state.selected_player = VALID_PLAYERS[0]

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
    
    /* GLASS CONTAINER */
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
    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        padding: 0 !important;
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
    
    /* VAULT DISPLAY */
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
    
    /* METRIC CARDS */
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

    /* CHIP BUTTONS */
    div[data-testid="column"] button {
        border-radius: 16px;
        height: 50px;
        width: 100%;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        border: 1px solid #E2E8F0;
        background: white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        transition: all 0.2s;
    }
    div[data-testid="column"] button:hover {
        border-color: #0F172A;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    div[data-testid="column"] button:focus {
        background: #F1F5F9;
        color: #0F172A;
        border-color: #0F172A;
    }

    /* ACTION BUTTONS */
    button[kind="primary"] {
        border-radius: 16px;
        height: 60px;
        font-weight: 600;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    button[kind="secondary"] {
        border-radius: 16px;
        height: 60px;
        border: 1px solid #E2E8F0;
        background: rgba(255,255,255,0.8);
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

# --- 3. LOGIC & DATA ---

def get_qr(name, iban, amount, purpose):
    data = f"BCD\n002\n1\nSCT\n\n{name}\n{iban.replace(' ', '')}\nEUR{amount:.2f}\n\n\n{purpose}"
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(data)}"

def calc_netto(row):
    b = row["Betrag"]
    a = str(row["Aktion"]).lower()
    return -b if (("ausgabe" in a or "auszahlung" in a) and b > 0) else b

@st.cache_data(ttl=0)
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(worksheet="Buchungen", ttl=0)
        rename_map = {"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"}
        df = df.rename(columns=rename_map)
        
        expected_cols = ["Datum", "Name", "Aktion", "Betrag", "Zeitstempel"]
        for col in expected_cols:
            if col not in df.columns: df[col] = None

        if not df.empty:
            df["Betrag"] = pd.to_numeric(df["Betrag"].astype(str).str.replace(',', '.', regex=False), errors='coerce').fillna(0)
            df['Full_Date'] = pd.to_datetime(df['Datum'] + ' ' + df['Zeitstempel'].fillna('00:00'), format='%d.%m.%Y %H:%M', errors='coerce')
            df['Full_Date'] = df['Full_Date'].fillna(pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce'))
            df["Netto"] = df.apply(calc_netto, axis=1)
            return df.sort_values("Full_Date", ascending=False).reset_index(drop=True), conn
    except Exception: 
        pass
    return pd.DataFrame(columns=["Datum", "Zeitstempel", "Name", "Aktion", "Betrag", "Netto", "Full_Date"]), conn

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

# --- HEADER (visible on Overview) ---
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
        st.markdown("##### 📡 Live Feed")
        for i, row in df.head(5).iterrows():
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
        df_p = df[~df["Aktion"].str.contains("Bank", case=False, na=False)]
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

# --- PAGE 2: QUICK TRANSACTION ---
elif page == "Transaktion":
    st.markdown("### 🎲 Quick Action")
    
    # 1. PLAYER SECTION
    with st.container(border=True):
        st.caption("👤 SPIELER WÄHLEN")
        p_sel = st.pills("Name", VALID_PLAYERS + ["Sonstiges"], selection_mode="single", default=VALID_PLAYERS[0], key="player_select", label_visibility="collapsed")
        
        final_name = p_sel
        if p_sel == "Sonstiges":
            final_name = st.text_input("Name/Zweck", placeholder="Name oder Zweck eingeben", key="custom_name_input")

    # 2. AMOUNT SECTION
    with st.container(border=True):
        st.caption("💰 BETRAG")
        
        # Chips als Quick-Select
        cols = st.columns(len(CHIP_VALUES))
        for i, val in enumerate(CHIP_VALUES):
            cols[i].button(f"{val}", key=f"btn_{val}", on_click=set_amount, args=(val,), use_container_width=True)

        st.write("")
        # Input Field (Number)
        amount = st.number_input("Betrag (€)", key="trans_amount", step=5.0, format="%.2f", label_visibility="collapsed")

    # 3. ACTION SECTION
    with st.container(border=True):
        st.caption("⚡ AKTION")
        
        c1, c2 = st.columns(2)
        
        action_triggered = False
        typ = None
        sign = 0
        ntfy_tag = "moneybag"
        
        with c1:
            if st.button("📥 Einzahlen (Kaufen)", type="primary", use_container_width=True):
                typ, sign = "Einzahlung", 1
                ntfy_tag = "moneybag"
                action_triggered = True
            if st.button("📈 Bank Gewinn", type="secondary", use_container_width=True):
                typ, sign = "Bank Einnahme", 1
                ntfy_tag = "moneybag"
                action_triggered = True
                
        with c2:
            if st.button("📤 Auszahlen (Tauschen)", type="primary", use_container_width=True):
                typ, sign = "Auszahlung", -1
                ntfy_tag = "chart_with_downwards_trend"
                action_triggered = True
            if st.button("💸 Bank Verlust", type="secondary", use_container_width=True):
                typ, sign = "Bank Ausgabe", -1
                ntfy_tag = "chart_with_downwards_trend"
                action_triggered = True
        
        # PROCESSING LOGIC
        if action_triggered:
            if not final_name:
                st.error("⚠️ Bitte Name wählen!")
            elif amount <= 0:
                st.error("⚠️ Betrag > 0 erforderlich!")
            else:
                with st.spinner(f"Buche {typ}..."):
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
                        if not raw.empty:
                            raw = raw.rename(columns={"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"})
                        
                        # Speichern
                        raw_save = conn.read(worksheet="Buchungen", ttl=0)
                        updated_save = pd.concat([raw_save, new_entry], ignore_index=True)
                        conn.update(worksheet="Buchungen", data=updated_save)
                        
                        # Notify
                        if "Bank" in typ:
                            try:
                                msg = f"{final_name}: {amount}€"
                                requests.post("https://ntfy.sh/bj-boys-dashboard", 
                                    data=msg.encode('utf-8'),
                                    headers={"Title": f"{typ}".encode('utf-8'), "Tags": ntfy_tag}, timeout=2)
                            except: pass

                        st.toast(f"✅ {typ}: {amount:.2f}€", icon="♠️")
                        if "Einnahme" in typ or "Gewinn" in typ: st.balloons()
                        
                        time.sleep(1)
                        st.cache_data.clear()
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Fehler: {e}")
                        
    # --- PUNKT 1: UNDO FUNKTION ---
    st.markdown("---")
    if not df.empty:
        last_entry = df.iloc[0] # Da wir descending sortieren, ist 0 der neueste
        with st.expander(f"↩️ Letzte Aktion rückgängig machen ({last_entry['Name']}: {last_entry['Betrag']}€)"):
            st.warning("Wirklich löschen? Das entfernt die letzte Zeile aus dem Sheet.")
            if st.button("🗑 Ja, letzte Buchung löschen", type="secondary"):
                try:
                    # Rohdaten laden (unsortiert, wie im Sheet)
                    raw_df = conn.read(worksheet="Buchungen", ttl=0)
                    if not raw_df.empty:
                        # Letzte Zeile droppen
                        raw_df = raw_df.iloc[:-1]
                        conn.update(worksheet="Buchungen", data=raw_df)
                        st.toast("Letzte Buchung gelöscht!", icon="🗑")
                        time.sleep(1)
                        st.cache_data.clear()
                        st.rerun()
                except Exception as e:
                    st.error(f"Fehler beim Löschen: {e}")

# --- PAGE 3: STATS ---
elif page == "Statistik":
    st.markdown("### 📊 Deep Analytics")
    
    # --- PUNKT 3: BANK PROFIT (House Edge) ---
    # Logik: Was die Bank gewonnen hat = Umkehrung dessen was Spieler "Netto" haben (exkl. Bank-Transaktionen)
    # Oder: Wir schauen auf Bank Transaktionen (Gewinn/Verlust) + Chip Overflow
    # Einfachste Metrik für "Gewinnt die Bank": 
    # Wenn Spieler-Saldo negativ ist (Spieler haben verloren), ist die Bank im Plus.
    
    bank_profit = df[~df["Aktion"].str.contains("Bank", case=False, na=False)]["Netto"].sum() * -1
    # Korrektur um explizite Bank-Transaktionen, falls diese "außerhalb" des Spiels waren?
    # Wir nehmen hier an: Bank Profit = Summe aller Spieler-Verluste.
    
    st.markdown(f"""
    <div class="glass-card" style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <div class="metric-label">🏦 House Performance</div>
            <div style="font-size: 12px; opacity: 0.7;">(Spielerverluste vs. Gewinne)</div>
        </div>
        <div class="metric-value" style="color: {'#10B981' if bank_profit >= 0 else '#EF4444'}">
            {bank_profit:+.2f} €
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 1. Globale Balance-Historie berechnen
    df_calc = df.sort_values("Full_Date").copy()
    df_calc["Balance"] = df_calc["Netto"].cumsum()
    
    # 2. Session-Logik
    def get_session_date(dt):
        if pd.isna(dt): return datetime.now().date()
        return dt.date() - timedelta(days=1) if dt.hour < 6 else dt.date()

    df_calc["Session_Date"] = df_calc["Full_Date"].apply(get_session_date)

    # 3. Filter anwenden
    filter_options = ["Aktuelle Session", "Gesamt", "Dieser Monat", "Benutzerdefiniert"]
    scope = st.pills("Zeitraum", filter_options, default="Aktuelle Session")
    
    today = datetime.now().date()
    
    if scope == "Aktuelle Session":
        current_session_date = get_session_date(datetime.now())
        df_s = df_calc[df_calc["Session_Date"] == current_session_date]
    elif scope == "Gesamt":
        df_s = df_calc
    elif scope == "Dieser Monat":
        df_s = df_calc[(df_calc["Full_Date"].dt.month == today.month) & (df_calc["Full_Date"].dt.year == today.year)]
    elif scope == "Benutzerdefiniert":
        c_date = st.container()
        d_range = c_date.date_input("Wähle Zeitraum:", value=(today - timedelta(days=7), today), format="DD.MM.YYYY")
        if isinstance(d_range, tuple) and len(d_range) == 2:
            df_s = df_calc[(df_calc["Full_Date"].dt.date >= d_range[0]) & (df_calc["Full_Date"].dt.date <= d_range[1])]
        elif isinstance(d_range, tuple) and len(d_range) == 1:
            df_s = df_calc[df_calc["Full_Date"].dt.date == d_range[0]]
    else:
        df_s = df_calc

    t1, t2, t3 = st.tabs(["Performance", "Timeline", "Hall of Fame"])
    
    with t1:
        # Profit pro Spieler
        df_p = df_s[~df_s["Aktion"].str.contains("Bank", case=False, na=False)]
        if not df_p.empty:
            agg = df_p.groupby("Name")["Netto"].sum().mul(-1).reset_index(name="Profit").sort_values("Profit", ascending=False)
            agg["Color"] = agg["Profit"].apply(lambda x: '#10B981' if x >= 0 else '#EF4444')
            
            fig = px.bar(agg, x="Profit", y="Name", orientation='h', text="Profit")
            fig.update_traces(marker_color=agg["Color"], texttemplate='%{text:+.2f} €', textposition='outside', textfont_family="JetBrains Mono")
            fig.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=400, yaxis_title=None, xaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Keine Daten im gewählten Zeitraum.")
            
    with t2:
        # Timeline
        if not df_s.empty:
            df_h = df_s.sort_values("Full_Date")
            fig_l = px.area(df_h, x="Full_Date", y="Balance")
            
            min_y = df_h["Balance"].min()
            max_y = df_h["Balance"].max()
            padding = (max_y - min_y) * 0.1 if max_y != min_y else 10
            
            fig_l.update_yaxes(range=[min_y - padding, max_y + padding])
            fig_l.update_traces(line_color='#0F172A', fill_color='rgba(15, 23, 42, 0.1)')
            fig_l.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=350, yaxis_title=None, xaxis_title=None)
            st.plotly_chart(fig_l, use_container_width=True)
        else:
            st.info("Keine Transaktionen in diesem Zeitraum.")
            
    with t3:
        st.markdown("##### 👤 Spieler-Profil")
        sel_player = st.selectbox("Spieler wählen", VALID_PLAYERS)
        
        if sel_player and not df_calc.empty:
            df_play = df_calc[df_calc["Name"] == sel_player].copy()
            if not df_play.empty:
                df_play["Player_Profit"] = -df_play["Netto"]
                lifetime = df_play["Player_Profit"].sum()
                df_sess = df_play.groupby("Session_Date")["Player_Profit"].sum().reset_index()
                best_s = df_sess["Player_Profit"].max() if not df_sess.empty else 0
                worst_s = df_sess["Player_Profit"].min() if not df_sess.empty else 0
                
                badges = ""
                if lifetime > 50: badges += "🦈 Hai "
                if lifetime < -50: badges += "💸 Sponsor "
                if best_s > 100: badges += "🚀 Moon "
                if worst_s < -100: badges += "💀 Tilt "
                
                st.caption(f"Status: {badges}")
                
                c1, c2, c3 = st.columns(3)
                col_data = [(c1, "Lifetime", lifetime), (c2, "Best Session", best_s), (c3, "Worst Session", worst_s)]
                for col, label, val in col_data:
                    c_color = "#10B981" if val >= 0 else "#EF4444"
                    with col:
                        st.markdown(f"""
                        <div class="glass-card" style="padding:15px; text-align:center;">
                            <div class="metric-label">{label}</div>
                            <div class="metric-value" style="color:{c_color}">{val:+.2f} €</div>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("Keine Daten für diesen Spieler.")

# --- PAGE 4: SETTLEMENT (LIFETIME) ---
elif page == "Kassensturz":
    # --- PUNKT 5: LIFETIME ABRECHNUNG ---
    st.markdown("### 🏁 Abrechnung (Gesamt)")
    st.info("ℹ️ Berechnet den aktuellen Kontostand aller Spieler über die gesamte Laufzeit (Lifetime). Zeigt an, wer noch Schulden hat.")
    
    secrets_iban = st.secrets.get("bank", {}).get("iban", "")
    secrets_owner = st.secrets.get("bank", {}).get("owner", "Bank")
    
    if not secrets_iban: 
        secrets_iban = st.text_input("IBAN eingeben:", placeholder="DE...")
        secrets_owner = st.text_input("Empfänger:", value="Casino Bank")
    
    # Wir nehmen ALLE Daten, filtern nicht nach Datum
    # Nur Spieler berücksichtigen
    df_sess = df[df["Name"].isin(VALID_PLAYERS)].copy()
    
    if df_sess.empty:
        st.info("Noch keine Buchungen vorhanden.")
    else:
        # Bilanz berechnen
        bilanz_gesamt = df_sess.groupby("Name")["Netto"].sum().mul(-1)
        
        # Aufteilen in Schuldner (Müssen zahlen) und Gläubiger (Kriegen Geld)
        # Filterung kleiner Beträge wegen Floating Point Ungenauigkeiten
        debtors = bilanz_gesamt[bilanz_gesamt < -0.1]
        creditors = bilanz_gesamt[bilanz_gesamt > 0.1]
        
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("🔴 Zahler")
            st.caption("Müssen an die Bank überweisen")
            if debtors.empty:
                st.write("Keine offenen Zahlungen.")
            else:
                for name, amount in debtors.items():
                    abs_amount = abs(amount)
                    qr = get_qr(secrets_owner, secrets_iban, abs_amount, f"BJ {name}")
                    
                    st.markdown(f"""
                    <div class="glass-card" style="padding: 10px; margin-bottom: 10px; border-left: 5px solid #EF4444;">
                        <div style="font-weight:bold; font-size:16px;">{name}</div>
                        <div style="font-family:'JetBrains Mono'; color:#EF4444;">{amount:.2f} €</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    with st.expander(f"📱 QR für {name}"):
                        st.image(qr, width=150)

        with c2:
            st.subheader("🟢 Empfänger")
            st.caption("Bank schuldet diesen Spielern")
            if creditors.empty:
                st.write("Niemand.")
            else:
                for name, amount in creditors.items():
                    st.markdown(f"""
                    <div class="glass-card" style="padding: 10px; margin-bottom: 10px; border-left: 5px solid #10B981;">
                        <div style="font-weight:bold; font-size:16px;">{name}</div>
                        <div style="font-family:'JetBrains Mono'; color:#10B981;">+{amount:.2f} €</div>
                    </div>
                    """, unsafe_allow_html=True)

        if debtors.empty and creditors.empty:
            st.balloons()
            st.success("Alles ausgeglichen! 🎉")
