import streamlit as st
import pandas as pd
import datetime
import altair as alt
from streamlit_gsheets import GSheetsConnection

# --- KONFIGURATION ---
st.set_page_config(page_title="Blackjack Dashboard", page_icon="♠️", layout="centered")

# CSS: Erzwingt weißes Design auch bei harten Fällen und entfernt unnötigen Rand
st.markdown("""
<style>
    /* Globaler Hintergrund weiß erzwingen */
    .stApp {
        background-color: #FFFFFF;
        color: #000000;
    }
    /* Metriken schön stylen */
    .stMetric {
        background-color: #F9F9F9;
        border: 1px solid #E0E0E0;
        padding: 10px;
        border-radius: 8px;
        text-align: center;
        color: #000000 !important;
    }
    /* Inputs weiß machen */
    .stTextInput, .stNumberInput, .stSelectbox {
        color: #000000;
    }
    /* Versteckt Header/Footer */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- DATENBANK VERBINDUNG ---
# Wir holen die Daten direkt aus Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Daten laden (ttl=0 bedeutet: kein Caching, immer live neu laden beim Klick)
try:
    df = conn.read(worksheet="Log", ttl=0)
    # Sicherstellen, dass leere Zeilen am Ende ignoriert werden
    df = df.dropna(how="all")
except Exception as e:
    st.error(f"Fehler beim Laden der Datenbank: {e}")
    st.stop()

# --- BERECHNUNGEN ---
# Wir filtern nach Typen für die Bank-Berechnung
einzahlungen_spieler = df[df['Typ'] == 'Einzahlung']['Betrag'].sum()
auszahlungen_spieler = df[df['Typ'] == 'Auszahlung']['Betrag'].sum()
bank_sonder_ein = df[df['Typ'] == 'Bank Einnahme']['Betrag'].sum()
bank_sonder_aus = df[df['Typ'] == 'Bank Ausgabe']['Betrag'].sum()

# Der aktuelle Koffer-Inhalt
bank_bestand = einzahlungen_spieler + bank_sonder_ein - auszahlungen_spieler - bank_sonder_aus

# --- DASHBOARD HEADER ---
st.title("♠️ Blackjack Bank")

# Großes KPI
st.markdown(f"<h1 style='text-align: center; color: #000000; font-size: 4rem; margin-bottom: 0;'>{bank_bestand:,.2f} €</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>Aktueller Bankbestand</p>", unsafe_allow_html=True)

if st.button("🔄 Daten aktualisieren (Sync)", use_container_width=True):
    st.rerun()

st.divider()

# --- STATS CHART ---
st.subheader("📊 Einnahmen Übersicht")
chart_data = df[df['Typ'].isin(['Einzahlung', 'Bank Einnahme'])].copy()
chart_data['Kategorie'] = chart_data.apply(lambda x: 'Spieler' if x['Typ'] == 'Einzahlung' else 'Sonstiges', axis=1)

c = alt.Chart(chart_data).mark_bar().encode(
    x=alt.X('Betrag', title='Betrag €'),
    y=alt.Y('Spieler', sort='-x', title=''),
    color=alt.Color('Kategorie', legend=None, scale=alt.Scale(range=['#333333', '#888888'])),
    tooltip=['Spieler', 'Betrag', 'Datum']
).properties(height=250)
st.altair_chart(c, use_container_width=True)

# --- EINGABE MASKE ---
with st.expander("➕ Neue Buchung hinzufügen", expanded=True):
    with st.form("input_form", clear_on_submit=True):
        col_in1, col_in2 = st.columns(2)
        
        with col_in1:
            bekannte_spieler = ["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi", "Neuer Spieler..."]
            name_input = st.selectbox("Name", bekannte_spieler)
            if name_input == "Neuer Spieler...":
                name_manual = st.text_input("Name eingeben")
            else:
                name_manual = name_input
        
        with col_in2:
            betrag_input = st.number_input("Betrag €", min_value=0.0, step=5.0, value=50.0)
        
        typ_input = st.radio("Aktion", 
                             ["Einzahlung (Spieler kauft Chips)", 
                              "Auszahlung (Spieler tauscht zurück)",
                              "Bank Ausgabe (Ausgaben)",
                              "Bank Einnahme (Roulette/Sonstiges)"],
                             horizontal=False)
        
        if st.form_submit_button("Buchen ✅", use_container_width=True):
            # Zeitstempel generieren
            now = datetime.datetime.now()
            date_str = now.strftime("%d.%m.%Y")
            time_str = now.strftime("%H:%M")
            
            # Mapping
            if "Einzahlung" in typ_input: short_typ = "Einzahlung"
            elif "Auszahlung" in typ_input: short_typ = "Auszahlung"
            elif "Bank Ausgabe" in typ_input: short_typ = "Bank Ausgabe"
            else: short_typ = "Bank Einnahme"

            # Neue Zeile erstellen
            new_data = pd.DataFrame([{
                "Datum": date_str,
                "Zeit": time_str,
                "Spieler": name_manual,
                "Typ": short_typ,
                "Betrag": betrag_input
            }])
            
            # An bestehende Daten anhängen
            updated_df = pd.concat([df, new_data], ignore_index=True)
            
            # Zurück zu Google Sheets schreiben
            conn.update(worksheet="Log", data=updated_df)
            
            st.success("Gespeichert!")
            st.rerun()

st.divider()

# --- TABELLEN ---
tab1, tab2 = st.tabs(["🏆 Leaderboard", "📜 Historie"])

with tab1:
    player_df = df[df['Typ'].isin(['Einzahlung', 'Auszahlung'])]
    
    if not player_df.empty:
        stats = []
        for p in player_df['Spieler'].unique():
            sub = player_df[player_df['Spieler'] == p]
            buyin = sub[sub['Typ'] == 'Einzahlung']['Betrag'].sum()
            cashout = sub[sub['Typ'] == 'Auszahlung']['Betrag'].sum()
            profit = cashout - buyin 
            stats.append({"Spieler": p, "Buy-In": buyin, "Cash-Out": cashout, "Ergebnis": profit})
        
        stats_df = pd.DataFrame(stats).sort_values(by="Ergebnis", ascending=False)
        
        def highlight_profit(val):
            color = '#006400' if val > 0 else '#8B0000' if val < 0 else 'black' # Dunkelgrün / Dunkelrot für gute Lesbarkeit auf Weiß
            return f'color: {color}; font-weight: bold;'

        st.dataframe(
            stats_df.style.format({"Buy-In": "{:.2f} €", "Cash-Out": "{:.2f} €", "Ergebnis": "{:+.2f} €"})
                    .map(highlight_profit, subset=['Ergebnis']),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Noch keine Spieler-Daten.")

with tab2:
    # Umgekehrt sortieren (neueste oben)
    st.dataframe(
        df.iloc[::-1], 
        use_container_width=True, 
        hide_index=True
    )
