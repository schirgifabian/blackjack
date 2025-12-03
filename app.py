import streamlit as st
import extra_streamlit_components as stx   
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
import datetime                            
import time                                
import pytz
import requests
import urllib.parse

# --- KONFIGURATION & KONSTANTEN ---
st.set_page_config(page_title="Blackjack Bank", page_icon="♠️", layout="centered")

# Liste der festen Spieler (Wichtig für Filter und Dropdowns)
VALID_PLAYERS = sorted(["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi"])

# --- CSS STYLING ---
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stApp { background-color: white; }
            div[data-testid="stDataFrame"] { font-family: monospace; }
            div[data-testid="stMetricValue"] { font-size: 24px; }
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

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
    # Ausgaben und Auszahlungen verringern den Bankbestand
    if ("ausgabe" in aktion or "auszahlung" in aktion) and betrag > 0:
        return -betrag
    return betrag

# --- HAUPTPROGRAMM START ---

st.title("♠️ Blackjack Bank")

# Verbindung zu Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- DATEN LADEN ---
try:
    df = conn.read(worksheet="Buchungen", ttl=0)
    
    # Spalten mappen und sicherstellen
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
    # Bereinigung: Kommas zu Punkten, Zahlenformat
    df["Betrag"] = df["Betrag"].astype(str).str.replace(',', '.', regex=False)
    df["Betrag"] = pd.to_numeric(df["Betrag"], errors='coerce').fillna(0)
    
    # Datum parsen (Robustheit verbessert)
    df['Full_Date'] = pd.to_datetime(df['Datum'] + ' ' + df['Zeitstempel'].fillna('00:00'), format='%d.%m.%Y %H:%M', errors='coerce')
    # Fallback falls Zeit fehlt
    df['Full_Date'] = df['Full_Date'].fillna(pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce'))

    # Netto berechnen (Bank-Sicht)
    df["Netto"] = df.apply(berechne_netto, axis=1)
    
    # Sortieren für Verlauf
    df = df.sort_values(by="Full_Date", ascending=True).reset_index(drop=True)
    kontostand = df["Netto"].sum()
else:
    kontostand = 0.0

# --- HEADER (KONTOSTAND) ---
color = "black" if kontostand >= 0 else "red"
st.markdown(f"<h1 style='text-align: center; font-size: 80px; color: {color};'>{kontostand:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".") + "</h1>", unsafe_allow_html=True)

# Refresh Button
if st.button("🔄", help="Aktualisieren", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.divider()

# --- 1. BUCHUNGSMASKE ---
with st.expander("➕ Neue Buchung", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        # Dropdown mit den definierten Spielern + Option für Manuell
        buchung_namen = VALID_PLAYERS + ["Manuelle Ausgabe 📝"]
        auswahl_name = st.selectbox("Name", buchung_namen)
        
        final_name = auswahl_name
        if auswahl_name == "Manuelle Ausgabe 📝":
            custom_input = st.text_input("Zweck", placeholder="Pizza / Bier")
            if custom_input: final_name = custom_input

    with col2:
        betrag_input = st.number_input("Betrag €", min_value=0.00, value=10.00, step=5.00, format="%.2f")

    aktion_auswahl = st.radio("Typ", [
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
            "Spieler": final_name,
            "Typ": typ_short,
            "Betrag": betrag_input
        }])
        
        try:
            # Daten neu laden um Konflikte zu vermeiden
            df_raw = conn.read(worksheet="Buchungen", ttl=0)
            updated_df = pd.concat([df_raw, neuer_eintrag], ignore_index=True)
            conn.update(worksheet="Buchungen", data=updated_df)
            
            # Ntfy Benachrichtigung (Optional)
            if "Bank" in typ_short:
                try:
                    ntfy_topic = "bj-boys-dashboard"
                    if "Einnahme" in typ_short:
                        title, tags, msg = "🤑 Bank Einnahme", "moneybag,up", f"Plus: {betrag_input:.2f} €\nGrund: {final_name}"
                    else:
                        title, tags, msg = "💸 Bank Ausgabe", "chart_with_downwards_trend,down", f"Minus: {betrag_input:.2f} €\nZweck: {final_name}"
                    requests.post(f"https://ntfy.sh/{ntfy_topic}", data=msg.encode('utf-8'), headers={"Title": title.encode('utf-8'), "Tags": tags})
                except: pass

            st.success(f"Gebucht: {final_name} ({betrag_input:.2f}€)")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Fehler beim Speichern: {e}")

st.divider()

# --- ANALYSE BEREICH (Wird nur angezeigt, wenn Daten da sind) ---
if not df.empty:
    st.subheader("📊 Statistik")
    
    # --- FILTER ---
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

    df_stats = df.copy()

    # --- FILTER LOGIK ---
    if zeitraum == "Aktuelle Session":
        df_stats = df_stats[df_stats["Full_Date"].dt.date.isin([today, yesterday])]
    
    elif zeitraum == "Dieser Monat":
        df_stats = df_stats[(df_stats["Full_Date"].dt.month == today.month) & (df_stats["Full_Date"].dt.year == today.year)]
    
    elif zeitraum == "Benutzerdefiniert":
        c_date = st.container()
        d_range = c_date.date_input("Wähle den Zeitraum:", value=(today - timedelta(days=7), today), format="DD.MM.YYYY")
        if isinstance(d_range, tuple) and len(d_range) == 2:
            df_stats = df_stats[(df_stats["Full_Date"].dt.date >= d_range[0]) & (df_stats["Full_Date"].dt.date <= d_range[1])]
        elif isinstance(d_range, tuple) and len(d_range) == 1:
            df_stats = df_stats[df_stats["Full_Date"].dt.date == d_range[0]]

    # Anzeige-DF vorbereiten
    if hide_bank:
        df_display = df_stats[~df_stats["Aktion"].str.contains("Bank", case=False, na=False)]
    else:
        df_display = df_stats

    if df_stats.empty:
        st.info(f"Keine Daten für Filter: '{zeitraum}'.")
    else:
        # --- KPIs & TABS ---
        df_display = df_display.sort_values(by="Full_Date", ascending=True)
        df_display["Bankverlauf"] = df_display["Netto"].cumsum()

        delta_bank = df_display["Netto"].sum()
        chips_in = df_stats[df_stats["Aktion"].str.contains("Einzahlung", case=False, na=False)]["Betrag"].sum()
        chips_out = df_stats[df_stats["Aktion"].str.contains("Auszahlung", case=False, na=False)]["Betrag"].sum()

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Chips gekauft", f"{chips_in:,.0f} €")
        kpi2.metric("Chips ausgezahlt", f"{chips_out:,.0f} €")
        kpi3.metric("Bank Gewinn/Verlust", f"{delta_bank:,.2f} €", delta_color="normal")

        tab_bilanz, tab_verlauf, tab_list = st.tabs(["🏆 Spieler", "📈 Bank-Verlauf", "📝 Liste"])

        # Leaderboard (immer ohne Bank-Aktionen)
        df_players_only = df_stats[~df_stats["Aktion"].str.contains("Bank", case=False)].copy()

        if not df_players_only.empty:
            def get_profit(x):
                ein = x[x["Aktion"].str.contains("Einzahlung")]["Betrag"].sum()
                aus = x[x["Aktion"].str.contains("Auszahlung")]["Betrag"].sum()
                return aus - ein # Positiv = Spieler hat gewonnen

            lb = df_players_only.groupby("Name").apply(get_profit).reset_index(name="Profit").sort_values("Profit", ascending=False)
        else:
            lb = pd.DataFrame()

        with tab_bilanz:
            if not lb.empty:
                lb["Color"] = lb["Profit"].apply(lambda x: '#2E7D32' if x >= 0 else '#C62828')
                fig = px.bar(lb, x="Profit", y="Name", orientation='h', text="Profit", title="Gewinn/Verlust pro Spieler")
                fig.update_traces(marker_color=lb["Color"], texttemplate='%{text:+.2f} €', textposition='outside')
                fig.update_layout(xaxis_title="Gewinn", paper_bgcolor='white', plot_bgcolor='white', font_color='black')
                st.plotly_chart(fig, use_container_width=True)
            else: 
                st.info("Keine Spielerdaten im gewählten Zeitraum.")

        with tab_verlauf:
            if len(df_display) > 0:
                fig_line = px.line(df_display, x="Full_Date", y="Bankverlauf", title="Entwicklung Bankbestand", line_shape='hv')
                fig_line.update_layout(paper_bgcolor='white', plot_bgcolor='white', font_color='black', yaxis_title="Kontostand €")
                fig_line.update_traces(line_color='black', line_width=3)
                st.plotly_chart(fig_line, use_container_width=True)
            else: st.info("Zu wenig Daten.")

        with tab_list:
             st.dataframe(df_display[["Datum", "Zeitstempel", "Name", "Aktion", "Betrag"]].sort_index(ascending=False), use_container_width=True, hide_index=True)

    # --- HALL OF FAME / PROFIL ---
    st.markdown("### 👤 Spieler-Profil & Hall of Fame")
    
    # Auswahl-Logik: Versuche den Top-Gewinner vorzuwählen
    default_idx = 0
    if not lb.empty:
        top_winner = lb.iloc[0]["Name"]
        if top_winner in VALID_PLAYERS:
            default_idx = VALID_PLAYERS.index(top_winner)
            
    selected_player = st.selectbox("Wähle einen Spieler für Details:", VALID_PLAYERS, index=default_idx)

    if selected_player:
        df_p = df[df["Name"] == selected_player].copy()
        
        if df_p.empty:
            st.info(f"Noch keine Buchungen für {selected_player} gefunden.")
        else:
            # Profit aus Spielersicht: -Netto (weil Netto = Banksicht)
            df_p["Player_Profit"] = -df_p["Netto"]
            df_p["Date_Only"] = df_p["Full_Date"].dt.date
            
            # Gruppieren pro Abend (Session)
            df_sessions = df_p.groupby("Date_Only")["Player_Profit"].sum().reset_index()
            
            lifetime_profit = df_p["Player_Profit"].sum()
            
            if not df_sessions.empty:
                best_session = df_sessions["Player_Profit"].max()
                worst_session = df_sessions["Player_Profit"].min()
                best_date = df_sessions.loc[df_sessions["Player_Profit"].idxmax(), "Date_Only"].strftime("%d.%m.%y")
                worst_date = df_sessions.loc[df_sessions["Player_Profit"].idxmin(), "Date_Only"].strftime("%d.%m.%y")
            else:
                best_session, worst_session = 0, 0
                best_date, worst_date = "-", "-"

            # Badges
            badges = []
            if lifetime_profit > 50: badges.append("🦈 Hai")
            if lifetime_profit < -50: badges.append("💸 Sponsor")
            if best_session > 100: badges.append("🚀 Moon")
            if worst_session < -100: badges.append("📉 Rekt")

            st.markdown(f"**{selected_player}** {' '.join(badges)}")
            
            col_p1, col_p2, col_p3 = st.columns(3)
            col_p1.metric("Lifetime", f"{lifetime_profit:+.2f} €")
            col_p2.metric("Best", f"{best_session:+.2f} €", help=f"Datum: {best_date}")
            col_p3.metric("Worst", f"{worst_session:+.2f} €", help=f"Datum: {worst_date}")
            
            if not df_sessions.empty:
                df_sessions["Color"] = df_sessions["Player_Profit"].apply(lambda x: '#66BB6A' if x >= 0 else '#EF5350')
                fig_p = px.bar(df_sessions, x="Date_Only", y="Player_Profit", text="Player_Profit")
                fig_p.update_traces(marker_color=df_sessions["Color"], texttemplate='%{text:+.0f}', textposition='outside')
                fig_p.update_layout(yaxis_title="Ergebnis €", xaxis_title="", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_p, use_container_width=True)

    # --- TAGESABSCHLUSS (QR CODES) ---
    st.markdown("---")
    with st.expander("💸 Tagesabschluss & Abrechnung (Heute/Gestern)", expanded=False):
        
        # 1. Bankdaten laden
        secrets_iban = st.secrets.get("bank", {}).get("iban", "")
        secrets_owner = st.secrets.get("bank", {}).get("owner", "")
        
        if secrets_iban:
            iban_to_use = secrets_iban
            owner_to_use = secrets_owner
            st.success(f"Konto geladen: {owner_to_use}")
        else:
            st.warning("Keine Bankdaten in secrets.toml.")
            c_iban, c_owner = st.columns(2)
            iban_to_use = c_iban.text_input("IBAN", value="")
            owner_to_use = c_owner.text_input("Inhaber", value="Blackjack Kasse")

        # 2. Filter: Nur Heute & Gestern UND nur gültige Spieler
        mask_date = df["Full_Date"].dt.date.isin([today, yesterday])
        mask_name = df["Name"].isin(VALID_PLAYERS)
        
        df_session = df[mask_date & mask_name].copy()

        if df_session.empty:
            st.info("Keine offenen Sessions für Heute oder Gestern.")
        else:
            # Saldo berechnen: Einzahlung (+Netto) ist schlecht für Spieler -> mal -1
            session_balance = df_session.groupby("Name")["Netto"].sum().mul(-1)
            
            # Nur Verlierer (Saldo < 0) müssen zahlen
            losers = session_balance[session_balance < -0.01]

            if losers.empty:
                st.balloons()
                st.success("Niemand hat Schulden! 🎉")
            else:
                st.write("Wähle, wer bezahlen will:")
                
                # Dropdown: Name + Betrag
                options = {f"{name} (Schuldet {abs(amount):.2f} €)": (name, abs(amount)) for name, amount in losers.items()}
                selected_key = st.selectbox("Zahlungspflichtiger:", options.keys())
                
                if selected_key and iban_to_use:
                    p_name, p_amount = options[selected_key]
                    
                    qr_url = generate_epc_qr_url(owner_to_use, iban_to_use, p_amount, f"Blackjack {p_name}")
                    
                    col_spacer, col_qr, col_spacer2 = st.columns([1, 2, 1])
                    with col_qr:
                        st.image(qr_url, caption=f"Scan mich ({p_name})", width=300)
                        st.info(f"📱 {p_amount:.2f} € an {owner_to_use}")

else:
    # Falls DB komplett leer ist
    st.info("Datenbank ist leer. Buche etwas, um zu starten!")
