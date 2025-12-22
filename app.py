import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import pytz
import requests
import urllib.parse

# --- KONFIGURATION & KONSTANTEN ---
st.set_page_config(page_title="Blackjack Bank", page_icon="♠️", layout="centered")

# Liste der festen Spieler
VALID_PLAYERS = sorted(["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi"])

# --- CSS STYLING (CLEAN UI) ---
custom_css = """
<style>
    /* Globales Styling */
    .stApp {
        background-color: #F8F9FA;
    }
    
    /* Karten-Design für Container */
    div[data-testid="stVerticalBlock"] > div[style*="background-color"] {
        background-color: #FFFFFF;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        border: 1px solid #E9ECEF;
    }
    
    /* Metriken (KPIs) */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #E9ECEF;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }

    /* Der große Kontostand */
    .big-balance-container {
        text-align: center;
        padding: 20px 0;
        margin-bottom: 20px;
    }
    .big-balance-label {
        font-size: 14px;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        color: #6B7280;
        font-weight: 600;
    }
    .big-balance-val {
        font-size: 64px;
        font-weight: 800;
        color: #111827;
        line-height: 1.1;
        font-feature-settings: "tnum";
        font-variant-numeric: tabular-nums;
    }
    .big-balance-neg { color: #DC2626; }
    
    /* Buttons */
    button[kind="primary"] {
        height: 50px;
        font-size: 18px !important;
        font-weight: 600;
        border-radius: 10px;
    }

    /* Hide Streamlit Branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# --- HELPER FUNKTIONEN ---

def generate_epc_qr_url(name, iban, amount, purpose):
    """Generiert einen GiroCode (EPC-QR) Link."""
    iban_clean = iban.replace(" ", "").upper()
    amount_str = f"EUR{amount:.2f}"
    epc_data = f"""BCD
002
1
SCT

{name}
{iban_clean}
{amount_str}


{purpose}
"""
    data_encoded = urllib.parse.quote(epc_data)
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={data_encoded}"

def berechne_netto(row):
    """Berechnet den Netto-Einfluss auf die Bank."""
    betrag = row["Betrag"]
    aktion = str(row["Aktion"]).lower()
    if ("ausgabe" in aktion or "auszahlung" in aktion) and betrag > 0:
        return -betrag
    return betrag

def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(worksheet="Buchungen", ttl=0)
        rename_map = {"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"}
        df = df.rename(columns=rename_map)
        # Ensure numeric
        if not df.empty:
            df["Betrag"] = df["Betrag"].astype(str).str.replace(',', '.', regex=False)
            df["Betrag"] = pd.to_numeric(df["Betrag"], errors='coerce').fillna(0)
            
            df['Full_Date'] = pd.to_datetime(df['Datum'] + ' ' + df['Zeitstempel'].fillna('00:00'), format='%d.%m.%Y %H:%M', errors='coerce')
            df['Full_Date'] = df['Full_Date'].fillna(pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce'))
            
            df["Netto"] = df.apply(berechne_netto, axis=1)
            df = df.sort_values(by="Full_Date", ascending=False).reset_index(drop=True)
        return df, conn
    except Exception:
        return pd.DataFrame(columns=["Datum", "Zeitstempel", "Name", "Aktion", "Betrag", "Netto", "Full_Date"]), conn

# --- DATA LOADING ---
df, conn = load_data()
if not df.empty:
    kontostand = df["Netto"].sum()
else:
    kontostand = 0.0

# --- NAVIGATION ---
st.sidebar.title("♠️ Menu")
page = st.sidebar.radio("Gehe zu:", ["🏠 Übersicht", "➕ Neue Buchung", "📊 Statistik & Profile", "💸 Abrechnung"], label_visibility="collapsed")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Daten aktualisieren", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# --- HEADER (IMMER SICHTBAR) ---
# Zeigt den Kontostand immer oben an, egal auf welcher Seite
css_class = "big-balance-val" if kontostand >= 0 else "big-balance-val big-balance-neg"
balance_fmt = f"{kontostand:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

if page == "🏠 Übersicht":
    st.markdown(f"""
    <div class="big-balance-container">
        <div class="big-balance-label">Bank Kontostand</div>
        <div class="{css_class}">{balance_fmt} €</div>
    </div>
    """, unsafe_allow_html=True)

# --- PAGE: ÜBERSICHT (DASHBOARD) ---
if page == "🏠 Übersicht":
    
    if df.empty:
        st.info("Noch keine Daten vorhanden. Starte mit einer Buchung!")
    else:
        # 1. Quick Stats (Heute)
        today = datetime.now().date()
        df_today = df[df["Full_Date"].dt.date == today]
        
        col1, col2 = st.columns(2)
        chips_in_today = df_today[df_today["Aktion"].str.contains("Einzahlung", na=False)]["Betrag"].sum()
        chips_out_today = df_today[df_today["Aktion"].str.contains("Auszahlung", na=False)]["Betrag"].sum()
        
        with col1:
            st.metric("Chips Verkauf (Heute)", f"{chips_in_today:,.0f} €")
        with col2:
            st.metric("Chips Rücknahme (Heute)", f"{chips_out_today:,.0f} €")

        st.markdown("### 🔥 Top 3 (Gesamt)")
        # Simple Leaderboard
        df_players = df[~df["Aktion"].str.contains("Bank", case=False)]
        if not df_players.empty:
            lb = df_players.groupby("Name")["Netto"].sum().mul(-1).reset_index(name="Profit").sort_values("Profit", ascending=False).head(3)
            lb["Color"] = lb["Profit"].apply(lambda x: '#059669' if x >= 0 else '#DC2626')
            
            fig = px.bar(lb, x="Profit", y="Name", orientation='h', text="Profit")
            fig.update_traces(marker_color=lb["Color"], texttemplate='%{text:+.2f} €', textposition='inside')
            fig.update_layout(
                template="plotly_white",
                margin=dict(l=0, r=0, t=0, b=0),
                xaxis=dict(showgrid=False, showticklabels=False),
                yaxis=dict(title=None),
                height=150
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        
        st.markdown("### 🕒 Letzte Aktivitäten")
        st.dataframe(
            df[["Datum", "Name", "Aktion", "Betrag"]].head(5),
            use_container_width=True,
            hide_index=True
        )

# --- PAGE: BUCHUNG ---
elif page == "➕ Neue Buchung":
    st.markdown("## 💸 Neue Transaktion")
    
    with st.container(border=True):
        # Name
        buchung_namen = VALID_PLAYERS + ["Manuelle Ausgabe 📝"]
        auswahl_name = st.pills("Wer?", buchung_namen, selection_mode="single")
        
        # Falls nichts gewählt ist, default
        if not auswahl_name:
            auswahl_name = VALID_PLAYERS[0]
            
        final_name = auswahl_name
        if auswahl_name == "Manuelle Ausgabe 📝":
            final_name = st.text_input("Zweck eingeben", placeholder="z.B. Pizza")

        st.write("") 
        
        # Betrag (Groß und deutlich)
        c_betrag, c_aktion = st.columns([1, 1])
        with c_betrag:
            betrag_input = st.number_input("Betrag (€)", min_value=0.0, value=10.0, step=5.0, format="%.2f")
        
        with c_aktion:
            # Vereinfachte Auswahl
            aktion_map = {
                "Einzahlung (+)": "Einzahlung",
                "Auszahlung (-)": "Auszahlung",
                "Bank Einnahme (+)": "Bank Einnahme",
                "Bank Ausgabe (-)": "Bank Ausgabe"
            }
            aktion_label = st.radio("Was passiert?", list(aktion_map.keys()), index=0)
            typ_short = aktion_map[aktion_label]

        st.write("---")
        
        # Submit Logic
        if st.button(f"✅ Buchen: {final_name} | {betrag_input:.2f} €", type="primary", use_container_width=True):
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
                    # Reload raw data to append correctly
                    df_raw = conn.read(worksheet="Buchungen", ttl=0)
                    updated_df = pd.concat([df_raw, neuer_eintrag], ignore_index=True)
                    conn.update(worksheet="Buchungen", data=updated_df)
                    
                    # Ntfy (Silent fail if it doesn't work)
                    if "Bank" in typ_short:
                        try:
                            ntfy_topic = "bj-boys-dashboard"
                            if "Einnahme" in typ_short:
                                title, tags, msg = "🤑 Bank Einnahme", "moneybag,up", f"Plus: {betrag_input:.2f} €\nGrund: {final_name}"
                            else:
                                title, tags, msg = "💸 Bank Ausgabe", "chart_with_downwards_trend,down", f"Minus: {betrag_input:.2f} €\nZweck: {final_name}"
                            requests.post(f"https://ntfy.sh/{ntfy_topic}", data=msg.encode('utf-8'), headers={"Title": title.encode('utf-8'), "Tags": tags})
                        except: pass

                    st.toast(f"Gebucht!", icon="✅")
                    st.cache_data.clear()
                    
                    # Kleines Feedback UI statt Rerun-Loop
                    st.success(f"Erfolgreich: {final_name} {aktion_label} {betrag_input}€")
                    
                except Exception as e:
                    st.error(f"Fehler: {e}")
            else:
                st.warning("Bitte Namen wählen.")

# --- PAGE: STATISTIK ---
elif page == "📊 Statistik & Profile":
    st.markdown("## 📊 Analyse")
    
    # Filter sauber oben
    col_filter, col_toggle = st.columns([3, 1])
    with col_filter:
        zeitraum = st.selectbox("Zeitraum", ["Alle Zeiten", "Aktuelle Session (Heute/Gestern)", "Dieser Monat"], index=0)
    
    # Filter Logik
    df_stats = df.copy()
    today = datetime.now().date()
    
    if zeitraum == "Aktuelle Session (Heute/Gestern)":
        yesterday = today - timedelta(days=1)
        df_stats = df_stats[df_stats["Full_Date"].dt.date.isin([today, yesterday])]
    elif zeitraum == "Dieser Monat":
        df_stats = df_stats[(df_stats["Full_Date"].dt.month == today.month) & (df_stats["Full_Date"].dt.year == today.year)]

    tab1, tab2, tab3 = st.tabs(["🏆 Rangliste", "📈 Verlauf", "👤 Spieler-Profil"])

    with tab1:
        df_players_only = df_stats[~df_stats["Aktion"].str.contains("Bank", case=False)].copy()
        if not df_players_only.empty:
            lb = df_players_only.groupby("Name")["Netto"].sum().mul(-1).reset_index(name="Profit").sort_values("Profit", ascending=False)
            lb["Color"] = lb["Profit"].apply(lambda x: '#059669' if x >= 0 else '#DC2626')
            
            fig = px.bar(lb, x="Profit", y="Name", orientation='h', text="Profit")
            fig.update_traces(marker_color=lb["Color"], texttemplate='%{text:+.2f} €', textposition='outside')
            fig.update_layout(height=400, template="plotly_white", xaxis_title="Gewinn (€)", yaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Keine Daten für diesen Zeitraum.")

    with tab2:
        if not df_stats.empty:
            df_hist = df_stats.sort_values(by="Full_Date", ascending=True).copy()
            df_hist["Bankverlauf"] = df_hist["Netto"].cumsum()
            
            fig_line = px.line(df_hist, x="Full_Date", y="Bankverlauf", markers=True)
            fig_line.update_traces(line_color='#111827', line_width=2)
            fig_line.update_layout(template="plotly_white", yaxis_title="Bank (€)", xaxis_title=None)
            st.plotly_chart(fig_line, use_container_width=True)

    with tab3:
        sel_player = st.selectbox("Spieler wählen", VALID_PLAYERS)
        df_p = df[df["Name"] == sel_player].copy()
        
        if df_p.empty:
            st.warning("Keine Daten.")
        else:
            df_p["Profit"] = -df_p["Netto"]
            lifetime = df_p["Profit"].sum()
            
            # Badges
            badges = ""
            if lifetime > 100: badges = "👑"
            elif lifetime < -100: badges = "💸"
            
            st.metric(f"Gesamt Profit {badges}", f"{lifetime:+.2f} €", delta=lifetime)
            
            # Session History
            df_p["Date"] = df_p["Full_Date"].dt.date
            daily = df_p.groupby("Date")["Profit"].sum().reset_index()
            daily["Color"] = daily["Profit"].apply(lambda x: '#059669' if x >= 0 else '#DC2626')
            
            fig_p = px.bar(daily, x="Date", y="Profit")
            fig_p.update_traces(marker_color=daily["Color"])
            fig_p.update_layout(template="plotly_white", height=300)
            st.plotly_chart(fig_p, use_container_width=True)

# --- PAGE: ABRECHNUNG ---
elif page == "💸 Abrechnung":
    st.markdown("## 💸 Schulden begleichen")
    st.info("Hier sehen wir, wer aus der **aktuellen Session (Heute & Gestern)** noch im Minus ist und zahlen muss.")
    
    # Config laden
    secrets_iban = st.secrets.get("bank", {}).get("iban", "")
    secrets_owner = st.secrets.get("bank", {}).get("owner", "Blackjack Kasse")
    
    if not secrets_iban:
        st.warning("Keine IBAN in secrets.toml gefunden.")
        secrets_iban = st.text_input("IBAN manuell eingeben")

    # Logik: Nur Session Verlierer
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    mask_date = df["Full_Date"].dt.date.isin([today, yesterday])
    mask_player = df["Name"].isin(VALID_PLAYERS)
    
    df_sess = df[mask_date & mask_player].copy()
    
    if df_sess.empty:
        st.success("Keine offenen Sessions gefunden.")
    else:
        # Spielerbilanz (Negatives Netto = Spieler hat Gewinn, Positives Netto = Bank hat Gewinn)
        # Wir brauchen: Wer hat VERLOREN? -> Wer hat mehr Chips gekauft als zurückgegeben.
        # Netto in DB: Einzahlung = +Betrag. Auszahlung = -Betrag.
        # Summe Netto > 0 heißt: Spieler hat mehr eingezahlt als rausgeholt -> Spieler hat VERLOREN.
        
        bilanz = df_sess.groupby("Name")["Netto"].sum()
        verlierer = bilanz[bilanz > 0] # Netto positiv = Geld in der Bank gelassen

        if verlierer.empty:
            st.canvas_confetti()
            st.success("Die Bank wurde geschlagen! Niemand muss einzahlen.")
        else:
            col_qr, col_list = st.columns([1, 1])
            
            with col_list:
                st.markdown("### 📉 Wer muss blechen?")
                radio_options = {f"{k} ({v:.2f} €)": (k, v) for k, v in verlierer.items()}
                selection = st.radio("Wähle Zahler:", options=radio_options.keys())
            
            if selection and secrets_iban:
                name, amount = radio_options[selection]
                qr_link = generate_epc_qr_url(secrets_owner, secrets_iban, amount, f"BJ {name}")
                
                with col_qr:
                    st.image(qr_link, caption=f"Scan für {name}", width=300)
