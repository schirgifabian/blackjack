import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pytz
import requests
import urllib.parse

# --- 1. CONFIG & SETUP ---
st.set_page_config(page_title="Blackjack Bank", page_icon="♠️", layout="centered")

# Konstanten
VALID_PLAYERS = sorted(["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi"])
THEME_COLOR = "#4F46E5" # Indigo-600

# --- 2. ULTIMATE CSS ENGINE ---
st.markdown("""
<style>
    /* FONTS IMPORTIEREN */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');

    /* BASE STYLES */
    .stApp {
        background-color: #F8FAFC; /* Slate-50 */
        font-family: 'Inter', sans-serif;
    }
    
    h1, h2, h3 {
        color: #0F172A;
        font-weight: 800;
        letter-spacing: -0.5px;
    }
    
    /* ZAHLEN DESIGN (Monospace für Finance-Look) */
    .money-font {
        font-family: 'JetBrains Mono', monospace;
        font-feature-settings: "zero" 1;
    }
    
    /* CUSTOM CARDS */
    .finance-card {
        background: white;
        border-radius: 24px;
        padding: 24px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01);
        border: 1px solid #F1F5F9;
        margin-bottom: 20px;
    }
    
    /* HERO BALANCE SECTION */
    .hero-balance {
        text-align: center;
        padding: 40px 0;
        background: linear-gradient(135deg, #4F46E5 0%, #3730A3 100%);
        border-radius: 0 0 32px 32px;
        margin: -60px -20px 30px -20px; /* Zieht den Header nach oben raus */
        color: white;
        box-shadow: 0 20px 25px -5px rgba(79, 70, 229, 0.3);
    }
    .hero-label {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 2px;
        opacity: 0.8;
        font-weight: 600;
    }
    .hero-amount {
        font-family: 'JetBrains Mono', monospace;
        font-size: 56px;
        font-weight: 700;
        margin-top: 10px;
        letter-spacing: -2px;
    }
    
    /* INPUT FIELDS OPTIMIERUNG */
    /* Macht Number Inputs riesig für Mobile */
    div[data-testid="stNumberInput"] input {
        font-family: 'JetBrains Mono', monospace;
        font-size: 24px;
        text-align: center;
        font-weight: bold;
        padding: 15px;
        border-radius: 12px;
    }
    
    /* BUTTONS */
    div.stButton > button {
        border-radius: 16px;
        height: 55px;
        font-weight: 600;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        border: none;
        transition: all 0.2s;
    }
    div.stButton > button:active {
        transform: scale(0.98);
    }

    /* HIDE STREAMLIT UI */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* TAB DESIGN */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: white;
        padding: 10px;
        border-radius: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px;
        font-weight: 600;
        border: none;
        background-color: transparent;
    }
    .stTabs [aria-selected="true"] {
        background-color: #F1F5F9 !important;
        color: #4F46E5 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. LOGIC CORE ---

def get_qr_url(name, iban, amount, purpose):
    data = f"BCD\n002\n1\nSCT\n\n{name}\n{iban.replace(' ', '')}\nEUR{amount:.2f}\n\n\n{purpose}"
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(data)}"

def calculate_netto(row):
    betrag = row["Betrag"]
    aktion = str(row["Aktion"]).lower()
    return -betrag if (("ausgabe" in aktion or "auszahlung" in aktion) and betrag > 0) else betrag

@st.cache_data(ttl=0)
def load_db():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(worksheet="Buchungen", ttl=0)
        df = df.rename(columns={"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"})
        if not df.empty:
            df["Betrag"] = pd.to_numeric(df["Betrag"].astype(str).str.replace(',', '.', regex=False), errors='coerce').fillna(0)
            df['Full_Date'] = pd.to_datetime(df['Datum'] + ' ' + df['Zeitstempel'].fillna('00:00'), format='%d.%m.%Y %H:%M', errors='coerce')
            df['Full_Date'] = df['Full_Date'].fillna(pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce'))
            df["Netto"] = df.apply(calculate_netto, axis=1)
            return df.sort_values("Full_Date", ascending=False).reset_index(drop=True), conn
    except: pass
    return pd.DataFrame(columns=["Datum", "Name", "Aktion", "Betrag", "Netto", "Full_Date"]), conn

df, conn = load_db()
kontostand = df["Netto"].sum() if not df.empty else 0.0

# --- 4. NAVIGATION BAR (Bottom-Style Logic via Sidebar) ---
with st.sidebar:
    st.markdown("### ♠️ Menu")
    nav = st.radio("Navigation", ["Home", "ATM (Buchen)", "Analytics", "Schulden"], label_visibility="collapsed")
    st.markdown("---")
    if st.button("Runde beenden (Reload)", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 5. PAGE: HOME ---
if nav == "Home":
    # HERO SECTION
    st.markdown(f"""
    <div class="hero-balance">
        <div class="hero-label">Aktueller Bank-Pot</div>
        <div class="hero-amount">{kontostand:,.2f} €</div>
    </div>
    """, unsafe_allow_html=True)

    if df.empty:
        st.info("Noch keine Spiele. Ab an den Tisch!")
    else:
        # QUICK STATS ROW
        col1, col2 = st.columns(2)
        today = datetime.now().date()
        df_today = df[df["Full_Date"].dt.date == today]
        
        with col1:
            st.markdown('<div class="finance-card" style="text-align:center; padding:15px;">', unsafe_allow_html=True)
            st.caption("Verkauf Heute")
            st.markdown(f'<div class="money-font" style="font-size:20px; color:#10B981;">+{df_today[df_today["Netto"] > 0]["Netto"].sum():.0f} €</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col2:
            st.markdown('<div class="finance-card" style="text-align:center; padding:15px;">', unsafe_allow_html=True)
            st.caption("Payout Heute")
            st.markdown(f'<div class="money-font" style="font-size:20px; color:#EF4444;">{df_today[df_today["Netto"] < 0]["Netto"].sum():.0f} €</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        # LEADERBOARD WIDGET
        st.markdown("### 🏆 Top Performer")
        df_players = df[~df["Aktion"].str.contains("Bank", case=False)]
        
        if not df_players.empty:
            lb = df_players.groupby("Name")["Netto"].sum().mul(-1).reset_index(name="Profit").sort_values("Profit", ascending=False).head(5)
            
            # Custom HTML Table for full control
            html_table = '<div class="finance-card" style="padding:0; overflow:hidden;">'
            for idx, row in lb.iterrows():
                rank = idx + 1
                medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank}."
                color = "#10B981" if row['Profit'] >= 0 else "#EF4444"
                bg = "#F8FAFC" if rank % 2 == 0 else "white"
                
                html_table += f"""
                <div style="display:flex; justify-content:space-between; align-items:center; padding:16px 20px; background:{bg}; border-bottom:1px solid #F1F5F9;">
                    <div style="display:flex; align-items:center; gap:12px;">
                        <span style="font-size:18px;">{medal}</span>
                        <span style="font-weight:600; font-size:15px;">{row['Name']}</span>
                    </div>
                    <span class="money-font" style="color:{color}; font-weight:bold;">{row['Profit']:+.2f} €</span>
                </div>
                """
            html_table += "</div>"
            st.markdown(html_table, unsafe_allow_html=True)

# --- 6. PAGE: ATM (BUCHUNG) ---
elif nav == "ATM (Buchen)":
    st.markdown("<h2 style='text-align:center; margin-bottom:30px;'>ATM Transfer 🏧</h2>", unsafe_allow_html=True)
    
    with st.container():
        st.markdown('<div class="finance-card">', unsafe_allow_html=True)
        
        # 1. Spieler Wahl (Pills)
        st.caption("ACCOUNT WÄHLEN")
        player = st.pills("Spieler", VALID_PLAYERS + ["Manuell"], selection_mode="single", default=VALID_PLAYERS[0], label_visibility="collapsed")
        if player == "Manuell":
            player = st.text_input("Name/Zweck", placeholder="Zweck eingeben")
            
        st.markdown("---")
        
        # 2. Betrag (Huge)
        st.caption("BETRAG (€)")
        amount = st.number_input("Betrag", value=10.0, step=5.0, min_value=0.0, format="%.2f", label_visibility="collapsed")
        
        st.markdown("---")
        
        # 3. Aktion (Icons)
        st.caption("AKTION")
        # Custom Layout for Actions
        c1, c2 = st.columns(2)
        type_choice = st.radio("Typ", ["Einzahlung (Kauf)", "Auszahlung (Rückgabe)", "Bank Einnahme", "Bank Ausgabe"], label_visibility="collapsed")
        
        st.markdown('</div>', unsafe_allow_html=True)

        # 4. Action Button
        action_map = {
            "Einzahlung (Kauf)": "Einzahlung",
            "Auszahlung (Rückgabe)": "Auszahlung",
            "Bank Einnahme": "Bank Einnahme",
            "Bank Ausgabe": "Bank Ausgabe"
        }
        
        if st.button("💸 Transaktion bestätigen", type="primary", use_container_width=True):
            if player:
                tz = pytz.timezone('Europe/Berlin')
                now = datetime.now(tz)
                typ_clean = action_map[type_choice]
                
                new_row = pd.DataFrame([{
                    "Datum": now.strftime("%d.%m.%Y"),
                    "Zeit": now.strftime("%H:%M"),
                    "Spieler": player,
                    "Typ": typ_clean,
                    "Betrag": amount
                }])
                
                try:
                    raw_df = conn.read(worksheet="Buchungen", ttl=0)
                    conn.update(worksheet="Buchungen", data=pd.concat([raw_df, new_row], ignore_index=True))
                    
                    # NTFY Hook
                    if "Bank" in typ_clean:
                        try:
                            topic, title, tag = "bj-boys-dashboard", "Bank Update", "moneybag"
                            if "Ausgabe" in typ_clean: tag = "chart_with_downwards_trend"
                            requests.post(f"https://ntfy.sh/{topic}", 
                                        data=f"{player}: {amount}€".encode('utf-8'),
                                        headers={"Title": title.encode('utf-8'), "Tags": tag})
                        except: pass

                    st.toast("Transaktion erfolgreich!", icon="✅")
                    st.cache_data.clear()
                    
                    # Receipt Animation
                    st.markdown(f"""
                    <div style="background:#ECFDF5; color:#065F46; padding:20px; border-radius:16px; text-align:center; border:1px solid #10B981; margin-top:20px;">
                        <div style="font-size:40px; margin-bottom:10px;">✅</div>
                        <div style="font-weight:bold; font-size:18px;">{amount:.2f} €</div>
                        <div style="opacity:0.8;">{typ_clean} für {player}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                except Exception as e:
                    st.error(f"Fehler: {e}")

# --- 7. PAGE: ANALYTICS ---
elif nav == "Analytics":
    st.markdown("## 📊 Market Data")
    
    # Timeframe Selector als Segmented Control
    mode = st.pills("Zeitraum", ["Aktuelle Session", "Gesamt"], selection_mode="single", default="Aktuelle Session")
    
    df_stats = df.copy()
    if mode == "Aktuelle Session":
        today = datetime.now().date()
        df_stats = df_stats[df_stats["Full_Date"].dt.date.isin([today, today - timedelta(days=1)])]

    tab_perf, tab_flow = st.tabs(["Performance", "Cashflow"])
    
    with tab_perf:
        df_p = df_stats[~df_stats["Aktion"].str.contains("Bank", case=False)]
        if not df_p.empty:
            data = df_p.groupby("Name")["Netto"].sum().mul(-1).reset_index(name="Profit").sort_values("Profit", ascending=False)
            data["Color"] = data["Profit"].apply(lambda x: '#4F46E5' if x >= 0 else '#94A3B8') # Indigo vs Slate
            
            fig = px.bar(data, x="Name", y="Profit", text="Profit")
            fig.update_traces(marker_color=data["Color"], texttemplate='%{text:+.0f}', textposition='outside', textfont_family="JetBrains Mono")
            fig.update_layout(
                template="plotly_white",
                plot_bgcolor='rgba(0,0,0,0)',
                yaxis=dict(showgrid=True, gridcolor='#F1F5F9', title=None, showticklabels=False),
                xaxis=dict(title=None),
                margin=dict(t=30, l=0, r=0, b=0),
                height=320,
                font=dict(family="Inter")
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            
    with tab_flow:
        if not df_stats.empty:
            df_hist = df_stats.sort_values("Full_Date")
            df_hist["Bankverlauf"] = df_hist["Netto"].cumsum()
            
            fig_l = px.area(df_hist, x="Full_Date", y="Bankverlauf")
            fig_l.update_traces(line_color='#4F46E5', fill_color='rgba(79, 70, 229, 0.1)', line_shape='spline')
            fig_l.update_layout(
                template="plotly_white",
                plot_bgcolor='rgba(0,0,0,0)',
                yaxis=dict(showgrid=True, gridcolor='#F1F5F9', title=None),
                xaxis=dict(title=None, showgrid=False),
                margin=dict(t=20, l=0, r=0, b=0),
                height=320
            )
            st.plotly_chart(fig_l, use_container_width=True, config={"displayModeBar": False})

# --- 8. PAGE: SCHULDEN (SETTLEMENT) ---
elif nav == "Schulden":
    st.markdown("## 🏁 Settlement")
    st.info("Berechnung basierend auf der aktuellen Session (Heute & Gestern).")

    # Secrets
    iban = st.secrets.get("bank", {}).get("iban", "")
    owner = st.secrets.get("bank", {}).get("owner", "Blackjack Bank")
    if not iban: iban = st.text_input("IBAN für QR Code:")
    
    today = datetime.now().date()
    df_sess = df[df["Full_Date"].dt.date.isin([today, today - timedelta(days=1)]) & df["Name"].isin(VALID_PLAYERS)]
    
    if df_sess.empty:
        st.markdown('<div class="finance-card" style="text-align:center;">💤 Keine aktive Session.</div>', unsafe_allow_html=True)
    else:
        # Logik: Netto > 0 heißt, man hat Chips gekauft (Geld geschuldet) und nicht zurückgetauscht.
        bilanz = df_sess.groupby("Name")["Netto"].sum()
        debtors = bilanz[bilanz > 0]
        
        if debtors.empty:
            st.success("Alles ausgeglichen! 🎉")
        else:
            for name, amount in debtors.items():
                qr_link = get_qr_url(owner, iban, amount, f"BJ {name}")
                
                # Card Design für Schuldner
                st.markdown(f"""
                <div class="finance-card" style="display:flex; align-items:center; gap:20px;">
                    <img src="{qr_link}" width="100" style="border-radius:10px;">
                    <div style="flex-grow:1;">
                        <h3 style="margin:0;">{name}</h3>
                        <div style="color:#64748B; font-size:14px; margin-bottom:5px;">muss zahlen</div>
                        <div class="money-font" style="font-size:24px; color:#EF4444; font-weight:bold;">{amount:.2f} €</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
