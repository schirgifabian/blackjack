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

# --- 2. LUXURY CSS ENGINE (Dein Design) ---
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
    
    /* METRIC CARDS (Custom for Stats) */
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

    /* CHIP BUTTONS STYLING */
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

# --- 3. LOGIC & DATA ---

def get_qr(name, iban, amount, purpose):
    """Generiert QR Code (Kombiniert Logik aus beiden Versionen)"""
    data = f"BCD\n002\n1\nSCT\n\n{name}\n{iban.replace(' ', '')}\nEUR{amount:.2f}\n\n\n{purpose}"
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(data)}"

def calc_netto(row):
    """Berechnet Netto (Kombiniert: Ausgaben/Auszahlungen sind negativ für die Bank)"""
    b = row["Betrag"]
    a = str(row["Aktion"]).lower()
    # Logik aus deiner Paste-Version: Ausgaben/Auszahlung verringern Bankbestand
    return -b if (("ausgabe" in a or "auszahlung" in a) and b > 0) else b

@st.cache_data(ttl=0)
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(worksheet="Buchungen", ttl=0)
        # Rename Map aus Paste-Version
        rename_map = {"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"}
        df = df.rename(columns=rename_map)
        
        expected_cols = ["Datum", "Name", "Aktion", "Betrag", "Zeitstempel"]
        for col in expected_cols:
            if col not in df.columns: df[col] = None

        if not df.empty:
            df["Betrag"] = pd.to_numeric(df["Betrag"].astype(str).str.replace(',', '.', regex=False), errors='coerce').fillna(0)
            
            # Robustes Datums-Parsing
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
    # Gleiche Struktur wie Design-Version
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
        # LIVE FEED (Design Version)
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

        # LEADERBOARD (Design Version)
        st.markdown("##### 👑 Leaderboard")
        df_p = df[~df["Aktion"].str.contains("Bank", case=False, na=False)]
        if not df_p.empty:
            # Profit aus Spielersicht: -Netto
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
    
    with st.container():
        # 1. PLAYER SELECTION (Design: Pills)
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.caption("SPIELER")
        
        # Design uses Pills, Logic supports "Sonstiges"
        p_sel = st.pills("Name", VALID_PLAYERS + ["Sonstiges"], selection_mode="single", default=VALID_PLAYERS[0], key="player_select", label_visibility="collapsed")
        
        final_name = p_sel
        if p_sel == "Sonstiges":
            final_name = st.text_input("Name/Zweck", placeholder="Pizza / Bier / Name", key="custom_name_input")
        st.markdown('</div>', unsafe_allow_html=True)

        # 2. CHIP SELECTOR (Design: Buttons)
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.caption("BETRAG WÄHLEN")
        
        cols = st.columns(len(CHIP_VALUES))
        for i, val in enumerate(CHIP_VALUES):
            cols[i].button(f"{val}", key=f"btn_{val}", on_click=set_amount, args=(val,), use_container_width=True)

        st.write("")
        amount = st.number_input("Betrag (€)", key="trans_amount", step=5.0, format="%.2f", label_visibility="visible")
        st.markdown('</div>', unsafe_allow_html=True)

        # 3. ACTION & SUBMIT (Design: 4 Buttons)
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.caption("AKTION")
        
        col_act1, col_act2 = st.columns(2)
        
        action_triggered = False
        typ = None
        sign = 0
        ntfy_tag = "moneybag"
        ntfy_title = "Update"
        
        with col_act1:
            if st.button("📥 KAUFEN (Einzahlen)", type="primary", use_container_width=True):
                typ, sign = "Einzahlung", 1
                ntfy_tag = "moneybag"
                action_triggered = True
            if st.button("📈 BANK GEWINN", use_container_width=True):
                typ, sign = "Bank Einnahme", 1
                ntfy_tag = "moneybag"
                action_triggered = True
                
        with col_act2:
            if st.button("📤 TAUSCHEN (Auszahlen)", type="primary", use_container_width=True):
                typ, sign = "Auszahlung", -1
                ntfy_tag = "chart_with_downwards_trend"
                action_triggered = True
            if st.button("💸 BANK VERLUST", use_container_width=True):
                typ, sign = "Bank Ausgabe", -1
                ntfy_tag = "chart_with_downwards_trend"
                action_triggered = True
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # PROCESSING LOGIC (Aus Paste-Version übernommen & angepasst)
        if action_triggered:
            if not final_name:
                st.error("⚠️ Bitte einen Namen wählen oder eingeben!")
            elif amount <= 0:
                st.error("⚠️ Betrag muss größer als 0 sein!")
            else:
                with st.spinner(f"Buche {typ} für {final_name}..."):
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
                        # Daten neu laden + anhängen
                        raw = conn.read(worksheet="Buchungen", ttl=0)
                        if not raw.empty:
                            rename_map = {"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"}
                            raw = raw.rename(columns=rename_map)
                            # Rück-Mapping für Speichern in DB (DB nutzt alte Spaltennamen?)
                            # Annahme: Google Sheet hat Spalten: Datum, Zeit, Spieler, Typ, Betrag
                            # Daher müssen wir sicherstellen, dass wir im korrekten Format speichern.
                            # Die Paste-Version speichert direkt new_entry, das passt zum Sheet.
                        
                        updated_df = pd.concat([raw, new_entry], ignore_index=True)
                        
                        # Mapping falls nötig rückgängig machen für Sheet (falls Sheet Header "Spieler" heißt)
                        # Hier nutzen wir einfach den concat, da new_entry die Spalten "Spieler", "Typ" etc hat.
                        # Wir müssen sicherstellen, dass raw auch diese Spalten hat.
                        # Um sicher zu gehen, laden wir raw ohne rename fürs Speichern:
                        raw_save = conn.read(worksheet="Buchungen", ttl=0)
                        updated_save = pd.concat([raw_save, new_entry], ignore_index=True)
                        
                        conn.update(worksheet="Buchungen", data=updated_save)
                        
                        # Ntfy Notification (Robust)
                        if "Bank" in typ:
                            try:
                                msg = f"{final_name}: {amount}€"
                                requests.post("https://ntfy.sh/bj-boys-dashboard", 
                                    data=msg.encode('utf-8'),
                                    headers={"Title": f"{typ}".encode('utf-8'), "Tags": ntfy_tag}, timeout=2)
                            except: pass

                        st.toast(f"✅ {typ}: {amount}€ erfolgreich!", icon="♠️")
                        if "Einnahme" in typ or "Gewinn" in typ: st.balloons()
                        
                        time.sleep(1)
                        st.cache_data.clear()
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Fehler beim Speichern: {e}")

# --- PAGE 3: STATS (Merged Features) ---
elif page == "Statistik":
    st.markdown("### 📊 Deep Analytics")
    
    # 1. FILTER (Aus Paste-Version, angepasst an Pills-Design)
    filter_options = ["Aktuelle Session", "Gesamt", "Dieser Monat", "Benutzerdefiniert"]
    scope = st.pills("Zeitraum", filter_options, default="Aktuelle Session")
    
    df_s = df.copy()
    today = datetime.now().date()
    
    # Filter Logik
    if scope == "Aktuelle Session":
        df_s = df_s[df_s["Full_Date"].dt.date.isin([today, today - timedelta(days=1)])]
    elif scope == "Dieser Monat":
        df_s = df_s[(df_s["Full_Date"].dt.month == today.month) & (df_s["Full_Date"].dt.year == today.year)]
    elif scope == "Benutzerdefiniert":
        c_date = st.container()
        d_range = c_date.date_input("Wähle Zeitraum:", value=(today - timedelta(days=7), today), format="DD.MM.YYYY")
        if isinstance(d_range, tuple) and len(d_range) == 2:
            df_s = df_s[(df_s["Full_Date"].dt.date >= d_range[0]) & (df_s["Full_Date"].dt.date <= d_range[1])]
        elif isinstance(d_range, tuple) and len(d_range) == 1:
            df_s = df_s[df_s["Full_Date"].dt.date == d_range[0]]

    # 2. TABS MIT NEUEN FEATURES
    t1, t2, t3 = st.tabs(["Performance", "Timeline", "Hall of Fame"])
    
    with t1:
        df_p = df_s[~df_s["Aktion"].str.contains("Bank", case=False, na=False)]
        if not df_p.empty:
            # Profit = -Netto (Spielersicht)
            agg = df_p.groupby("Name")["Netto"].sum().mul(-1).reset_index(name="Profit").sort_values("Profit", ascending=False)
            agg["Color"] = agg["Profit"].apply(lambda x: '#10B981' if x >= 0 else '#EF4444')
            
            fig = px.bar(agg, x="Profit", y="Name", orientation='h', text="Profit")
            fig.update_traces(marker_color=agg["Color"], texttemplate='%{text:+.2f} €', textposition='outside', textfont_family="JetBrains Mono")
            fig.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=400, yaxis_title=None, xaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Keine Daten im gewählten Zeitraum.")
            
    with t2:
        if not df_s.empty:
            df_h = df_s.sort_values("Full_Date")
            df_h["Balance"] = df_h["Netto"].cumsum()
            fig_l = px.area(df_h, x="Full_Date", y="Balance")
            fig_l.update_traces(line_color='#0F172A', fill_color='rgba(15, 23, 42, 0.1)')
            fig_l.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=350, yaxis_title=None, xaxis_title=None)
            st.plotly_chart(fig_l, use_container_width=True)
            
    with t3: # NEUES FEATURE: HALL OF FAME IM GLAS-DESIGN
        st.markdown("##### 👤 Spieler-Profil")
        sel_player = st.selectbox("Spieler wählen", VALID_PLAYERS)
        
        if sel_player and not df.empty:
            df_play = df[df["Name"] == sel_player].copy()
            if not df_play.empty:
                df_play["Player_Profit"] = -df_play["Netto"]
                df_play["Date_Only"] = df_play["Full_Date"].dt.date
                
                lifetime = df_play["Player_Profit"].sum()
                df_sess = df_play.groupby("Date_Only")["Player_Profit"].sum().reset_index()
                
                best_s = df_sess["Player_Profit"].max() if not df_sess.empty else 0
                worst_s = df_sess["Player_Profit"].min() if not df_sess.empty else 0
                
                # Badges
                badges = ""
                if lifetime > 50: badges += "🦈 Hai "
                if lifetime < -50: badges += "💸 Sponsor "
                if best_s > 100: badges += "🚀 Moon "
                
                st.caption(f"Status: {badges}")
                
                # Metrics in Glass Cards
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

# --- PAGE 4: SETTLEMENT (Kassensturz) ---
elif page == "Kassensturz":
    st.markdown("### 🏁 Abrechnung")
    
    secrets_iban = st.secrets.get("bank", {}).get("iban", "")
    secrets_owner = st.secrets.get("bank", {}).get("owner", "Bank")
    
    if not secrets_iban: 
        secrets_iban = st.text_input("IBAN eingeben:", placeholder="DE...")
        secrets_owner = st.text_input("Empfänger:", value="Casino Bank")
    
    # Logik aus Paste-Version: Nur Heute & Gestern betrachten
    today = datetime.now().date()
    mask_date = df["Full_Date"].dt.date.isin([today, today - timedelta(days=1)])
    mask_name = df["Name"].isin(VALID_PLAYERS)
    
    df_sess = df[mask_date & mask_name].copy()
    
    if df_sess.empty:
        st.info("Keine offenen Sessions für Heute oder Gestern.")
    else:
        # Saldo berechnen (Spielersicht)
        bilanz = df_sess.groupby("Name")["Netto"].sum().mul(-1)
        debtors = bilanz[bilanz < -0.01] # Nur wer Minus hat (Schulden bei Bank) muss zahlen
        
        if debtors.empty:
            st.balloons()
            st.success("Niemand hat Schulden! 🎉")
        else:
            st.markdown(f"**Empfänger:** {secrets_owner}<br><span style='font-family:monospace'>{secrets_iban}</span>", unsafe_allow_html=True)
            st.markdown("---")
            
            # Anzeige im Design-Look (Glass Cards mit QR)
            for name, amount in debtors.items():
                abs_amount = abs(amount)
                qr = get_qr(secrets_owner, secrets_iban, abs_amount, f"BJ {name}")
                
                st.markdown(f"""
                <div class="glass-card" style="padding: 0px; overflow: hidden;">
                    <div style="background: rgba(239, 68, 68, 0.1); padding: 15px; border-bottom: 1px solid rgba(255,255,255,0.5);">
                        <span style="font-weight:bold; font-size:18px;">🔴 {name}</span>
                        <span style="float:right; font-family:'JetBrains Mono'; font-weight:bold;">{abs_amount:.2f} €</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander(f"📱 QR Code für {name} anzeigen"):
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.image(qr, width=200)
                    with c2:
                        st.info("Scanne diesen Code mit deiner Banking App.")
