import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import pytz
import requests  # Wichtig für Ntfy

# --- KONFIGURATION ---
st.set_page_config(page_title="Blackjack Bank", page_icon="♠️", layout="centered")

# --- CSS HACK ---
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

# --- DATEN LADEN ---
try:
    df = conn.read(worksheet="Buchungen", ttl=0)
    rename_map = {"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"}
    df = df.rename(columns=rename_map)
    expected_cols = ["Datum", "Name", "Aktion", "Betrag"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None
except Exception:
    df = pd.DataFrame(columns=["Datum", "Zeitstempel", "Name", "Aktion", "Betrag"])

if not df.empty:
    df["Betrag"] = df["Betrag"].astype(str).str.replace(',', '.', regex=False)
    df["Betrag"] = pd.to_numeric(df["Betrag"], errors='coerce').fillna(0)

# --- LOGIK: KONTOSTAND ---
def berechne_netto(row):
    betrag = row["Betrag"]
    aktion = str(row["Aktion"]).lower()
    if ("ausgabe" in aktion or "auszahlung" in aktion) and betrag > 0:
        return -betrag
    return betrag

if not df.empty:
    df["Netto"] = df.apply(berechne_netto, axis=1)
    kontostand = df["Netto"].sum()
else:
    kontostand = 0.0

# --- ANZEIGE ---
color = "black" if kontostand >= 0 else "red"
st.markdown(f"<h1 style='text-align: center; font-size: 80px; color: {color};'>{kontostand:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".") + "</h1>", unsafe_allow_html=True)

if st.button("🔄 Aktualisieren", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.divider()

# --- BUCHUNG ---
st.subheader("➕ Neue Buchung")

with st.container(border=True):
    col1, col2 = st.columns(2)
    with col1:
        namen_liste = ["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi", "Manuelle Ausgabe 📝"]
        auswahl_name = st.selectbox("Name / Typ", namen_liste)
        final_name = auswahl_name
        if auswahl_name == "Manuelle Ausgabe 📝":
            custom_input = st.text_input("Wofür?", placeholder="z.B. Pizza...")
            if custom_input: final_name = custom_input
            else: final_name = "Sonstiges"

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
        
        # 1. In Google Sheets speichern
        neuer_eintrag = pd.DataFrame([{
            "Datum": now.strftime("%d.%m.%Y"),
            "Zeit": now.strftime("%H:%M"),
            "Spieler": final_name,
            "Typ": typ_short,
            "Betrag": betrag_input
        }])
        
        df_raw = conn.read(worksheet="Buchungen", ttl=0)
        updated_df = pd.concat([df_raw, neuer_eintrag], ignore_index=True)
        conn.update(worksheet="Buchungen", data=updated_df)
        
        # 2. Ntfy Benachrichtigung senden (Nur bei Bank-Aktionen)
        if "Bank" in typ_short:
            # Feedback anzeigen, dass gesendet wird
            st.toast(f"Sende Benachrichtigung an bj-boys-dashboard...", icon="📡")
            
            try:
                ntfy_topic = "bj-boys-dashboard"
                
                if "Einnahme" in typ_short:
                    title = "🤑 Bank Einnahme"
                    message = f"Plus: {betrag_input:.2f} €\nGrund: {final_name}"
                    tags = "moneybag,up"
                else: # Ausgabe
                    title = "💸 Bank Ausgabe"
                    message = f"Minus: {betrag_input:.2f} €\nZweck: {final_name}"
                    tags = "chart_with_downwards_trend,down"

                # Senden
                response = requests.post(
                    f"https://ntfy.sh/{ntfy_topic}",
                    data=message.encode('utf-8'),
                    headers={"Title": title.encode('utf-8'), "Tags": tags}
                )
                
                if response.status_code == 200:
                    st.toast("Benachrichtigung erfolgreich!", icon="✅")
                else:
                    st.error(f"Fehler beim Senden an Ntfy: Code {response.status_code}")
                    
            except Exception as e:
                st.error(f"Kritischer Fehler bei Ntfy: {e}")

        st.success(f"Gebucht: {final_name} ({betrag_input}€)")
        st.cache_data.clear()
        st.rerun()

st.divider()

# --- STATISTIK ---
st.subheader("📊 Statistik")
if not df.empty:
    tab1, tab2 = st.tabs(["💰 Einzahlungen", "💸 Auszahlungen & Ausgaben"])
    with tab1:
        ein_df = df[df["Aktion"].astype(str).str.contains("Einzahlung", case=False, na=False)].copy()
        if not ein_df.empty:
            leaderboard = ein_df.groupby("Name")["Betrag"].sum().reset_index().sort_values("Betrag", ascending=True)
            fig = px.bar(leaderboard, x="Betrag", y="Name", orientation='h', text="Betrag", title="Einzahlungen")
            fig.update_layout(paper_bgcolor='white', plot_bgcolor='white', font_color='black')
            fig.update_traces(marker_color='#1976D2', texttemplate='%{text:.2f} €', textposition='outside')
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("Noch keine Einzahlungen.")
    with tab2:
        aus_df = df[df["Aktion"].astype(str).str.contains("Aus", case=False, na=False)].copy()
        if not aus_df.empty:
            lost_board = aus_df.groupby("Name")["Betrag"].sum().reset_index().sort_values("Betrag", ascending=True)
            fig2 = px.bar(lost_board, x="Betrag", y="Name", orientation='h', text="Betrag", title="Ausgaben / Auszahlungen")
            fig2.update_layout(paper_bgcolor='white', plot_bgcolor='white', font_color='black')
            fig2.update_traces(marker_color='#D32F2F', texttemplate='%{text:.2f} €', textposition='outside')
            st.plotly_chart(fig2, use_container_width=True)
        else: st.info("Keine Ausgaben.")

    st.subheader("📜 Letzte Buchungen")
    display_df = df[["Datum", "Name", "Aktion", "Betrag"]].sort_index(ascending=False).copy()
    def highlight_rows(row):
        return ['color: #D32F2F; font-weight: bold'] * len(row) if "aus" in str(row["Aktion"]).lower() else ['color: black'] * len(row)
    st.dataframe(display_df.style.apply(highlight_rows, axis=1).format({"Betrag": lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")}), use_container_width=True, hide_index=True, height=400)
else:
    st.info("Keine Daten vorhanden.")
