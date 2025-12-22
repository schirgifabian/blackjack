import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pytz
import requests
import urllib.parse

# --- KONFIGURATION & KONSTANTEN ---
st.set_page_config(page_title="Blackjack Bank", page_icon="♠️", layout="centered")

# Liste der festen Spieler
VALID_PLAYERS = sorted(["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi"])

# --- CSS STYLING (MODERN LIGHT / FINANCE APP LOOK) ---
custom_css = """
<style>
    /* App Hintergrund */
    .stApp {
        background-color: #FAFAFA; /* Ganz leichtes Grau, angenehmer als reines Weiß */
    }
    
    /* Metrik-Boxen Styling (Karten-Look mit Schatten) */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #E5E7EB;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    
    /* Container Styling (Karten-Look) */
    div[data-testid="stVerticalBlock"] > div[style*="background-color"] {
        background-color: #FFFFFF;
        border-radius: 12px;
        border: 1px solid #E5E7EB;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }

    /* Überschriften */
    h1 {
        text-align: center;
        color: #111827;
        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
        font-weight: 800;
        letter-spacing: -1px;
    }
    
    h3 {
        font-weight: 600;
        color: #374151;
    }
    
    /* Der große Kontostand */
    .big-balance {
        font-size: 72px;
        font-weight: 800;
        text-align: center;
        margin-bottom: 10px;
        color: #111827; /* Fast Schwarz */
        letter-spacing: -2px;
    }
    
    .big-balance-neg {
        font-size: 72px;
        font-weight: 800;
        text-align: center;
        margin-bottom: 10px;
        color: #DC2626; /* Modernes Rot */
        letter-spacing: -2px;
    }

    /* Tabs modernisieren */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 8px 16px;
        background-color: #F3F4F6;
        border: none;
        color: #4B5563;
    }
    .stTabs [aria-selected="true"] {
        background-color: #000000 !important;
        color: #FFFFFF !important;
    }
    
    /* Hide MainMenu/Footer */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# --- HELPER FUNKTIONEN ---

def generate_epc_qr_url(name, iban, amount, purpose):
    """Generiert einen GiroCode (EPC-QR) Link."""
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

def berechne_netto(row):
    """Berechnet den Netto-Einfluss auf die Bank."""
    betrag = row["Betrag"]
    aktion = str(row["Aktion"]).lower()
    if ("ausgabe" in aktion or "auszahlung" in aktion) and betrag > 0:
        return -betrag
    return betrag

# --- HAUPTPROGRAMM START ---

st.markdown("<h1>♠️ Blackjack Bank</h1>", unsafe_allow_html=True)

# Verbindung zu Google Sheets
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

# --- DATEN VORBEREITEN ---
if not df.empty:
    df["Betrag"] = df["Betrag"].astype(str).str.replace(',', '.', regex=False)
    df["Betrag"] = pd.to_numeric(df["Betrag"], errors='coerce').fillna(0)
    
    df['Full_Date'] = pd.to_datetime(df['Datum'] + ' ' + df['Zeitstempel'].fillna('00:00'), format='%d.%m.%Y %H:%M', errors='coerce')
    df['Full_Date'] = df['Full_Date'].fillna(pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce'))

    df["Netto"] = df.apply(berechne_netto, axis=1)
    df = df.sort_values(by="Full_Date", ascending=True).reset_index(drop=True)
    kontostand = df["Netto"].sum()
else:
    kontostand = 0.0

# --- HEADER (KONTOSTAND) ---
balance_fmt = f"{kontostand:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
css_class = "big-balance" if kontostand >= 0 else "big-balance-neg"
st.markdown(f"<div class='{css_class}'>{balance_fmt}</div>", unsafe_allow_html=True)

col_ref1, col_ref2, col_ref3 = st.columns([1, 2, 1])
with col_ref2:
    if st.button("🔄 Aktualisieren", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.write("")

# --- 1. BUCHUNGSMASKE (Clean White Box) ---
with st.container(border=True):
    st.markdown("### ➕ Neue Buchung")
    
    col1, col2 = st.columns(2)
    with col1:
        buchung_namen = VALID_PLAYERS + ["Manuelle Ausgabe 📝"]
        auswahl_name = st.selectbox("Name", buchung_namen)
        
        final_name = auswahl_name
        if auswahl_name == "Manuelle Ausgabe 📝":
            custom_input = st.text_input("Zweck", placeholder="Pizza / Bier")
            if custom_input: final_name = custom_input

    with col2:
        betrag_input = st.number_input("Betrag €", min_value=0.00, value=10.00, step=5.00, format="%.2f")

    aktion_auswahl = st.radio("Aktion wählen", [
        "Einzahlung (Spieler kauft Chips) [+]", 
        "Auszahlung (Spieler tauscht zurück) [-]",
        "Bank Einnahme (Roulette/Sonstiges) [+]",
        "Bank Ausgabe (Ausgaben) [-]"
    ], horizontal=False)

    if st.button("Buchen", type="primary", use_container_width=True):
        typ_short = aktion_auswahl.split(" (")[0]
        tz = pytz.timezone('Europe/Berlin')
        now = datetime.now(tz)
        
        neuer_eintrag = pd.DataFrame([{
            "Datum": now.strftime("%d.%m.%Y"),
            "Zeit": now.strftime("%H:%M"),
            "Spieler": final_name,
            "Typ": typ_short,
            "Betrag": betrag_input
        }])
        
        try:
            df_raw = conn.read(worksheet="Buchungen", ttl=0)
            updated_df = pd.concat([df_raw, neuer_eintrag], ignore_index=True)
            conn.update(worksheet="Buchungen", data=updated_df)
            
            # Ntfy
            if "Bank" in typ_short:
                try:
                    ntfy_topic = "bj-boys-dashboard"
                    if "Einnahme" in typ_short:
                        title, tags, msg = "🤑 Bank Einnahme", "moneybag,up", f"Plus: {betrag_input:.2f} €\nGrund: {final_name}"
                    else:
                        title, tags, msg = "💸 Bank Ausgabe", "chart_with_downwards_trend,down", f"Minus: {betrag_input:.2f} €\nZweck: {final_name}"
                    requests.post(f"https://ntfy.sh/{ntfy_topic}", data=msg.encode('utf-8'), headers={"Title": title.encode('utf-8'), "Tags": tags})
                except: pass

            st.toast(f"Gebucht: {final_name} ({betrag_input:.2f}€)", icon="✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Fehler beim Speichern: {e}")

st.write("")

# --- ANALYSE BEREICH ---
if not df.empty:
    
    with st.expander("🔎 Filter Einstellungen", expanded=False):
        filter_col1, filter_col2 = st.columns([3, 1], vertical_alignment="bottom")
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        with filter_col1:
            options_list = ["Aktuelle Session", "Gesamt", "Dieser Monat", "Benutzerdefiniert"]
            try:
                zeitraum = st.pills("Zeitraum", options_list, default="Aktuelle Session")
            except AttributeError:
                zeitraum = st.selectbox("Zeitraum", options_list, index=0)

        with filter_col2:
            hide_bank = st.toggle("Bank ausblenden", value=False)

        # Filter
        df_stats = df.copy()
        if zeitraum == "Aktuelle Session":
            df_stats = df_stats[df_stats["Full_Date"].dt.date.isin([today, yesterday])]
        elif zeitraum == "Dieser Monat":
            df_stats = df_stats[(df_stats["Full_Date"].dt.month == today.month) & (df_stats["Full_Date"].dt.year == today.year)]
        elif zeitraum == "Benutzerdefiniert":
            c_date = st.container()
            d_range = c_date.date_input("Zeitraum wählen:", value=(today - timedelta(days=7), today), format="DD.MM.YYYY")
            if isinstance(d_range, tuple) and len(d_range) == 2:
                df_stats = df_stats[(df_stats["Full_Date"].dt.date >= d_range[0]) & (df_stats["Full_Date"].dt.date <= d_range[1])]

    # --- KPIs ---
    if hide_bank:
        df_display = df_stats[~df_stats["Aktion"].str.contains("Bank", case=False, na=False)]
    else:
        df_display = df_stats

    if not df_stats.empty:
        df_display = df_display.sort_values(by="Full_Date", ascending=True)
        df_display["Bankverlauf"] = df_display["Netto"].cumsum()

        delta_bank = df_display["Netto"].sum()
        chips_in = df_stats[df_stats["Aktion"].str.contains("Einzahlung", case=False, na=False)]["Betrag"].sum()
        chips_out = df_stats[df_stats["Aktion"].str.contains("Auszahlung", case=False, na=False)]["Betrag"].sum()

        st.markdown("### 📊 Statistik")
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Chips gekauft", f"{chips_in:,.0f} €")
        kpi2.metric("Chips ausgezahlt", f"{chips_out:,.0f} €")
        kpi3.metric("Bank Ergebnis", f"{delta_bank:,.2f} €", delta=delta_bank, delta_color="normal")

        # --- TABS ---
        st.write("")
        tab_bilanz, tab_verlauf, tab_list = st.tabs(["🏆 Rangliste", "📈 Verlauf", "📝 Liste"])

        df_players_only = df_stats[~df_stats["Aktion"].str.contains("Bank", case=False)].copy()
        if not df_players_only.empty:
            def get_profit(x):
                ein = x[x["Aktion"].str.contains("Einzahlung")]["Betrag"].sum()
                aus = x[x["Aktion"].str.contains("Auszahlung")]["Betrag"].sum()
                return aus - ein 

            lb = df_players_only.groupby("Name").apply(get_profit).reset_index(name="Profit").sort_values("Profit", ascending=False)
        else:
            lb = pd.DataFrame()

        with tab_bilanz:
            if not lb.empty:
                # Modernere Farben: Smaragdgrün für Plus, Ziegelrot für Minus
                lb["Color"] = lb["Profit"].apply(lambda x: '#059669' if x >= 0 else '#DC2626') 
                
                fig = px.bar(lb, x="Profit", y="Name", orientation='h', text="Profit", title=None)
                fig.update_traces(marker_color=lb["Color"], texttemplate='%{text:+.2f} €', textposition='outside')
                
                # Plotly White Template
                fig.update_layout(
                    template="plotly_white",
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=0, r=0, t=10, b=0),
                    xaxis_title="Gewinn (€)",
                    yaxis_title=None,
                    xaxis=dict(showgrid=True, gridcolor='#F3F4F6'),
                    font=dict(family="sans-serif", size=14, color="#1F2937")
                )
                st.plotly_chart(fig, use_container_width=True)
            else: 
                st.info("Keine Spielerdaten.")

        with tab_verlauf:
            if len(df_display) > 0:
                fig_line = px.line(df_display, x="Full_Date", y="Bankverlauf", markers=True)
                fig_line.update_traces(line_color='#000000', line_width=3, marker_size=6) # Schwarze Linie
                fig_line.update_layout(
                    template="plotly_white",
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=0, r=0, t=30, b=0),
                    yaxis_title="Kontostand (€)",
                    xaxis_title=None,
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=True, gridcolor='#F3F4F6'),
                    font=dict(family="sans-serif", color="#1F2937")
                )
                st.plotly_chart(fig_line, use_container_width=True)
            else: st.info("Zu wenig Daten.")

        with tab_list:
             st.dataframe(
                 df_display[["Datum", "Zeitstempel", "Name", "Aktion", "Betrag"]].sort_index(ascending=False), 
                 use_container_width=True, 
                 hide_index=True,
                 height=300
             )

    # --- PROFIL ---
    st.write("---")
    st.markdown("### 👤 Spieler-Profil")
    
    default_idx = 0
    if not lb.empty:
        top_winner = lb.iloc[0]["Name"]
        if top_winner in VALID_PLAYERS:
            default_idx = VALID_PLAYERS.index(top_winner)
            
    selected_player = st.selectbox("Wähle einen Spieler:", VALID_PLAYERS, index=default_idx)

    if selected_player:
        df_p = df[df["Name"] == selected_player].copy()
        
        if df_p.empty:
            st.info(f"Noch keine Buchungen für {selected_player}.")
        else:
            df_p["Player_Profit"] = -df_p["Netto"]
            df_p["Date_Only"] = df_p["Full_Date"].dt.date
            df_sessions = df_p.groupby("Date_Only")["Player_Profit"].sum().reset_index()
            lifetime_profit = df_p["Player_Profit"].sum()
            
            if not df_sessions.empty:
                best_session = df_sessions["Player_Profit"].max()
                worst_session = df_sessions["Player_Profit"].min()
            else:
                best_session, worst_session = 0, 0

            badges = []
            if lifetime_profit > 50: badges.append("🦈 Hai")
            if lifetime_profit < -50: badges.append("💸 Sponsor")

            with st.container(border=True):
                st.subheader(f"{selected_player} {' '.join(badges)}")
                col_p1, col_p2, col_p3 = st.columns(3)
                col_p1.metric("Gesamt", f"{lifetime_profit:+.2f} €", delta=lifetime_profit)
                col_p2.metric("Best", f"{best_session:+.2f} €")
                col_p3.metric("Worst", f"{worst_session:+.2f} €", delta_color="inverse")
                
                if not df_sessions.empty:
                    df_sessions["Color"] = df_sessions["Player_Profit"].apply(lambda x: '#059669' if x >= 0 else '#DC2626')
                    fig_p = px.bar(df_sessions, x="Date_Only", y="Player_Profit", text="Player_Profit")
                    fig_p.update_traces(marker_color=df_sessions["Color"], texttemplate='%{text:+.0f}', textposition='outside')
                    fig_p.update_layout(
                        template="plotly_white",
                        yaxis_title="Ergebnis €", 
                        xaxis_title=None, 
                        paper_bgcolor='rgba(0,0,0,0)', 
                        plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=0, r=0, t=10, b=0)
                    )
                    st.plotly_chart(fig_p, use_container_width=True)

    # --- ABRECHNUNG ---
    st.write("---")
    with st.expander("💸 Abrechnung (QR Codes)", expanded=False):
        secrets_iban = st.secrets.get("bank", {}).get("iban", "")
        secrets_owner = st.secrets.get("bank", {}).get("owner", "")
        
        if secrets_iban:
            iban_to_use = secrets_iban
            owner_to_use = secrets_owner
        else:
            c_iban, c_owner = st.columns(2)
            iban_to_use = c_iban.text_input("IBAN", value="")
            owner_to_use = c_owner.text_input("Inhaber", value="Blackjack Kasse")

        mask_date = df["Full_Date"].dt.date.isin([today, yesterday])
        mask_name = df["Name"].isin(VALID_PLAYERS)
        df_session = df[mask_date & mask_name].copy()

        if df_session.empty:
            st.info("Keine offenen Sessions.")
        else:
            session_balance = df_session.groupby("Name")["Netto"].sum().mul(-1)
            losers = session_balance[session_balance < -0.01]

            if losers.empty:
                st.success("Niemand hat Schulden!")
            else:
                st.write("Wer muss zahlen?")
                options = {f"{name} (Schuldet {abs(amount):.2f} €)": (name, abs(amount)) for name, amount in losers.items()}
                selected_key = st.selectbox("Verlierer auswählen:", options.keys())
                
                if selected_key and iban_to_use:
                    p_name, p_amount = options[selected_key]
                    qr_url = generate_epc_qr_url(owner_to_use, iban_to_use, p_amount, f"Blackjack {p_name}")
                    st.image(qr_url, caption=f"Scan mich ({p_name})", width=250)

else:
    st.warning("Datenbank ist leer.")
