import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import pytz
import requests

# --- KONFIGURATION ---
st.set_page_config(page_title="Blackjack Bank", page_icon="♠️", layout="centered")

# --- CSS STYLING ---
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stApp { background-color: white; }
            div[data-testid="stDataFrame"] { font-family: monospace; }
            div[data-testid="stMetricValue"] { font-size: 24px; }
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- TITEL ---
st.title("♠️ Blackjack Bank")

# --- VERBINDUNG ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- DATEN LADEN ---
try:
    df = conn.read(worksheet="Buchungen", ttl=0)
    rename_map = {"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"}
    df = df.rename(columns=rename_map)
    
    expected_cols = ["Datum", "Name", "Aktion", "Betrag", "Zeitstempel"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None
except Exception:
    df = pd.DataFrame(columns=["Datum", "Zeitstempel", "Name", "Aktion", "Betrag"])

if not df.empty:
    # Bereinigung
    df["Betrag"] = df["Betrag"].astype(str).str.replace(',', '.', regex=False)
    df["Betrag"] = pd.to_numeric(df["Betrag"], errors='coerce').fillna(0)
    
    # Datum parsen
    df['Full_Date'] = pd.to_datetime(df['Datum'] + ' ' + df['Zeitstempel'].fillna('00:00'), format='%d.%m.%Y %H:%M', errors='coerce')
    df['Full_Date'] = df['Full_Date'].fillna(pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce'))

# --- LOGIK: NETTO BERECHNUNG ---
def berechne_netto(row):
    betrag = row["Betrag"]
    aktion = str(row["Aktion"]).lower()
    if ("ausgabe" in aktion or "auszahlung" in aktion) and betrag > 0:
        return -betrag
    return betrag

if not df.empty:
    df["Netto"] = df.apply(berechne_netto, axis=1)
    # Sortieren für korrekten Verlauf später
    df = df.sort_values(by="Full_Date", ascending=True).reset_index(drop=True)
    kontostand = df["Netto"].sum()
else:
    kontostand = 0.0

# --- HEADER (KONTOSTAND) ---
color = "black" if kontostand >= 0 else "red"
st.markdown(f"<h1 style='text-align: center; font-size: 80px; color: {color};'>{kontostand:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".") + "</h1>", unsafe_allow_html=True)

col_btn1, col_btn2 = st.columns([1, 4]) 
if st.button("🔄", help="Aktualisieren", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.divider()

# --- BUCHEN ---
with st.expander("➕ Neue Buchung", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        namen_liste = ["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi", "Manuelle Ausgabe 📝"]
        auswahl_name = st.selectbox("Name", namen_liste)
        final_name = auswahl_name
        if auswahl_name == "Manuelle Ausgabe 📝":
            custom_input = st.text_input("Zweck", placeholder="Pizza / Bier")
            if custom_input: final_name = custom_input

    with col2:
        betrag_input = st.number_input("Betrag €", min_value=0.00, value=10.00, step=5.00, format="%.2f")

    aktion_auswahl = st.radio("Typ", [
        "Einzahlung (Spieler kauft Chips) [+]", 
        "Auszahlung (Spieler tauscht zurück) [-]",
        "Bank Einnahme (Roulette/Sonstiges) [+]",
        "Bank Ausgabe (Ausgaben) [-]"
    ])

    if st.button("Buchen ✅", type="primary", use_container_width=True):
        typ_short = aktion_auswahl.split(" (")[0]
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
            
            # Ntfy Logik
            if "Bank" in typ_short:
                try:
                    ntfy_topic = "bj-boys-dashboard"
                    if "Einnahme" in typ_short:
                        title, tags, msg = "🤑 Bank Einnahme", "moneybag,up", f"Plus: {betrag_input:.2f} €\nGrund: {final_name}"
                    else:
                        title, tags, msg = "💸 Bank Ausgabe", "chart_with_downwards_trend,down", f"Minus: {betrag_input:.2f} €\nZweck: {final_name}"
                    requests.post(f"https://ntfy.sh/{ntfy_topic}", data=msg.encode('utf-8'), headers={"Title": title.encode('utf-8'), "Tags": tags})
                    st.toast("Ntfy gesendet!", icon="✅")
                except: pass

            st.success(f"Gebucht: {final_name}")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Fehler: {e}")

st.divider()

# --- ANALYSE ---
st.subheader("📊 Statistik")

if not df.empty:
    # --- FILTER BEREICH ---
    filter_col1, filter_col2 = st.columns([2.5, 1])
    
    with filter_col1:
        zeitraum = st.pills("Zeitraum", ["Aktuelle Session", "Gesamt", "Dieser Monat"], default="Aktuelle Session")
    
    with filter_col2:
        st.write("") # Kleiner Abstandshalter nach unten
        st.write("") 
        hide_bank = st.checkbox("Bank-Buchungen ausblenden", value=False)
    
    df_stats = df.copy()
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    # 1. Datum Filter
    if zeitraum == "Aktuelle Session":
        df_stats = df_stats[df_stats["Full_Date"].dt.date.isin([today, yesterday])]
    elif zeitraum == "Dieser Monat":
        df_stats = df_stats[(df_stats["Full_Date"].dt.month == today.month) & (df_stats["Full_Date"].dt.year == today.year)]

    # 2. Bank Filter (Die Checkbox Logik)
    if hide_bank:
        df_stats = df_stats[~df_stats["Aktion"].str.contains("Bank", case=False, na=False)]

    if df_stats.empty:
        st.info(f"Keine Daten für Filter: '{zeitraum}'.")
    else:
        # Verlauf NEU berechnen basierend auf gefilterten Daten
        df_stats = df_stats.sort_values(by="Full_Date", ascending=True)
        df_stats["Bankverlauf"] = df_stats["Netto"].cumsum()
        
        # KPI BERECHNUNG
        delta_bank = df_stats["Netto"].sum()
        chips_in = df_stats[df_stats["Aktion"].str.contains("Einzahlung", case=False, na=False)]["Betrag"].sum()
        chips_out = df_stats[df_stats["Aktion"].str.contains("Auszahlung", case=False, na=False)]["Betrag"].sum()

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Chips gekauft", f"{chips_in:,.0f} €")
        kpi2.metric("Chips ausgezahlt", f"{chips_out:,.0f} €")
        kpi3.metric("Bank Gewinn/Verlust", f"{delta_bank:,.2f} €", delta_color="normal")

        tab_bilanz, tab_verlauf, tab_list = st.tabs(["🏆 Spieler", "📈 Bank-Verlauf", "📝 Liste"])

        with tab_bilanz:
            # Nur Spieler betrachten (Bank sowieso raus, wenn Checkbox aktiv)
            df_p = df_stats[~df_stats["Aktion"].str.contains("Bank", case=False)].copy()
            if not df_p.empty:
                def get_profit(x):
                    ein = x[x["Aktion"].str.contains("Einzahlung")]["Betrag"].sum()
                    aus = x[x["Aktion"].str.contains("Auszahlung")]["Betrag"].sum()
                    return aus - ein
                
                lb = df_p.groupby("Name").apply(get_profit).reset_index(name="Profit").sort_values("Profit", ascending=False)
                lb["Color"] = lb["Profit"].apply(lambda x: '#2E7D32' if x >= 0 else '#C62828')
                
                fig = px.bar(lb, x="Profit", y="Name", orientation='h', text="Profit", title="Gewinn/Verlust pro Spieler")
                fig.update_traces(marker_color=lb["Color"], texttemplate='%{text:+.2f} €', textposition='outside')
                fig.update_layout(xaxis_title="Gewinn", paper_bgcolor='white', plot_bgcolor='white', font_color='black')
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("Keine Spielerdaten im gewählten Zeitraum.")

        with tab_verlauf:
            if len(df_stats) > 0:
                fig_line = px.line(df_stats, x="Full_Date", y="Bankverlauf", 
                                   title="Entwicklung Bankbestand (Gefiltert)",
                                   line_shape='hv')
                
                fig_line.update_layout(paper_bgcolor='white', plot_bgcolor='white', font_color='black', yaxis_title="Kontostand €")
                fig_line.update_traces(line_color='black', line_width=3)
                st.plotly_chart(fig_line, use_container_width=True)
            else: st.info("Zu wenig Daten.")

        with tab_list:
             st.dataframe(df_stats[["Datum", "Zeitstempel", "Name", "Aktion", "Betrag"]].sort_index(ascending=False), use_container_width=True, hide_index=True)
else:
    st.info("Datenbank leer.")
