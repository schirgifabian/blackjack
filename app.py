import streamlit as st
import pandas as pd
import datetime
import altair as alt

# --- KONFIGURATION ---
st.set_page_config(page_title="Blackjack Dashboard", page_icon="♠️", layout="centered")

# CSS für Feinschliff (Trotz config.toml hilft das für Metric-Cards)
st.markdown("""
<style>
    .stMetric {
        background-color: #f5f5f5;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
        text-align: center;
    }
    /* Versteckt das Hamburger Menu oben rechts für saubereren Look */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- DATEN INITIALISIEREN (MIT DEINER HISTORIE) ---
if 'data' not in st.session_state:
    # Initialer Datensatz
    initial_data = [
        ["Initial", "Tobi", "Einzahlung", 10.0],
        ["Initial", "Alex", "Einzahlung", 30.0],
        ["Initial", "Dani", "Einzahlung", 30.0],
        ["Initial", "Fabi", "Einzahlung", 10.0],
        ["Initial", "Schirgi", "Einzahlung", 120.0],
        ["Initial", "Lüxn", "Einzahlung", 90.0],
        ["Initial", "Domi", "Einzahlung", 20.0],
        ["Initial", "Roulette (Rot)", "Bank Einnahme", 155.0],
        ["Initial", "Mischmaschine", "Bank Ausgabe", 32.26]
    ]
    st.session_state.data = pd.DataFrame(initial_data, columns=["Zeit", "Spieler", "Typ", "Betrag"])

# --- BERECHNUNGEN ---
df = st.session_state.data

# Wir filtern nach Typen
einzahlungen_spieler = df[df['Typ'] == 'Einzahlung']['Betrag'].sum()
auszahlungen_spieler = df[df['Typ'] == 'Auszahlung']['Betrag'].sum()
bank_sonder_ein = df[df['Typ'] == 'Bank Einnahme']['Betrag'].sum()
bank_sonder_aus = df[df['Typ'] == 'Bank Ausgabe']['Betrag'].sum()

# Der aktuelle Koffer-Inhalt
# (Startkapital ist hier 0, da wir alle Einzahlungen in der Historie haben)
bank_bestand = einzahlungen_spieler + bank_sonder_ein - auszahlungen_spieler - bank_sonder_aus

# --- DASHBOARD HEADER ---
st.title("♠️ Blackjack Bank")
st.caption(f"Aktuelle Runde | Light Mode Active ☀️")

# Großes KPI
st.markdown(f"<h1 style='text-align: center; color: #333; font-size: 3.5rem;'>{bank_bestand:,.2f} €</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'><b>Aktueller Bankbestand (Koffer)</b></p>", unsafe_allow_html=True)

st.divider()

# --- VISUALISIERUNG / STATS (Wunsch: Schöne Darstellung) ---
st.subheader("📊 Woher kommt das Geld?")

# Daten für das Chart aufbereiten
chart_data = df[df['Typ'].isin(['Einzahlung', 'Bank Einnahme'])].copy()
chart_data['Kategorie'] = chart_data.apply(lambda x: 'Spieler' if x['Typ'] == 'Einzahlung' else 'Roulette/Sonstiges', axis=1)

# Balkendiagramm: Wer hat wie viel reingebracht?
c = alt.Chart(chart_data).mark_bar().encode(
    x=alt.X('Betrag', title='Betrag in €'),
    y=alt.Y('Spieler', sort='-x', title=''),
    color=alt.Color('Kategorie', legend=None, scale=alt.Scale(domain=['Spieler', 'Roulette/Sonstiges'], range=['#1f77b4', '#2ca02c'])),
    tooltip=['Spieler', 'Betrag']
).properties(height=300)

st.altair_chart(c, use_container_width=True)

# --- EINGABE MASKE ---
with st.expander("➕ Neue Transaktion buchen", expanded=False):
    with st.form("input_form", clear_on_submit=True):
        st.write("Wer macht was?")
        col_in1, col_in2 = st.columns(2)
        
        with col_in1:
            # Dropdown mit den bekannten Namen + Option für Neue
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
                              "Bank Ausgabe (Sonstiges)",
                              "Bank Einnahme (Sonstiges)"],
                             horizontal=False)
        
        if st.form_submit_button("Buchen ✅", use_container_width=True):
            now_str = datetime.datetime.now().strftime("%H:%M")
            
            # Mapping der langen Texte auf kurze Datenbank-Typen
            if "Einzahlung" in typ_input: short_typ = "Einzahlung"
            elif "Auszahlung" in typ_input: short_typ = "Auszahlung"
            elif "Bank Ausgabe" in typ_input: short_typ = "Bank Ausgabe"
            else: short_typ = "Bank Einnahme"

            new_row = pd.DataFrame({
                "Zeit": [now_str],
                "Spieler": [name_manual],
                "Typ": [short_typ],
                "Betrag": [betrag_input]
            })
            st.session_state.data = pd.concat([st.session_state.data, new_row], ignore_index=True)
            st.rerun()

st.divider()

# --- TABELLEN ---
tab1, tab2 = st.tabs(["🏆 Leaderboard (Spieler)", "📜 Gesamte Historie"])

with tab1:
    # Nur Spieler berechnen (Roulette & Mischmaschine rausfiltern)
    player_df = df[df['Typ'].isin(['Einzahlung', 'Auszahlung'])]
    
    if not player_df.empty:
        stats = []
        for p in player_df['Spieler'].unique():
            sub = player_df[player_df['Spieler'] == p]
            buyin = sub[sub['Typ'] == 'Einzahlung']['Betrag'].sum()
            cashout = sub[sub['Typ'] == 'Auszahlung']['Betrag'].sum()
            # Gewinn ist Cashout - Buyin (Negativ heißt Geld verloren)
            profit = cashout - buyin 
            stats.append({"Spieler": p, "Buy-In": buyin, "Cash-Out": cashout, "Ergebnis": profit})
        
        stats_df = pd.DataFrame(stats).sort_values(by="Ergebnis", ascending=False)
        
        # Styling der Tabelle (Farben für Plus/Minus)
        def highlight_profit(val):
            color = 'green' if val > 0 else 'red' if val < 0 else 'black'
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
    # Die Rohdaten anzeigen, neueste oben
    st.dataframe(
        df.iloc[::-1], 
        use_container_width=True, 
        hide_index=True
    )
    
    if st.button("Letzten Eintrag löschen (Korrektur)"):
        if len(st.session_state.data) > 0:
            st.session_state.data = st.session_state.data[:-1]
            st.rerun()
