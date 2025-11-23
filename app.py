import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import pytz

# --- KONFIGURATION ---
st.set_page_config(page_title="Blackjack Bank", page_icon="♠️", layout="centered")

# --- CSS HACK für Mobile Optimierung & Weißes Design erzwingen ---
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stApp {
                background-color: white;
            }
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- TITEL ---
st.title("♠️ Blackjack Bank")

# --- VERBINDUNG ZU GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

# Cache leeren Button (falls Daten klemmen)
if st.button("🔄 Daten aktualisieren (Sync)"):
    st.cache_data.clear()
    st.rerun()

# --- DATEN LADEN ---
# Wir lesen das Arbeitsblatt "Buchungen" (muss existieren, sonst wird es erstellt)
try:
    df = conn.read(worksheet="Buchungen", usecols=list(range(6)), ttl=5)
    df = df.dropna(how="all")
except:
    # Falls Tabelle leer oder neu, erstelle leeren DataFrame
    df = pd.DataFrame(columns=["Datum", "Name", "Aktion", "Betrag", "Notiz", "Zeitstempel"])

# --- LEADERBOARD BERECHNEN ---
# Wir berechnen den Kontostand live aus der Historie
if not df.empty:
    # Zahlen sicherstellen
    df["Betrag"] = pd.to_numeric(df["Betrag"], errors="coerce").fillna(0)
    
    # Gesamtsaldo der Bank
    bank_saldo = df["Betrag"].sum()
    
    # Spieler Salden (Nur Einzahlungen und Auszahlungen der Spieler betrachten)
    # Wir filtern Roulette und Ausgaben raus für das Leaderboard
    spieler_df = df[~df["Aktion"].isin(["Bank Einnahme (Roulette/Sonstiges)", "Bank Ausgabe (Ausgaben)"])]
    
    # Gruppieren nach Spieler
    leaderboard = spieler_df.groupby("Name")["Betrag"].sum().reset_index()
    leaderboard.columns = ["Spieler", "Investiert"]
    leaderboard = leaderboard.sort_values(by="Investiert", ascending=False)
else:
    bank_saldo = 0.0
    leaderboard = pd.DataFrame(columns=["Spieler", "Investiert"])

# --- ANZEIGE BANKBESTAND ---
st.markdown(f"<h1 style='text-align: center; font-size: 80px; color: black;'>{bank_saldo:,.2f} €</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>Aktueller Bankbestand</p>", unsafe_allow_html=True)

st.divider()

# --- STATS (DIAGRAMM) ---
st.subheader("📊 Einnahmen Übersicht")

if not leaderboard.empty:
    # Diagramm Design für hellen Hintergrund optimieren
    fig = px.bar(leaderboard, x="Investiert", y="Spieler", orientation='h', text="Investiert")
    fig.update_traces(texttemplate='%{text:.2f} €', textposition='outside')
    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color="black"),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=False)
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Noch keine Daten für das Diagramm.")

# --- NEUE BUCHUNG ---
with st.expander("➕ Neue Buchung hinzufügen", expanded=True):
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Dropdown mit bekannten Namen + Option für neue
        bekannte_namen = ["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi"]
        name_input = st.selectbox("Name / Kategorie", options=bekannte_namen + ["Roulette (Rot)", "Mischmaschine", "Sonstiges"])
        
    with col2:
        betrag_input = st.number_input("Betrag €", min_value=0.00, value=10.00, step=5.00, format="%.2f")

    aktion = st.radio("Aktion", [
        "Einzahlung (Spieler kauft Chips) [+]", 
        "Auszahlung (Spieler tauscht zurück) [-]",
        "Bank Einnahme (Roulette/Sonstiges) [+]",
        "Bank Ausgabe (Ausgaben) [-]"
    ])

    if st.button("Buchen ✅", type="primary", use_container_width=True):
        
        # Vorzeichen logik
        final_betrag = betrag_input
        if "[-]" in aktion:
            final_betrag = -betrag_input
            
        # Zeitstempel (Deutschland)
        tz = pytz.timezone('Europe/Berlin')
        now = datetime.now(tz)
        datum_str = now.strftime("%d.%m.%Y")
        zeit_str = now.strftime("%H:%M:%S")
        
        # Neuer Eintrag als DataFrame
        neuer_eintrag = pd.DataFrame([{
            "Datum": datum_str,
            "Name": name_input,
            "Aktion": aktion.split(" (")[0], # Nur der kurze Text
            "Betrag": final_betrag,
            "Notiz": aktion,
            "Zeitstempel": zeit_str
        }])
        
        # Hinzufügen zu den bestehenden Daten
        updated_df = pd.concat([df, neuer_eintrag], ignore_index=True)
        
        # In Google Sheets speichern
        conn.update(worksheet="Buchungen", data=updated_df)
        
        st.success("Gebucht!")
        st.cache_data.clear()
        st.rerun()

st.divider()

# --- HISTORIE TABELLE ---
st.subheader("📜 Letzte Buchungen")
if not df.empty:
    # Zeige die neuesten zuerst
    display_df = df.sort_index(ascending=False).copy()
    
    # Schönere Formatierung für die Anzeige
    st.dataframe(
        display_df[["Datum", "Name", "Betrag", "Aktion"]], 
        use_container_width=True,
        hide_index=True
    )
