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

# --- DATEN LADEN & BEREINIGEN ---
try:
    df = conn.read(worksheet="Buchungen", ttl=0)
    
    # 1. SPALTEN UMBENENNEN (Damit Code und Tabelle übereinstimmen)
    # Wir mappen "Spieler" -> "Name" und "Typ" -> "Aktion"
    rename_map = {"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"}
    df = df.rename(columns=rename_map)
    
    # Falls Spalten fehlen (z.B. leere Tabelle), erstellen wir sie
    expected_cols = ["Datum", "Name", "Aktion", "Betrag"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None

except Exception:
    # Fallback bei leerer Tabelle
    df = pd.DataFrame(columns=["Datum", "Zeitstempel", "Name", "Aktion", "Betrag", "Notiz"])

# 2. ZAHLEN FORMATIEREN (Komma zu Punkt & Text zu Zahl)
# Wandelt "32,26" in 32.26 um und macht daraus echte Zahlen
if not df.empty:
    df["Betrag"] = df["Betrag"].astype(str).str.replace(',', '.', regex=False)
    df["Betrag"] = pd.to_numeric(df["Betrag"], errors='coerce').fillna(0)

# 3. LOGIK: ECHTEN KONTOSTAND BERECHNEN
# Wir erstellen eine Hilfsspalte "Netto", die schaut: Ist es eine Ausgabe? -> Minus!
def berechne_netto(row):
    betrag = row["Betrag"]
    aktion = str(row["Aktion"]).lower() # Alles kleinschreiben zum Prüfen
    
    # Wenn "ausgabe" oder "auszahlung" im Text steht, muss es abgezogen werden
    # (aber nur wenn es nicht schon negativ ist)
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
st.markdown(f"<h1 style='text-align: center; font-size: 80px; color: {color};'>{kontostand:.2f} €</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>Aktueller Bankbestand</p>", unsafe_allow_html=True)

if st.button("🔄 Daten aktualisieren (Sync)", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.divider()

# --- NEUE BUCHUNG ---
with st.expander("➕ Neue Buchung hinzufügen", expanded=True):
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
        
        # Wir speichern den Betrag IMMER positiv in der Tabelle (wie in deinem Screenshot)
        # Die Logik oben (berechne_netto) kümmert sich beim Lesen ums Minus.
        # Nur der "Typ" (Aktion) muss stimmen.
        
        typ_short = aktion_auswahl.split(" (")[0] # Z.B. "Einzahlung" oder "Bank Ausgabe"
        
        # Zeitstempel
        tz = pytz.timezone('Europe/Berlin')
        now = datetime.now(tz)
        
        # Neuer Eintrag passend zu deiner Tabellen-Struktur
        neuer_eintrag = pd.DataFrame([{
            "Datum": now.strftime("%d.%m.%Y"),
            "Zeit": now.strftime("%H:%M"),     # Spalte heißt in Sheet "Zeit"
            "Spieler": name_input,             # Spalte heißt in Sheet "Spieler"
            "Typ": typ_short,                  # Spalte heißt in Sheet "Typ"
            "Betrag": betrag_input             # Wir speichern als Zahl, Google Sheets macht evtl Komma draus
        }])
        
        # Da wir df oben umbenannt haben ("Spieler" -> "Name"), müssen wir zum SPEICHERN
        # wieder die Original-Namen benutzen, damit die Tabelle nicht kaputt geht.
        # Wir laden die Tabelle kurz neu im Rohformat, hängen an und speichern.
        df_raw = conn.read(worksheet="Buchungen", ttl=0)
        updated_df = pd.concat([df_raw, neuer_eintrag], ignore_index=True)
        
        conn.update(worksheet="Buchungen", data=updated_df)
        
        st.success("Gebucht!")
        st.cache_data.clear()
        st.rerun()

st.divider()

# --- DIAGRAMM & HISTORIE ---
st.subheader("📊 Übersicht")

if not df.empty:
    # 1. Diagramm: Nur Spieler Einzahlungen anzeigen
    # Wir filtern alles raus, was "Bank", "Roulette" oder "Mischmaschine" ist
    # ODER wir filtern einfach nur auf Typ="Einzahlung"
    
    # Filter: Nur Zeilen wo "Einzahlung" im Typ steht
    spieler_df = df[df["Aktion"].astype(str).str.contains("Einzahlung", case=False, na=False)].copy()
    
    if not spieler_df.empty:
        leaderboard = spieler_df.groupby("Name")["Betrag"].sum().reset_index().sort_values("Betrag", ascending=False)
        
        fig = px.bar(leaderboard, x="Betrag", y="Name", orientation='h', 
                     text="Betrag", title="Wer hat wie viele Chips gekauft?")
        fig.update_layout(paper_bgcolor='white', plot_bgcolor='white', font_color='black')
        fig.update_traces(texttemplate='%{text:.2f} €', textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

    # 2. Historie Tabelle
    st.subheader("📜 Letzte Buchungen")
    # Anzeige anpassen (Spalten schön benennen)
    display_df = df[["Datum", "Name", "Aktion", "Betrag"]].sort_index(ascending=False)
    st.dataframe(display_df, use_container_width=True, hide_index=True)
