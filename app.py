import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pytz
import requests
import urllib.parse

# --- PAGE CONFIG ---
st.set_page_config(page_title="Blackjack Bank", page_icon="♠️", layout="centered")

# --- KONSTANTEN ---
VALID_PLAYERS = sorted(["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi"])

# --- PREMIUM CSS STYLING ---
st.markdown("""
<style>
    /* 1. Schriftart importieren (Inter) */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #1E293B;
    }
    
    /* 2. Hintergrund & Globales */
    .stApp {
        background: #F1F5F9; /* Slate-100 */
    }
    
    /* 3. Karten-Design (Soft UI) */
    div[data-testid="stVerticalBlock"] > div[style*="background-color"] {
        background-color: #FFFFFF;
        border-radius: 20px;
        padding: 24px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.025);
        border: 1px solid #F8FAFC;
    }
    
    /* 4. Metriken (KPI Boxen) */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        padding: 16px;
        border-radius: 16px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        transition: transform 0.2s;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    
    /* 5. Großer Kontostand */
    .balance-card {
        background: linear-gradient(135deg, #0F172A 0%, #334155 100%);
        color: white;
        padding: 40px 20px;
        border-radius: 24px;
        text-align: center;
        margin-bottom: 30px;
        box-shadow: 0 20px 25px -5px rgba(15, 23, 42, 0.3);
    }
    .balance-label {
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 2px;
        opacity: 0.8;
        margin-bottom: 8px;
        font-weight: 600;
    }
    .balance-value {
        font-size: 56px;
        font-weight: 800;
        letter-spacing: -1px;
    }
    .balance-neg {
        background: linear-gradient(135deg, #991B1B 0%, #EF4444 100%);
    }

    /* 6. Tabs verschönern */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #FFFFFF;
        border-radius: 30px;
        padding: 8px 20px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        border: 1px solid #E2E8F0;
        font-weight: 600;
        font-size: 14px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0F172A !important;
        color: white !important;
    }

    /* Hide Decorations */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- HELPER FUNKTIONEN ---
def generate_epc_qr_url(name, iban, amount, purpose):
    iban_clean = iban.replace(" ", "").upper()
    amount_str = f"EUR{amount:.2f}"
    epc_data = f"BCD\n002\n1\nSCT\n\n{name}\n{iban_clean}\n{amount_str}\n\n\n{purpose}\n"
    data_encoded = urllib.parse.quote(epc_data)
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={data_encoded}"

def berechne_netto(row):
    betrag = row["Betrag"]
    aktion = str(row["Aktion"]).lower()
    if ("ausgabe" in aktion or "auszahlung" in aktion) and betrag > 0:
        return -betrag
    return betrag

@st.cache_data(ttl=0)
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(worksheet="Buchungen", ttl=0)
        rename_map = {"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"}
        df = df.rename(columns=rename_map)
        
        if not df.empty:
            df["Betrag"] = df["Betrag"].astype(str).str.replace(',', '.', regex=False)
            df["Betrag"] = pd.to_numeric(df["Betrag"], errors='coerce').fillna(0)
            df['Full_Date'] = pd.to_datetime(df['Datum'] + ' ' + df['Zeitstempel'].fillna('00:00'), format='%d.%m.%Y %H:%M', errors='coerce')
            df['Full_Date'] = df['Full_Date'].fillna(pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce'))
            df["Netto"] = df.apply(berechne_netto, axis=1)
            df = df.sort_values(by="Full_Date", ascending=False).reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame(columns=["Datum", "Name", "Aktion", "Betrag", "Netto", "Full_Date"])

# --- DATEN LADEN ---
conn = st.connection("gsheets", type=GSheetsConnection)
df = load_data()
kontostand = df["Netto"].sum() if not df.empty else 0.0

# --- SIDEBAR NAV ---
st.sidebar.markdown("## ♠️ Blackjack Bank")
page = st.sidebar.radio("Navigation", ["Dashboard", "Neue Buchung", "Statistik", "Abrechnung"], label_visibility="collapsed")
st.sidebar.markdown("---")
if st.sidebar.button("🔄 Reload App", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# --- HEADER BEREICH (Immer sichtbar) ---
if page == "Dashboard":
    # Custom HTML Card für den Kontostand
    css_class = "balance-card" if kontostand >= 0 else "balance-card balance-neg"
    balance_fmt = f"{kontostand:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    st.markdown(f"""
    <div class="{css_class}">
        <div class="balance-label">Aktueller Bank-Stand</div>
        <div class="balance-value">{balance_fmt} €</div>
    </div>
    """, unsafe_allow_html=True)

# --- PAGE 1: DASHBOARD ---
if page == "Dashboard":
    if df.empty:
        st.info("👋 Willkommen! Starte mit deiner ersten Buchung.")
    else:
        # KPI Row
        col1, col2, col3 = st.columns(3)
        
        today = datetime.now().date()
        df_today = df[df["Full_Date"].dt.date == today]
        
        turnover_in = df_today[df_today["Aktion"].str.contains("Einzahlung", na=False)]["Betrag"].sum()
        turnover_out = df_today[df_today["Aktion"].str.contains("Auszahlung", na=False)]["Betrag"].sum()
        bank_delta_today = df_today["Netto"].sum()

        col1.metric("Verkauf (Heute)", f"{turnover_in:.0f} €")
        col2.metric("Auszahlung (Heute)", f"{turnover_out:.0f} €")
        col3.metric("Bank Gewinn (Heute)", f"{bank_delta_today:+.2f} €", delta=bank_delta_today)

        st.write("")
        st.markdown("##### 🔥 Live Leaderboard")
        
        # Schöne Tabelle mit Progress Bars
        df_players = df[~df["Aktion"].str.contains("Bank", case=False)]
        if not df_players.empty:
            lb = df_players.groupby("Name")["Netto"].sum().mul(-1).reset_index(name="Profit").sort_values("Profit", ascending=False)
            
            st.dataframe(
                lb,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Name": st.column_config.TextColumn("Spieler", width="medium"),
                    "Profit": st.column_config.ProgressColumn(
                        "Gewinn / Verlust",
                        format="%.2f €",
                        min_value=float(lb["Profit"].min()),
                        max_value=float(lb["Profit"].max()),
                    )
                }
            )
        
        st.write("")
        st.markdown("##### 🕒 Letzte Transaktionen")
        st.dataframe(
            df[["Zeitstempel", "Name", "Aktion", "Betrag"]].head(5),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Zeitstempel": st.column_config.TextColumn("Uhrzeit", width="small"),
                "Betrag": st.column_config.NumberColumn("Betrag", format="%.2f €")
            }
        )

# --- PAGE 2: BUCHUNG ---
elif page == "Neue Buchung":
    st.markdown("### 💸 Transaktion erfassen")
    
    with st.container(border=True):
        st.caption("Schritt 1: Wer?")
        # Modern Chips selection
        buchung_namen = VALID_PLAYERS + ["Manuelle Ausgabe 📝"]
        auswahl_name = st.pills("", buchung_namen, selection_mode="single", default=VALID_PLAYERS[0])
        
        final_name = auswahl_name
        if auswahl_name == "Manuelle Ausgabe 📝":
            final_name = st.text_input("Verwendungszweck", placeholder="z.B. Pizza Bestellung")

        st.write("")
        st.caption("Schritt 2: Wie viel & Was?")
        
        col_amount, col_type = st.columns([1, 1.5])
        with col_amount:
            betrag_input = st.number_input("Betrag", value=10.0, step=5.0, format="%.2f")
        
        with col_type:
            # Clean Labels
            aktion_map = {
                "📥 Einzahlung (Kauf)": "Einzahlung",
                "📤 Auszahlung (Rückgabe)": "Auszahlung",
                "🏦 Bank Einnahme": "Bank Einnahme",
                "💸 Bank Ausgabe": "Bank Ausgabe"
            }
            aktion_label = st.radio("Typ", list(aktion_map.keys()), label_visibility="collapsed")
            typ_short = aktion_map[aktion_label]

        st.markdown("---")
        
        if st.button("Transaktion buchen", type="primary", use_container_width=True):
            if final_name:
                tz = pytz.timezone('Europe/Berlin')
                now = datetime.now(tz)
                
                neuer_eintrag = pd.DataFrame([{
                    "Datum": now.strftime("%d.%m.%Y"),
                    "Zeit": now.strftime("%H:%M"),
                    "Spieler": final_name,
                    "Typ": typ_short,
                    "Betrag": betrag_input
                }])
                
                try:
                    df_raw = conn.read(worksheet="Buchungen", ttl=0)
                    updated_df = pd.concat([df_raw, neuer_eintrag], ignore_index=True)
                    conn.update(worksheet="Buchungen", data=updated_df)
                    
                    # NTFY Integration
                    if "Bank" in typ_short:
                        try:
                            ntfy_topic = "bj-boys-dashboard"
                            msg_title = "💰 Bank Plus" if "Einnahme" in typ_short else "💸 Bank Minus"
                            msg_tag = "moneybag" if "Einnahme" in typ_short else "chart_with_downwards_trend"
                            requests.post(f"https://ntfy.sh/{ntfy_topic}", 
                                        data=f"{final_name}: {betrag_input}€".encode('utf-8'),
                                        headers={"Title": msg_title.encode('utf-8'), "Tags": msg_tag})
                        except: pass

                    st.cache_data.clear()
                    
                    # Success "Receipt"
                    st.success("Erfolgreich gebucht!")
                    st.markdown(f"""
                    <div style="background-color:#ECFDF5; padding:15px; border-radius:10px; border:1px solid #10B981; color:#065F46; text-align:center;">
                        <strong>{final_name}</strong><br>
                        {aktion_label}<br>
                        <span style="font-size:20px; font-weight:bold;">{betrag_input:.2f} €</span>
                    </div>
                    """, unsafe_allow_html=True)
                    
                except Exception as e:
                    st.error(f"Fehler: {e}")

# --- PAGE 3: STATISTIK ---
elif page == "Statistik":
    st.markdown("### 📈 Deep Dive")
    
    col_sel, col_dummy = st.columns([2, 1])
    with col_sel:
        zeitraum = st.selectbox("Zeitraum wählen", ["Gesamt", "Aktuelle Session", "Dieser Monat"])
    
    # Filter Logic
    df_stats = df.copy()
    today = datetime.now().date()
    
    if zeitraum == "Aktuelle Session":
        df_stats = df_stats[df_stats["Full_Date"].dt.date.isin([today, today - timedelta(days=1)])]
    elif zeitraum == "Dieser Monat":
        df_stats = df_stats[df_stats["Full_Date"].dt.month == today.month]

    t1, t2 = st.tabs(["Performance", "Verlauf"])
    
    with t1:
        # Plotly Chart ohne Grid, sehr clean
        df_p = df_stats[~df_stats["Aktion"].str.contains("Bank", case=False)]
        if not df_p.empty:
            data = df_p.groupby("Name")["Netto"].sum().mul(-1).reset_index(name="Profit").sort_values("Profit", ascending=False)
            data["Color"] = data["Profit"].apply(lambda x: '#10B981' if x >= 0 else '#EF4444') # Emerald vs Red
            
            fig = px.bar(data, x="Name", y="Profit", text="Profit")
            fig.update_traces(marker_color=data["Color"], texttemplate='%{text:+.0f}', textposition='outside')
            fig.update_layout(
                template="plotly_white",
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                yaxis_title=None,
                xaxis_title=None,
                yaxis=dict(showgrid=True, gridcolor='#F1F5F9'),
                margin=dict(t=20, l=0, r=0, b=0),
                height=350
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Keine Daten im gewählten Zeitraum.")
            
    with t2:
        if not df_stats.empty:
            df_hist = df_stats.sort_values("Full_Date")
            df_hist["Bankverlauf"] = df_hist["Netto"].cumsum()
            
            fig_l = px.area(df_hist, x="Full_Date", y="Bankverlauf")
            fig_l.update_traces(line_color='#0F172A', fill_color='rgba(15, 23, 42, 0.1)')
            fig_l.update_layout(
                template="plotly_white",
                plot_bgcolor='rgba(0,0,0,0)',
                yaxis=dict(showgrid=True, gridcolor='#F1F5F9'),
                margin=dict(t=20, l=0, r=0, b=0),
                height=350
            )
            st.plotly_chart(fig_l, use_container_width=True)

# --- PAGE 4: ABRECHNUNG ---
elif page == "Abrechnung":
    st.markdown("### 🏁 Kassensturz")
    
    # Secrets Handling
    secrets_iban = st.secrets.get("bank", {}).get("iban", "")
    secrets_owner = st.secrets.get("bank", {}).get("owner", "Blackjack Kasse")
    
    if not secrets_iban:
        st.warning("⚠️ Keine IBAN konfiguriert.")
        secrets_iban = st.text_input("IBAN für QR Code:")

    # Logik für Session
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    df_sess = df[df["Full_Date"].dt.date.isin([today, yesterday]) & df["Name"].isin(VALID_PLAYERS)]
    
    if df_sess.empty:
        st.info("Keine aktive Session gefunden.")
    else:
        bilanz = df_sess.groupby("Name")["Netto"].sum()
        # Wer im Plus ist beim "Netto" hat der Bank Geld gegeben -> Bank hat Geld -> Spieler hat verloren
        # Wer im Minus ist beim "Netto" hat Geld genommen -> Bank hat weniger -> Spieler hat gewonnen
        # Wait, Logik Check:
        # Einzahlung: +100 (Netto +100 in Bank). Bank hat 100.
        # Auszahlung: -50 (Netto -50 in Bank). Bank hat 50.
        # Spieler hat 100 gezahlt, 50 bekommen. Spieler hat 50 verloren.
        # Also: Positive Summe = Spieler Verlust (Muss zahlen, falls er noch nicht gezahlt hat? Nein.)
        
        # STOP: Blackjack Logik ist anders.
        # Am Ende des Abends zählt man Chips.
        # Differenz = Ergebnis.
        # Wenn wir "Einzahlung" buchen, hat der Spieler das Geld schon physisch gegeben?
        # Annahme: Ja, Einzahlung = Cash in die Kasse.
        # Dann muss am Ende niemand etwas überweisen, außer die Kasse ist leer.
        
        # VARIANTE "SCHULDENBUCH":
        # Wenn "Einzahlung" heißt: "Ich kaufe Chips auf Pump", dann muss man am Ende zahlen.
        # Wir nehmen an: Einzahlung = Schulden bei der Bank. Auszahlung = Schulden tilgen / Gewinn.
        
        # Wir schauen nur auf Netto.
        # Netto > 0: Spieler hat mehr Chips geholt als zurückgegeben -> Er schuldet der Bank Geld.
        schuldner = bilanz[bilanz > 0]

        if schuldner.empty:
            st.success("✅ Niemand hat Schulden aus dieser Session!")
        else:
            st.markdown("Folgende Spieler haben Chips gekauft aber weniger zurückgegeben (Verlust):")
            
            # Schöne Cards für Schuldner
            for player, amount in schuldner.items():
                with st.expander(f"💳 **{player}**: {amount:.2f} € offen", expanded=True):
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        qr = generate_epc_qr_url(secrets_owner, secrets_iban, amount, f"BJ {player}")
                        st.image(qr, width=200)
                    with c2:
                        st.markdown(f"""
                        **Empfänger:** {secrets_owner}<br>
                        **IBAN:** {secrets_iban}<br>
                        **Betrag:** <span style="color:#EF4444; font-weight:bold;">{amount:.2f} €</span><br>
                        **Verwendungszweck:** BJ {player}
                        """, unsafe_allow_html=True)
