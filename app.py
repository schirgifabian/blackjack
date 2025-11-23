import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import pytz

# --- KONFIGURATION ---
st.set_page_config(page_title="Blackjack Bank", page_icon="♠️", layout="centered")

# --- CSS HACK: Weißes Design erzwingen ---
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

# --- VERBINDUNG HERSTELLEN ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- DATEN LADEN ---
try:
    # Versuche, das Blatt "Buchungen" zu laden
    df = conn.read(worksheet="Buchungen", ttl=0)
    # Falls die Tabelle leer ist oder komische Spalten hat, Fehler abfangen
    if df.empty or "Betrag" not in df.columns:
        raise ValueError("Tabelle leer oder falsches Format")
except:
    # Fallback: Leere Tabelle erstellen, falls noch keine existiert
    df = pd.DataFrame(columns=["Datum", "Name", "Aktion", "Betrag", "Notiz", "Zeitstempel"])

# --- ZUSAMMENFASSUNG BERECHNEN ---
# Wir stellen sicher, dass 'Betrag' Zahlen sind
df["Betrag"] = pd.to_numeric(df["Betrag"], errors='coerce').fillna(0)

# Kontostand berechnen (Summe aller Beträge)
kontostand = df["Betrag"].sum()

# --- ANZEIGE KONTOSTAND ---
st.markdown(f"<h1 style='text-align: center; font-size: 80px;'>{kontostand:.2f} €</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>Aktueller Bankbestand</p>", unsafe_allow_html=True)

if st.button("🔄 Daten aktualisieren (Sync)", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.divider()

# --- NEUE BUCHUNG EINGEBEN ---
with st.expander("➕ Neue Buchung hinzufügen", expanded=True):
    col1, col2 = st.columns(2)
    
    with col1:
        # Hier deine Spieler-Liste anpassen
        name_input = st.selectbox("Name / Typ", 
                                  ["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi", 
                                   "Roulette (Rot)", "Roulette (Schwarz)", "Bank (Sonstiges)"])
        
    with col2:
        betrag_input = st.number_input("Betrag €", min_value=0.00, value=10.00, step=5.00, format="%.2f")

    aktion = st.radio("Aktion", [
        "Einzahlung (Spieler kauft Chips) [+]", 
        "Auszahlung (Spieler tauscht zurück) [-]",
        "Bank Einnahme (Roulette/Sonstiges) [+]",
        "Bank Ausgabe (Ausgaben) [-]"
    ])

    if st.button("Buchen ✅", type="primary", use_container_width=True):
        
        # Vorzeichen Logik
        final_betrag = betrag_input
        # Wenn es eine Auszahlung oder Ausgabe ist -> Minus rechnen
        if "[-]" in aktion:
            final_betrag = -betrag_input
            
        # Zeitstempel
        tz = pytz.timezone('Europe/Berlin')
        now = datetime.now(tz)
        datum_str = now.strftime("%d.%m.%Y")
        zeit_str = now.strftime("%H:%M:%S")
        
        # Neuer Eintrag
        neuer_eintrag = pd.DataFrame([{
            "Datum": datum_str,
            "Name": name_input,
            "Aktion": aktion.split(" (")[0], 
            "Betrag": final_betrag,
            "Notiz": aktion,
            "Zeitstempel": zeit_str
        }])
        
        # Anfügen und Speichern
        # Wir nehmen die bestehenden Daten (df) und hängen den neuen Eintrag an
        updated_df = pd.concat([df, neuer_eintrag], ignore_index=True)
        
        try:
            conn.update(worksheet="Buchungen", data=updated_df)
            st.success("Gebucht! Tabelle aktualisiert.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Fehler beim Speichern: {e}")

st.divider()

# --- DIAGRAMM & LISTE ---
st.subheader("📊 Übersicht")

if not df.empty:
    # 1. Diagramm: Wer hat wie viel eingezahlt?
    # Wir filtern nur echte Einzahlungen/Auszahlungen der Spieler (nicht Bank/Roulette)
    spieler_df = df[~df["Name"].str.contains("Roulette|Bank", case=False, na=False)]
    
    if not spieler_df.empty:
        # Gruppieren nach Name und Summe bilden
        leaderboard = spieler_df.groupby("Name")["Betrag"].sum().reset_index().sort_values("Betrag", ascending=False)
        
        fig = px.bar(leaderboard, x="Betrag", y="Name", orientation='h', 
                     text="Betrag", title="Netto-Einzahlungen (Wer hat wie viel drin?)")
        fig.update_layout(paper_bgcolor='white', plot_bgcolor='white', font_color='black')
        fig.update_traces(texttemplate='%{text:.2f} €', textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

    # 2. Historie Tabelle
    st.subheader("📜 Letzte Buchungen")
    # Neueste oben
    display_df = df.sort_index(ascending=False)
    st.dataframe(display_df[["Datum", "Name", "Betrag", "Aktion"]], use_container_width=True, hide_index=True)

else:
    st.info("Noch keine Buchungen vorhanden.")
