import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
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
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- TITEL ---
st.title("♠️ Blackjack Bank")

# --- VERBINDUNG ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- DATEN LADEN & VORBEREITEN ---
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
    # 1. Betrag säubern
    df["Betrag"] = df["Betrag"].astype(str).str.replace(',', '.', regex=False)
    df["Betrag"] = pd.to_numeric(df["Betrag"], errors='coerce').fillna(0)
    
    # 2. Datum für Sortierung und Filterung nutzbar machen
    # Wir erstellen eine echte Datetime-Spalte aus Datum + Zeitstempel
    df['Full_Date'] = pd.to_datetime(df['Datum'] + ' ' + df['Zeitstempel'].fillna('00:00'), format='%d.%m.%Y %H:%M', errors='coerce')
    # Falls das parsen fehlschlägt (alte Daten), fallback auf nur Datum
    df['Full_Date'] = df['Full_Date'].fillna(pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce'))

# --- LOGIK: KONTOSTAND (NETTO) ---
def berechne_netto(row):
    betrag = row["Betrag"]
    aktion = str(row["Aktion"]).lower()
    # Ausgaben und Auszahlungen verringern den Bankbestand
    if ("ausgabe" in aktion or "auszahlung" in aktion) and betrag > 0:
        return -betrag
    return betrag

if not df.empty:
    df["Netto"] = df.apply(berechne_netto, axis=1)
    # Sortieren nach Zeit für korrekten Verlauf
    df = df.sort_values(by="Full_Date", ascending=True).reset_index(drop=True)
    df["Bankverlauf"] = df["Netto"].cumsum() # Laufender Kontostand
    kontostand = df["Netto"].sum()
else:
    kontostand = 0.0

# --- ANZEIGE HAUPTSEITE ---
color = "black" if kontostand >= 0 else "red"
st.markdown(f"<h1 style='text-align: center; font-size: 80px; color: {color};'>{kontostand:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".") + "</h1>", unsafe_allow_html=True)

col_btn1, col_btn2 = st.columns([1, 4]) 
# Kleiner Refresh Button Hack für Layout
if st.button("🔄", help="Daten aktualisieren", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.divider()

# --- BUCHUNG FORMULAR ---
with st.expander("➕ Neue Buchung erstellen", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        namen_liste = ["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi", "Manuelle Ausgabe 📝"]
        auswahl_name = st.selectbox("Name / Typ", namen_liste)
        final_name = auswahl_name
        if auswahl_name == "Manuelle Ausgabe 📝":
            custom_input = st.text_input("Zweck / Name", placeholder="z.B. Pizza")
            if custom_input: final_name = custom_input

    with col2:
        betrag_input = st.number_input("Betrag €", min_value=0.00, value=10.00, step=5.00, format="%.2f")

    aktion_auswahl = st.radio("Art der Buchung", [
        "Einzahlung (Spieler kauft Chips) [+]", 
        "Auszahlung (Spieler tauscht zurück) [-]",
        "Bank Einnahme (Roulette/Sonstiges) [+]",
        "Bank Ausgabe (Ausgaben) [-]"
    ])

    if st.button("Buchen ✅", type="primary", use_container_width=True):
        typ_short = aktion_auswahl.split(" (")[0]
        tz = pytz.timezone('Europe/Berlin')
        now = datetime.now(tz)
        
        # Google Sheets Update
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
            
            # Ntfy Senden (Nur bei Bank Aktionen)
            if "Bank" in typ_short:
                try:
                    ntfy_topic = "bj-boys-dashboard"
                    if "Einnahme" in typ_short:
                        title, tags, msg = "🤑 Bank Einnahme", "moneybag,up", f"Plus: {betrag_input:.2f} €\nGrund: {final_name}"
                    else:
                        title, tags, msg = "💸 Bank Ausgabe", "chart_with_downwards_trend,down", f"Minus: {betrag_input:.2f} €\nZweck: {final_name}"
                    
                    requests.post(f"https://ntfy.sh/{ntfy_topic}", data=msg.encode('utf-8'), headers={"Title": title.encode('utf-8'), "Tags": tags})
                    st.toast("Benachrichtigung gesendet!", icon="✅")
                except Exception:
                    pass # Silent fail für Ntfy

            st.success(f"Gebucht: {final_name} ({betrag_input}€)")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Fehler beim Speichern: {e}")

st.divider()

# --- ERWEITERTE STATISTIKEN ---
st.subheader("📊 Analyse & Statistiken")

if not df.empty:
    # 1. FILTER-LOGIK
    filter_col1, filter_col2 = st.columns([2, 1])
    with filter_col1:
        zeitraum = st.pills("Zeitraum", ["Gesamt", "Heute", "Dieser Monat"], default="Gesamt")
    
    # Filter anwenden
    df_stats = df.copy()
    today = datetime.now().date()
    
    if zeitraum == "Heute":
        df_stats = df_stats[df_stats["Full_Date"].dt.date == today]
    elif zeitraum == "Dieser Monat":
        df_stats = df_stats[(df_stats["Full_Date"].dt.month == today.month) & (df_stats["Full_Date"].dt.year == today.year)]

    if df_stats.empty:
        st.warning(f"Keine Daten für Zeitraum '{zeitraum}' gefunden.")
    else:
        # KPIs anzeigen
        kpi1, kpi2, kpi3 = st.columns(3)
        volumen = df_stats["Betrag"].sum()
        anzahl_tx = len(df_stats)
        delta_bank = df_stats["Netto"].sum()
        
        kpi1.metric("Anzahl Buchungen", f"{anzahl_tx}")
        kpi2.metric("Bewegtes Volumen", f"{volumen:,.0f} €")
        kpi3.metric("Bank Gewinn/Verlust", f"{delta_bank:,.2f} €", delta_color="normal")

        # TABS FÜR DIAGRAMME
        tab_bilanz, tab_verlauf, tab_details = st.tabs(["🏆 Spieler-Bilanz", "📈 Bank-Verlauf", "📝 Buchungsliste"])

        # --- TAB 1: SPIELER BILANZ (Gewinn vs Verlust) ---
        with tab_bilanz:
            # Wir filtern nur Spieler-Aktionen (keine reinen Bank-Ausgaben/Einnahmen)
            df_player = df_stats[~df_stats["Name"].isin(["Manuelle Ausgabe 📝", "Sonstiges"]) & 
                                 ~df_stats["Aktion"].str.contains("Bank", case=False)].copy()
            
            if not df_player.empty:
                # Logik: 
                # Einzahlung = Spieler investiert (Minus für Spieler-Bilanz, Plus für Bank) -> Hier zählen wir es als Investition
                # Auszahlung = Spieler bekommt raus
                # Profit = Summe(Auszahlung) - Summe(Einzahlung)
                
                def calc_player_profit(x):
                    einzahlungen = x[x["Aktion"].str.contains("Einzahlung")]["Betrag"].sum()
                    auszahlungen = x[x["Aktion"].str.contains("Auszahlung")]["Betrag"].sum()
                    return auszahlungen - einzahlungen

                leaderboard = df_player.groupby("Name").apply(calc_player_profit).reset_index(name="Profit")
                leaderboard = leaderboard.sort_values("Profit", ascending=False)
                
                # Farben: Grün für Profit, Rot für Verlust
                leaderboard["Color"] = leaderboard["Profit"].apply(lambda x: '#2E7D32' if x >= 0 else '#C62828')

                fig_bal = px.bar(leaderboard, x="Profit", y="Name", orientation='h', text="Profit", title=f"Spieler Gewinne ({zeitraum})")
                fig_bal.update_traces(marker_color=leaderboard["Color"], texttemplate='%{text:+.2f} €', textposition='outside')
                fig_bal.update_layout(paper_bgcolor='white', plot_bgcolor='white', font_color='black', xaxis_title="Gewinn (+) / Verlust (-)")
                st.plotly_chart(fig_bal, use_container_width=True)
            else:
                st.info("Keine Spieler-Daten in diesem Zeitraum.")

        # --- TAB 2: BANK VERLAUF ---
        with tab_verlauf:
            # Liniendiagramm über die Zeit
            if len(df_stats) > 1:
                fig_line = px.line(df_stats, x="Full_Date", y="Bankverlauf", markers=True, title="Entwicklung Bankbestand")
                fig_line.update_layout(paper_bgcolor='white', plot_bgcolor='white', font_color='black', yaxis_title="Kontostand in €")
                fig_line.update_traces(line_color='black', line_width=3)
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.info("Zu wenige Daten für eine Verlaufskurve.")

        # --- TAB 3: LISTE ---
        with tab_details:
            display_df = df_stats[["Datum", "Zeitstempel", "Name", "Aktion", "Betrag"]].sort_index(ascending=False).copy()
            def highlight_rows(row):
                if "aus" in str(row["Aktion"]).lower():
                    return ['color: #D32F2F'] * len(row)
                return ['color: black'] * len(row)
            
            st.dataframe(
                display_df.style.apply(highlight_rows, axis=1)
                .format({"Betrag": lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")}), 
                use_container_width=True, hide_index=True
            )

else:
    st.info("Noch keine Daten vorhanden.")
