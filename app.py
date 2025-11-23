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
            /* Tabellen-Schriftart anpassen für bessere Lesbarkeit */
            div[data-testid="stDataFrame"] {
                font-family: monospace;
            }
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- TITEL ---
st.title("♠️ Blackjack Bank")

# --- VERBINDUNG HERSTELLEN ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- DATEN LADEN & BEREINIGEN ---
try:
    df = conn.read(worksheet="Buchungen", ttl=0)
    
    # Spalten mappen
    rename_map = {"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"}
    df = df.rename(columns=rename_map)
    
    # Fehlende Spalten ergänzen
    expected_cols = ["Datum", "Name", "Aktion", "Betrag"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None

except Exception:
    df = pd.DataFrame(columns=["Datum", "Zeitstempel", "Name", "Aktion", "Betrag", "Notiz"])

# ZAHLEN FORMATIEREN (Komma fixen & in Zahl wandeln)
if not df.empty:
    df["Betrag"] = df["Betrag"].astype(str).str.replace(',', '.', regex=False)
    df["Betrag"] = pd.to_numeric(df["Betrag"], errors='coerce').fillna(0)

# --- LOGIK: KONTOSTAND ---
def berechne_netto(row):
    betrag = row["Betrag"]
    aktion = str(row["Aktion"]).lower()
    # Ausgaben abziehen
    if ("ausgabe" in aktion or "auszahlung" in aktion) and betrag > 0:
        return -betrag
    return betrag

if not df.empty:
    df["Netto"] = df.apply(berechne_netto, axis=1)
    kontostand = df["Netto"].sum()
else:
    kontostand = 0.0

# --- ANZEIGE KONTOSTAND ---
color = "black" if kontostand >= 0 else "red"
st.markdown(f"<h1 style='text-align: center; font-size: 80px; color: {color};'>{kontostand:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".") + "</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>Aktueller Bankbestand</p>", unsafe_allow_html=True)

if st.button("🔄 Aktualisieren", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.divider()

# --- NEUE BUCHUNG ---
with st.expander("➕ Neue Buchung hinzufügen", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        name_input = st.selectbox("Name / Typ", 
                                  ["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi", 
                                   "Roulette (Rot)", "Roulette (Schwarz)", "Mischmaschine", "Sonstiges"])
    with col2:
        betrag_input = st.number_input("Betrag €", min_value=0.00, value=10.00, step=5.00, format="%.2f")

    aktion_auswahl = st.radio("Aktion", [
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
            "Spieler": name_input,
            "Typ": typ_short,
            "Betrag": betrag_input
        }])
        
        df_raw = conn.read(worksheet="Buchungen", ttl=0)
        updated_df = pd.concat([df_raw, neuer_eintrag], ignore_index=True)
        conn.update(worksheet="Buchungen", data=updated_df)
        st.success("Gebucht!")
        st.cache_data.clear()
        st.rerun()

st.divider()

# --- DIAGRAMME (2 STÜCK) ---
st.subheader("📊 Statistik")

if not df.empty:
    tab1, tab2 = st.tabs(["💰 Einzahlungen (Top-Liste)", "💸 Auszahlungen & Ausgaben"])
    
    # 1. EINZAHLUNGEN CHART
    with tab1:
        # Filter: Nur "Einzahlung" und keine Bank-Dinge
        ein_df = df[df["Aktion"].astype(str).str.contains("Einzahlung", case=False, na=False)].copy()
        if not ein_df.empty:
            # Gruppieren und Sortieren
            leaderboard = ein_df.groupby("Name")["Betrag"].sum().reset_index().sort_values("Betrag", ascending=True) # Ascending true für Balken von oben nach unten
            
            fig = px.bar(leaderboard, x="Betrag", y="Name", orientation='h', 
                         text="Betrag", title="Wer hat wie viel eingezahlt?")
            fig.update_layout(paper_bgcolor='white', plot_bgcolor='white', font_color='black')
            # Textformatierung im Chart
            fig.update_traces(marker_color='#1976D2', texttemplate='%{text:.2f} €', textposition='outside')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Noch keine Einzahlungen.")

    # 2. AUSZAHLUNGEN CHART
    with tab2:
        # Filter: Alles was "Ausgabe" oder "Auszahlung" ist
        aus_df = df[df["Aktion"].astype(str).str.contains("Aus", case=False, na=False)].copy()
        if not aus_df.empty:
            lost_board = aus_df.groupby("Name")["Betrag"].sum().reset_index().sort_values("Betrag", ascending=True)
            
            fig2 = px.bar(lost_board, x="Betrag", y="Name", orientation='h', 
                          text="Betrag", title="Wo ging das Geld hin?")
            fig2.update_layout(paper_bgcolor='white', plot_bgcolor='white', font_color='black')
            # Rote Balken für Ausgaben
            fig2.update_traces(marker_color='#D32F2F', texttemplate='%{text:.2f} €', textposition='outside')
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Noch keine Auszahlungen oder Ausgaben.")

    st.divider()

    # --- HISTORIE TABELLE (Gestylet) ---
    st.subheader("📜 Letzte Buchungen")
    
    # Wir bereiten die Tabelle für die Anzeige vor
    display_df = df[["Datum", "Name", "Aktion", "Betrag"]].sort_index(ascending=False).copy()

    # Funktion für Farbe: Rot wenn "Aus" im Text, sonst Standard
    def highlight_rows(row):
        aktion = str(row["Aktion"]).lower()
        if "aus" in aktion: # Findet Ausgabe und Auszahlung
            return ['color: #D32F2F; font-weight: bold'] * len(row)
        return ['color: black'] * len(row)

    # Funktion für Formatierung: 10.0 -> "10,00"
    def format_german_currency(val):
        return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # Styling anwenden
    styled_df = display_df.style.apply(highlight_rows, axis=1)\
        .format({"Betrag": format_german_currency})

    st.dataframe(styled_df, use_container_width=True, hide_index=True, height=400)

else:
    st.info("Keine Daten vorhanden.")
