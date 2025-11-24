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
            /* Checkbox besser ausrichten */
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
    
    # Datum parsen
    df['Full_Date'] = pd.to_datetime(df['Datum'] + ' ' + df['Zeitstempel'].fillna('00:00'), format='%d.%m.%Y %H:%M', errors='coerce')
    df['Full_Date'] = df['Full_Date'].fillna(pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce'))

# --- HELPER: GIROCODE GENERATOR ---
def generate_epc_qr_url(name, iban, amount, purpose):
    """
    Erstellt eine URL für einen EPC-QR Code.
    """
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
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    df_stats = df_stats[df_stats['Full_Date'] >= yesterday_start]

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
        return aus - ein # Positiv = Gewinn, Negativ = Verlust

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

    # --- TAGESABSCHLUSS (QR CODES) ---
    st.markdown("---")
    with st.expander("💸 Tagesabschluss & Abrechnung", expanded=False):
        
        # Versuche Daten aus Secrets zu laden
        secrets_iban = st.secrets.get("bank", {}).get("iban", "")
        secrets_owner = st.secrets.get("bank", {}).get("owner", "")
        
        if secrets_iban:
            # Wenn Secrets da sind, nehmen wir die automatisch
            iban_to_use = secrets_iban
            owner_to_use = secrets_owner
            st.success(f"Zahlungsziel geladen: {owner_to_use} (aus Konfiguration)")
        else:
            # Fallback: Eingabefelder
            st.warning("Keine Bankdaten in secrets.toml gefunden. Bitte manuell eingeben.")
            c_iban, c_owner = st.columns(2)
            iban_to_use = c_iban.text_input("IBAN", value="")
            owner_to_use = c_owner.text_input("Inhaber", value="Blackjack Kasse")

        if iban_to_use and not lb.empty:
            losers = lb[lb["Profit"] < 0].copy()
            
            if losers.empty:
                st.success("Heute gibt es keine Verlierer! 🎉")
            else:
                st.write("Scannt den Code mit eurer Banking-App:")
                cols = st.columns(len(losers) if len(losers) < 3 else 3)
                
                for index, (idx, row) in enumerate(losers.iterrows()):
                    pay_amount = abs(row["Profit"])
                    player_name = row["Name"]
                    
                    qr_url = generate_epc_qr_url(
                        name=owner_to_use,
                        iban=iban_to_use,
                        amount=pay_amount,
                        purpose="Spieleabend" # <-- Hier geändert wie gewünscht
                    )
                    
                    col_idx = index % 3 
                    with cols[col_idx]:
                        st.image(qr_url, width=200)
                        st.markdown(f"**{player_name}**")
                        st.markdown(f"Schuldet: :red[**{pay_amount:.2f} €**]")

else:
    st.info("Datenbank leer.")
