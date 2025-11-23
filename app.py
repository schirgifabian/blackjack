import streamlit as st
import pandas as pd
import datetime

# --- KONFIGURATION & DESIGN ---
st.set_page_config(page_title="Blackjack Bank", page_icon="♠️", layout="centered")

# CSS Hack für schönere Darstellung auf Mobilgeräten (Tabellen kompakter)
st.markdown("""
<style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 10px;
        text-align: center;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
    }
</style>
""", unsafe_allow_html=True)

# --- STATUS INITIALISIEREN ---
# Wir nutzen Session State, um die Daten während der Laufzeit zu speichern
if 'data' not in st.session_state:
    st.session_state.data = pd.DataFrame(columns=["Zeit", "Spieler", "Typ", "Betrag"])

if 'startkapital' not in st.session_state:
    st.session_state.startkapital = 1000.0  # Standardwert

# --- SIDEBAR (EINSTELLUNGEN) ---
with st.sidebar:
    st.header("⚙️ Einstellungen")
    st.session_state.startkapital = st.number_input(
        "Bank Startkapital (€)", 
        value=st.session_state.startkapital, 
        step=50.0
    )
    
    st.divider()
    st.write("⚠️ **Daten-Reset:**")
    if st.button("Alles löschen & Neustart", type="primary"):
        st.session_state.data = pd.DataFrame(columns=["Zeit", "Spieler", "Typ", "Betrag"])
        st.rerun()

# --- HAUPTBEREICH ---
st.title("♠️ Blackjack Bank")

# 1. BERECHNUNGEN
df = st.session_state.data
total_buyin = df[df['Typ'] == 'Einzahlung']['Betrag'].sum()
total_payout = df[df['Typ'] == 'Auszahlung']['Betrag'].sum()
bank_bestand = st.session_state.startkapital + total_buyin - total_payout

# 2. KPI DASHBOARD (Die großen Zahlen)
col1, col2 = st.columns(2)
col3, col4 = st.columns(2)

with col1:
    st.metric("🏦 Bank Bestand", f"{bank_bestand:,.0f} €", delta_color="normal")
with col2:
    # Profit der Bank (Einzahlung - Auszahlung)
    bank_profit = total_buyin - total_payout
    st.metric("📈 Bank Gewinn", f"{bank_profit:,.0f} €", delta=bank_profit)

with col3:
    st.metric("Eingezahlt (Buy-In)", f"{total_buyin:,.0f} €")
with col4:
    st.metric("Ausgezahlt (Cash-Out)", f"{total_payout:,.0f} €")

st.divider()

# 3. EINGABE MASKE (Expander, damit es am Handy platzsparend ist)
with st.expander("➕ Neue Buchung (Hier klicken)", expanded=True):
    with st.form("buchung_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            spieler_name = st.text_input("Name des Spielers")
        with c2:
            betrag = st.number_input("Betrag (€)", min_value=1.0, step=5.0, value=50.0)
        
        typ_wahl = st.radio("Art der Buchung", ["Einzahlung (Spieler kauft Chips)", "Auszahlung (Spieler gibt Chips ab)"], horizontal=True)
        
        submitted = st.form_submit_button("Buchen ✅", use_container_width=True)
        
        if submitted and spieler_name:
            now = datetime.datetime.now().strftime("%H:%M")
            art_short = "Einzahlung" if "Einzahlung" in typ_wahl else "Auszahlung"
            
            new_entry = pd.DataFrame({
                "Zeit": [now], 
                "Spieler": [spieler_name], 
                "Typ": [art_short], 
                "Betrag": [betrag]
            })
            st.session_state.data = pd.concat([st.session_state.data, new_entry], ignore_index=True)
            st.rerun() # Seite neu laden um Daten zu aktualisieren

# 4. SPIELER STATISTIK (Wer gewinnt gerade?)
if not df.empty:
    st.subheader("🏆 Spieler Bilanz")
    
    # Pivot Tabelle erstellen um pro Spieler zu rechnen
    players = df['Spieler'].unique()
    stats = []
    
    for p in players:
        p_df = df[df['Spieler'] == p]
        einz = p_df[p_df['Typ'] == 'Einzahlung']['Betrag'].sum()
        ausz = p_df[p_df['Typ'] == 'Auszahlung']['Betrag'].sum()
        profit = ausz - einz
        stats.append({"Spieler": p, "Buy-In": einz, "Cash-Out": ausz, "Gewinn/Verlust": profit})
    
    stats_df = pd.DataFrame(stats).sort_values(by="Gewinn/Verlust", ascending=False)
    
    # Tabelle schön darstellen
    st.dataframe(
        stats_df, 
        column_config={
            "Gewinn/Verlust": st.column_config.NumberColumn(
                "Gewinn/Verlust",
                format="%d €"
            )
        },
        hide_index=True,
        use_container_width=True
    )

    # 5. LETZTE BUCHUNGEN & KORREKTUR
    st.subheader("📜 Letzte Buchungen")
    st.dataframe(df.sort_index(ascending=False).head(5), use_container_width=True, hide_index=True)
    
    if st.button("Letzte Buchung rückgängig machen ↩️"):
        st.session_state.data = st.session_state.data[:-1]
        st.rerun()

else:
    st.info("Noch keine Buchungen vorhanden. Starte oben mit einer Eingabe!")
