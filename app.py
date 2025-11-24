import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import pytz
import urllib.parse

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
            div[data-testid="stCheckbox"] { padding-top: 2rem; } 
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
    
    # Datum parsen und Zeitzonenfehler beheben
    df['Full_Date'] = pd.to_datetime(df['Datum'] + ' ' + df['Zeitstempel'].fillna('00:00'), format='%d.%m.%Y %H:%M', errors='coerce')
    df['Full_Date'] = df['Full_Date'].fillna(pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce'))

# --- HELPER: GIROCODE GENERATOR ---
def generate_epc_qr_url(name, iban, amount, purpose):
    iban_clean = iban.replace(" ", "").upper()
    amount_str = f"EUR{amount:.2f}"
    epc_data = f"""BCD
002
1
SCT

{name}
{iban_clean}
{amount_str}


{purpose}
"""
    data_encoded = urllib.parse.quote(epc_data)
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={data_encoded}"

# --- NETTO BERECHNUNG ---
def berechne_netto(row):
    betrag = row["Betrag"]
    aktion = str(row["Aktion"]).lower()
    if ("ausgabe" in aktion or "auszahlung" in aktion):
        return -betrag
    return betrag

# --- UI: FILTERBEREICH ---
st.divider()
col_filter, col_check = st.columns([3, 1])

with col_filter:
    zeitraum = st.selectbox("Zeitraum wählen:", ["Aktuelle Session", "Alles"], index=0)

with col_check:
    exclude_bank = st.checkbox("Bank ausbl.")

# --- DATEN FILTERN ---
now = datetime.now(pytz.timezone('Europe/Berlin'))
df_stats = df.copy()

if zeitraum == "Aktuelle Session":
    today_start_aware = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # WICHTIG: tzinfo=None verhindert den Vergleichsfehler
    start_limit = (today_start_aware - timedelta(days=1)).replace(tzinfo=None)
    df_stats = df_stats[df_stats['Full_Date'] >= start_limit]

# --- KPI LOGIK ---
if exclude_bank:
    df_stats = df_stats[~df_stats["Aktion"].str.contains("Bank", case=False)]

df_stats["Netto"] = df_stats.apply(berechne_netto, axis=1)
df_stats = df_stats.sort_values("Full_Date")
df_stats["Bankverlauf"] = df_stats["Netto"].cumsum()

if not df_stats.empty:
    chips_in = df_stats[df_stats["Aktion"].str.contains("Einzahlung", case=False, na=False)]["Betrag"].sum()
    chips_out = df_stats[df_stats["Aktion"].str.contains("Auszahlung", case=False, na=False)]["Betrag"].sum()
    delta_bank = chips_in - chips_out

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Chips gekauft", f"{chips_in:,.0f} €")
    kpi2.metric("Chips ausgezahlt", f"{chips_out:,.0f} €")
    kpi3.metric("Bankstand (Netto)", f"{delta_bank:,.2f} €", delta_color="normal")

    tab_bilanz, tab_verlauf, tab_list = st.tabs(["🏆 Spieler", "📈 Verlauf", "📝 Liste"])

    # Profite berechnen
    df_players_only = df_stats[~df_stats["Aktion"].str.contains("Bank", case=False)].copy()
    
    def get_profit(x):
        ein = x[x["Aktion"].str.contains("Einzahlung")]["Betrag"].sum()
        aus = x[x["Aktion"].str.contains("Auszahlung")]["Betrag"].sum()
        return aus - ein 

    game_data_exists = not df_players_only.empty
    lb = pd.DataFrame()

    if game_data_exists:
        lb = df_players_only.groupby("Name").apply(get_profit).reset_index(name="Profit").sort_values("Profit", ascending=False)

    with tab_bilanz:
        if not lb.empty:
            lb["Color"] = lb["Profit"].apply(lambda x: '#2E7D32' if x >= 0 else '#C62828')
            fig = px.bar(lb, x="Profit", y="Name", orientation='h', text="Profit", title="Gewinn/Verlust pro Spieler")
            fig.update_traces(marker_color=lb["Color"], texttemplate='%{text:+.2f} €', textposition='outside')
            fig.update_layout(xaxis_title="Gewinn", paper_bgcolor='white', plot_bgcolor='white', font_color='black')
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("Keine Spielerdaten.")

    with tab_verlauf:
        fig_line = px.line(df_stats, x="Full_Date", y="Bankverlauf", title="Entwicklung Bankbestand", line_shape='hv')
        fig_line.update_layout(paper_bgcolor='white', plot_bgcolor='white', font_color='black', yaxis_title="Kontostand €")
        fig_line.update_traces(line_color='black', line_width=3)
        st.plotly_chart(fig_line, use_container_width=True)

    with tab_list:
            st.dataframe(df_stats[["Datum", "Zeitstempel", "Name", "Aktion", "Betrag"]].sort_index(ascending=False), use_container_width=True, hide_index=True)

    # --- TAGESABSCHLUSS (SAFE QR CODES) ---
    st.markdown("---")
    with st.expander("💸 Tagesabschluss & Abrechnung", expanded=False):
        
        secrets_iban = st.secrets.get("bank", {}).get("iban", "")
        secrets_owner = st.secrets.get("bank", {}).get("owner", "")
        
        if secrets_iban:
            iban_to_use = secrets_iban
            owner_to_use = secrets_owner
            st.success(f"Empfängerkonto: {owner_to_use}")
        else:
            st.warning("Keine Bankdaten konfiguriert.")
            c_iban, c_owner = st.columns(2)
            iban_to_use = c_iban.text_input("IBAN", value="")
            owner_to_use = c_owner.text_input("Inhaber", value="Blackjack Kasse")

        if iban_to_use and not lb.empty:
            losers = lb[lb["Profit"] < 0].copy()
            
            if losers.empty:
                st.balloons()
                st.success("Keine offenen Schulden! Die Bank hat gewonnen oder alle sind 'break even'.")
            else:
                st.write("Wähle die Person aus, die bezahlen möchte:")
                
                # Dictionary erstellen für das Dropdown: "Name (Betrag)" -> Daten
                options = {f"{row['Name']} (Schuldet {abs(row['Profit']):.2f} €)": row for _, row in losers.iterrows()}
                
                selected_option = st.selectbox("Zahlungspflichtiger Spieler:", options.keys())
                
                if selected_option:
                    # Daten des gewählten Spielers holen
                    selected_row = options[selected_option]
                    pay_amount = abs(selected_row["Profit"])
                    player_name = selected_row["Name"]
                    
                    qr_url = generate_epc_qr_url(
                        name=owner_to_use,
                        iban=iban_to_use,
                        amount=pay_amount,
                        purpose="Spieleabend"
                    )
                    
                    # QR Code zentriert anzeigen
                    col_spacer1, col_qr, col_spacer2 = st.columns([1, 2, 1])
                    with col_qr:
                        st.image(qr_url, caption=f"GiroCode für {player_name}", width=300)
                        st.info(f"📱 Bitte Banking-App öffnen und scannen.\nBetrag: {pay_amount:.2f} €")

else:
    st.info("Datenbank leer.")
