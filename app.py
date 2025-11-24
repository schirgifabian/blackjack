import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import pytz
import requests
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
            div[data-testid="stCheckbox"] { padding-top: 1rem; } 
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- HELPER: GIROCODE GENERATOR ---
def generate_epc_qr_url(name, iban, amount, purpose):
    iban_clean = iban.replace(" ", "").upper()
    amount_str = f"EUR{amount:.2f}"
    # EPC-QR-Standard Formatierung
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

# --- HELPER: NETTO BERECHNUNG ---
def berechne_netto(row):
    betrag = row["Betrag"]
    aktion = str(row["Aktion"]).lower()
    # Ausgaben und Auszahlungen verringern den Bankbestand
    if ("ausgabe" in aktion or "auszahlung" in aktion) and betrag > 0:
        return -betrag
    return betrag

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
    # Bereinigung: Kommas zu Punkten, Zahlenformat
    df["Betrag"] = df["Betrag"].astype(str).str.replace(',', '.', regex=False)
    df["Betrag"] = pd.to_numeric(df["Betrag"], errors='coerce').fillna(0)
    
    # Datum parsen (Robustheit verbessert)
    df['Full_Date'] = pd.to_datetime(df['Datum'] + ' ' + df['Zeitstempel'].fillna('00:00'), format='%d.%m.%Y %H:%M', errors='coerce')
    # Fallback falls Zeit fehlt
    df['Full_Date'] = df['Full_Date'].fillna(pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce'))

    # Netto berechnen
    df["Netto"] = df.apply(berechne_netto, axis=1)
    
    # Sortieren
    df = df.sort_values(by="Full_Date", ascending=True).reset_index(drop=True)
    kontostand = df["Netto"].sum()
else:
    kontostand = 0.0

# --- HEADER (KONTOSTAND) ---
color = "black" if kontostand >= 0 else "red"
# Großes Display des Kontostands
st.markdown(f"<h1 style='text-align: center; font-size: 80px; color: {color};'>{kontostand:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".") + "</h1>", unsafe_allow_html=True)

# Refresh Button
col_btn1, col_btn2 = st.columns([1, 4]) 
if st.button("🔄", help="Aktualisieren", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.divider()

# --- BUCHEN (HAUPTFUNKTION) ---
with st.expander("➕ Neue Buchung", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        namen_liste = ["Tobi", "Alex", "Dani", "Fabi", "Schirgi", "Lüxn", "Domi", "Manuelle Ausgabe 📝"]
        auswahl_name = st.selectbox("Name", namen_liste)
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
            
            # Ntfy Logik (Benachrichtigung aufs Handy)
            if "Bank" in typ_short:
                try:
                    ntfy_topic = "bj-boys-dashboard"
                    if "Einnahme" in typ_short:
                        title, tags, msg = "🤑 Bank Einnahme", "moneybag,up", f"Plus: {betrag_input:.2f} €\nGrund: {final_name}"
                    else:
                        title, tags, msg = "💸 Bank Ausgabe", "chart_with_downwards_trend,down", f"Minus: {betrag_input:.2f} €\nZweck: {final_name}"
                    requests.post(f"https://ntfy.sh/{ntfy_topic}", data=msg.encode('utf-8'), headers={"Title": title.encode('utf-8'), "Tags": tags})
                except: pass

            st.success(f"Gebucht: {final_name}")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Fehler: {e}")

st.divider()

# --- ANALYSE & STATISTIK ---
st.subheader("📊 Statistik")

if not df.empty:
    # --- FILTER BEREICH ---
    filter_col1, filter_col2 = st.columns([3, 1], vertical_alignment="bottom")

    with filter_col1:
        # "Benutzerdefiniert" zu den Optionen hinzufügen
        options_list = ["Aktuelle Session", "Gesamt", "Dieser Monat", "Benutzerdefiniert"]
        try:
            zeitraum = st.pills("Zeitraum", options_list, default="Aktuelle Session")
        except AttributeError:
            zeitraum = st.selectbox("Zeitraum", options_list, index=0)

    with filter_col2:
        hide_bank = st.toggle("Bank ausblenden", value=False)

    df_stats = df.copy()
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    # --- DATUMS LOGIK ---
    if zeitraum == "Aktuelle Session":
        df_stats = df_stats[df_stats["Full_Date"].dt.date.isin([today, yesterday])]
    
    elif zeitraum == "Dieser Monat":
        df_stats = df_stats[(df_stats["Full_Date"].dt.month == today.month) & (df_stats["Full_Date"].dt.year == today.year)]
    
    elif zeitraum == "Benutzerdefiniert":
        # Datepicker erscheint nur, wenn "Benutzerdefiniert" gewählt ist
        c_date = st.container()
        d_range = c_date.date_input(
            "Wähle den Zeitraum:",
            value=(today - timedelta(days=7), today), # Default: Letzte 7 Tage
            format="DD.MM.YYYY"
        )
        
        # Logik um sicherzustellen, dass Start & Ende vorhanden sind
        if isinstance(d_range, tuple) and len(d_range) == 2:
            start_date, end_date = d_range
            df_stats = df_stats[
                (df_stats["Full_Date"].dt.date >= start_date) & 
                (df_stats["Full_Date"].dt.date <= end_date)
            ]
        elif isinstance(d_range, tuple) and len(d_range) == 1:
            # Falls User erst das Startdatum geklickt hat
            start_date = d_range[0]
            df_stats = df_stats[df_stats["Full_Date"].dt.date == start_date]

    # 2. Bank Filter (Für Anzeige im Graphen/Liste)
    if hide_bank:
        df_display = df_stats[~df_stats["Aktion"].str.contains("Bank", case=False, na=False)]
    else:
        df_display = df_stats

    if df_stats.empty:
        st.info(f"Keine Daten für Filter: '{zeitraum}'.")
    else:
        # Verlauf NEU berechnen für Anzeige
        df_display = df_display.sort_values(by="Full_Date", ascending=True)
        df_display["Bankverlauf"] = df_display["Netto"].cumsum()

        # KPI BERECHNUNG
        delta_bank = df_display["Netto"].sum()
        chips_in = df_stats[df_stats["Aktion"].str.contains("Einzahlung", case=False, na=False)]["Betrag"].sum()
        chips_out = df_stats[df_stats["Aktion"].str.contains("Auszahlung", case=False, na=False)]["Betrag"].sum()

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Chips gekauft", f"{chips_in:,.0f} €")
        kpi2.metric("Chips ausgezahlt", f"{chips_out:,.0f} €")
        kpi3.metric("Bank Gewinn/Verlust", f"{delta_bank:,.2f} €", delta_color="normal")

        tab_bilanz, tab_verlauf, tab_list = st.tabs(["🏆 Spieler", "📈 Bank-Verlauf", "📝 Liste"])

        # Spieler Profit Berechnung (unabhängig vom Bank-Filter)
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
                lb["Color"] = lb["Profit"].apply(lambda x: '#2E7D32' if x >= 0 else '#C62828')
                fig = px.bar(lb, x="Profit", y="Name", orientation='h', text="Profit", title="Gewinn/Verlust pro Spieler")
                fig.update_traces(marker_color=lb["Color"], texttemplate='%{text:+.2f} €', textposition='outside')
                fig.update_layout(xaxis_title="Gewinn", paper_bgcolor='white', plot_bgcolor='white', font_color='black')
                st.plotly_chart(fig, use_container_width=True)
            else: 
                st.info("Keine Spielerdaten im gewählten Zeitraum.")

        with tab_verlauf:
            if len(df_display) > 0:
                fig_line = px.line(df_display, x="Full_Date", y="Bankverlauf", 
                                   title="Entwicklung Bankbestand",
                                   line_shape='hv')
                fig_line.update_layout(paper_bgcolor='white', plot_bgcolor='white', font_color='black', yaxis_title="Kontostand €")
                fig_line.update_traces(line_color='black', line_width=3)
                st.plotly_chart(fig_line, use_container_width=True)
            else: st.info("Zu wenig Daten.")

        with tab_list:
             st.dataframe(df_display[["Datum", "Zeitstempel", "Name", "Aktion", "Betrag"]].sort_index(ascending=False), use_container_width=True, hide_index=True)
        # --- FEATURE: SPIELER-DETAILSEITE & HALL OF FAME ---
        st.markdown("### 👤 Spieler-Profil & Hall of Fame")
        
        # Namen aus der Datenbank holen
        all_names_in_db = df["Name"].unique().tolist()

        # OPTION A: Blacklist (Alles rausfiltern, was kein Spieler ist)
        # Hier trägst du Wörter ein, die ignoriert werden sollen:
        ignored_names = ["Mischmaschine", "Bank", "Kasse", "Initial", "Admin"]
        
        all_players = sorted([
            name for name in all_names_in_db 
            if name not in ignored_names and name is not None
        ])
        
        # OPTION B: Whitelist (Falls du NUR feste Namen zulassen willst)
        # Wenn du Option B nutzen willst, entferne das # vor der nächsten Zeile:
        # all_players = sorted(["Max", "Anna", "Tom", "Lisa"]) # <-- Hier deine 7 Namen eintragen

        # UI: Dropdown zur Auswahl
        default_idx = 0
        
        # Wir versuchen, den aktuellen Top-Gewinner vorzuwählen
        if not lb.empty:
            # Suche den ersten Namen aus der Rangliste, der auch in unserer "Echten Spieler"-Liste ist
            for _, row in lb.iterrows():
                potential_winner = row["Name"]
                if potential_winner in all_players:
                    default_idx = all_players.index(potential_winner)
                    break
                
        selected_player = st.selectbox("Wähle einen Spieler für Details:", all_players, index=default_idx)

        if selected_player:
            # Daten filtern
            # WICHTIG: Wir drehen das Vorzeichen um! 
            # In der Bank-DB ist Einzahlung (+) gut für Bank, schlecht für Spieler-Cashflow.
            # Auszahlung (-) ist schlecht für Bank, gut für Spieler-Cashflow.
            # Daher: Spieler Profit = -1 * Bank Netto
            df_p = df[df["Name"] == selected_player].copy()
            df_p["Player_Profit"] = -df_p["Netto"]
            
            # 1. Sessions aggregieren (Pro Datum)
            # Wir summieren alles pro Tag (Einzahlungen vs Auszahlungen)
            df_sessions = df_p.groupby("Datum")["Player_Profit"].sum().reset_index()
            # Datum konvertieren für Sortierung
            df_sessions["Date_Obj"] = pd.to_datetime(df_sessions["Datum"], format="%d.%m.%Y")
            df_sessions = df_sessions.sort_values("Date_Obj")
            
            # 2. Kennzahlen berechnen
            lifetime_profit = df_sessions["Player_Profit"].sum()
            
            # Heute
            today_str = datetime.now().strftime("%d.%m.%Y")
            profit_today = df_sessions[df_sessions["Datum"] == today_str]["Player_Profit"].sum()
            
            # Beste / Schlechteste Session
            if not df_sessions.empty:
                best_session = df_sessions["Player_Profit"].max()
                worst_session = df_sessions["Player_Profit"].min()
                best_date = df_sessions.loc[df_sessions["Player_Profit"].idxmax(), "Datum"]
                worst_date = df_sessions.loc[df_sessions["Player_Profit"].idxmin(), "Datum"]
                
                # Letzte 5 Abende (exklusive heute, oder einfach letzte 5 Einträge)
                last_5_sum = df_sessions.tail(5)["Player_Profit"].sum()
            else:
                best_session = 0
                worst_session = 0
                best_date = "-"
                worst_date = "-"
                last_5_sum = 0

            # 3. BADGES VERGEBEN 🏅
            badges = []
            if lifetime_profit > 0: badges.append("🤑 Im Plus")
            if lifetime_profit < -200: badges.append("💸 Sponsor")
            if best_session > 50: badges.append("🚀 To The Moon")
            if worst_session < -50: badges.append("📉 Rekt")
            if len(df_sessions) > 10: badges.append("👴 Stammgast")
            # "Bankkiller": Hat mehr als 20% des aktuellen Bankbestands (falls Bank positiv) "gestohlen"
            if kontostand > 0 and lifetime_profit > (kontostand * 0.2): badges.append("🦈 Bank-Hai")
            if profit_today > 0: badges.append("🔥 Hot Streak")

            # --- ANZEIGE ---
            
            # Badges anzeigen
            if badges:
                st.write(" ".join([f"`{b}`" for b in badges]))
            
            # Metriken Reihe 1
            m1, m2, m3 = st.columns(3)
            m1.metric("Lifetime Profit", f"{lifetime_profit:+.2f} €", delta_color="normal")
            m2.metric("Heute", f"{profit_today:+.2f} €")
            m3.metric("Letzte 5 Abende", f"{last_5_sum:+.2f} €")
            
            # Metriken Reihe 2 (Rekorde)
            r1, r2 = st.columns(2)
            r1.metric("Bester Abend", f"{best_session:+.2f} €", help=f"Am {best_date}")
            r2.metric("Schlimmster Abend", f"{worst_session:+.2f} €", help=f"Am {worst_date}")
            
            # Graph: Timeline
            st.caption("Verlauf der Abende (Gewinn/Verlust pro Session)")
            if not df_sessions.empty:
                df_sessions["Color"] = df_sessions["Player_Profit"].apply(lambda x: '#66BB6A' if x >= 0 else '#EF5350')
                fig_p = px.bar(df_sessions, x="Datum", y="Player_Profit", 
                               title=f"Verlauf: {selected_player}", text="Player_Profit")
                fig_p.update_traces(marker_color=df_sessions["Color"], texttemplate='%{text:+.0f}', textposition='outside')
                fig_p.update_layout(yaxis_title="Gewinn €", paper_bgcolor='white', plot_bgcolor='white', font_color='black')
                st.plotly_chart(fig_p, use_container_width=True)
            else:
                st.info("Noch keine abgeschlossenen Sessions.")


        # --- TAGESABSCHLUSS & QR CODES ---
        st.markdown("---")
        with st.expander("💸 Tagesabschluss & Abrechnung", expanded=False):
            
            # Daten aus Secrets laden
            secrets_iban = st.secrets.get("bank", {}).get("iban", "")
            secrets_owner = st.secrets.get("bank", {}).get("owner", "")
            
            if secrets_iban:
                iban_to_use = secrets_iban
                owner_to_use = secrets_owner
                st.success(f"Empfängerkonto geladen: {owner_to_use}")
            else:
                st.warning("Keine Bankdaten in secrets.toml.")
                c_iban, c_owner = st.columns(2)
                iban_to_use = c_iban.text_input("IBAN", value="")
                owner_to_use = c_owner.text_input("Inhaber", value="Blackjack Kasse")

            # Nur Verlierer müssen zahlen
            if iban_to_use and not lb.empty:
                losers = lb[lb["Profit"] < 0].copy()
                
                if losers.empty:
                    st.balloons()
                    st.success("Keine offenen Schulden! 🎉")
                else:
                    st.write("Wähle die Person aus, die bezahlen möchte:")
                    
                    # Dropdown Menü für Spieler
                    # Key ist der angezeigte Text, Value ist die Zeile mit den Daten
                    options = {f"{row['Name']} (Schuldet {abs(row['Profit']):.2f} €)": row for _, row in losers.iterrows()}
                    
                    selected_option = st.selectbox("Zahlungspflichtiger Spieler:", options.keys())
                    
                    if selected_option:
                        selected_row = options[selected_option]
                        pay_amount = abs(selected_row["Profit"])
                        player_name = selected_row["Name"]
                        
                        qr_url = generate_epc_qr_url(
                            name=owner_to_use,
                            iban=iban_to_use,
                            amount=pay_amount,
                            purpose="Spieleabend"
                        )
                        
                        # Layout für den QR Code
                        col_spacer1, col_qr, col_spacer2 = st.columns([1, 2, 1])
                        with col_qr:
                            st.image(qr_url, caption=f"GiroCode für {player_name}", width=300)
                            st.info(f"📱 Bitte Banking-App öffnen und scannen.\nBetrag: {pay_amount:.2f} €")
else:
    st.info("Datenbank leer. Buche etwas, um zu starten!")
