import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import urllib.parse

# --- KONFIGURATION ---
st.set_page_config(page_title="Blackjack Bank", page_icon="♠️", layout="centered")

# --- CSS STYLING ---
st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    div[data-testid="stMetricValue"] { font-size: 24px; }
    
    /* Badges */
    .badge {
        display: inline-block;
        padding: 0.25em 0.4em;
        font-size: 75%;
        font-weight: 700;
        line-height: 1;
        text-align: center;
        white-space: nowrap;
        vertical-align: baseline;
        border-radius: 0.25rem;
        color: #fff;
        margin-right: 5px;
        margin-bottom: 5px;
    }
    .bg-success { background-color: #28a745; } /* Grün */
    .bg-danger { background-color: #dc3545; }  /* Rot */
    .bg-warning { background-color: #ffc107; color: #212529; } /* Gelb */
    .bg-info { background-color: #17a2b8; }    /* Blau */
    .bg-dark { background-color: #343a40; }    /* Grau */
    </style>
""", unsafe_allow_html=True)

# --- HELPER FUNKTIONEN ---
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

def berechne_netto(row):
    betrag = row["Betrag"]
    aktion = str(row["Aktion"]).lower()
    if ("ausgabe" in aktion or "auszahlung" in aktion) and betrag > 0:
        return -betrag
    return betrag

def get_current_date_str():
    return datetime.now().strftime("%d.%m.%Y")

def get_current_time_str():
    return datetime.now().strftime("%H:%M")

# --- DATEN LADEN ---
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    df = conn.read(worksheet="Buchungen", ttl=0)
    
    # Mapping alter Spaltennamen falls nötig
    rename_map = {"Spieler": "Name", "Typ": "Aktion", "Zeit": "Zeitstempel"}
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    
    # Sicherstellen, dass Session_ID existiert (Migration für alte Daten)
    if "Session_ID" not in df.columns:
        df["Session_ID"] = "Legacy_Archiv" 
    
    # Spalten initialisieren falls leer
    expected_cols = ["Datum", "Name", "Aktion", "Betrag", "Zeitstempel", "Session_ID"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None
            
except Exception:
    df = pd.DataFrame(columns=["Datum", "Zeitstempel", "Name", "Aktion", "Betrag", "Session_ID"])

# --- DATEN VORBEREITUNG ---
if not df.empty:
    # Zahlenformatierung
    df["Betrag"] = df["Betrag"].astype(str).str.replace(',', '.', regex=False)
    df["Betrag"] = pd.to_numeric(df["Betrag"], errors='coerce').fillna(0)
    
    # Datum basteln für Sortierung
    df['Full_Date'] = pd.to_datetime(df['Datum'] + ' ' + df['Zeitstempel'].fillna('00:00'), format='%d.%m.%Y %H:%M', errors='coerce')
    df['Full_Date'] = df['Full_Date'].fillna(pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce'))
    
    # Netto
    df["Netto"] = df.apply(berechne_netto, axis=1)
    
    # Sortierung: Neueste zuerst für interne Verarbeitung oft praktisch, aber für Charts chronologisch
    df = df.sort_values(by="Full_Date", ascending=True).reset_index(drop=True)

# --- SESSION STATE INITIALISIERUNG ---
# Wir ermitteln die aktuellste Session aus den Daten, falls noch keine im State ist
if "active_session" not in st.session_state:
    if not df.empty:
        last_session = df.iloc[-1]["Session_ID"]
        st.session_state.active_session = last_session
    else:
        st.session_state.active_session = f"Session_{datetime.now().strftime('%Y-%m-%d')}"

# --- SIDEBAR / HEADER STEUERUNG ---
st.title("♠️ Blackjack Bank")

col_control1, col_control2 = st.columns([2, 1])

with col_control1:
    # Dropdown für Ansicht
    unique_sessions = list(df["Session_ID"].unique()) if not df.empty else []
    # Sortieren: Legacy zuerst, dann chronologisch, wir drehen es um (neueste oben)
    unique_sessions = sorted([s for s in unique_sessions if s is not None], reverse=True)
    
    options = ["Alle Sessions"] + unique_sessions
    
    # Versuchen den aktuellen State im Dropdown zu matchen
    current_idx = 0
    if st.session_state.active_session in options:
        current_idx = options.index(st.session_state.active_session)
        
    view_mode = st.selectbox("🔍 Ansicht / Filter:", options, index=current_idx)

with col_control2:
    st.write("") # Spacer
    if st.button("🆕 Neue Session", use_container_width=True, help="Startet einen neuen Spielabend"):
        new_session_id = f"Session_{datetime.now().strftime('%Y-%m-%d')}"
        st.session_state.active_session = new_session_id
        st.success(f"Gestartet: {new_session_id}")
        st.rerun()

# Daten filtern basierend auf Auswahl
if view_mode == "Alle Sessions":
    df_display = df.copy()
    display_title = "Gesamtübersicht (Lifetime)"
else:
    df_display = df[df["Session_ID"] == view_mode].copy()
    display_title = f"Übersicht: {view_mode}"
    # Wenn User eine Session auswählt, setzen wir diese auch als aktiv für neue Buchungen (optional)
    st.session_state.active_session = view_mode

# --- TABS ---
tab_game, tab_player, tab_history, tab_booking = st.tabs(["🎲 Spieltisch", "👤 Spieler-Details", "📜 History", "✍️ Buchen"])

# ==========================================
# TAB 1: SPIELTISCH (DASHBOARD)
# ==========================================
with tab_game:
    st.subheader(display_title)
    
    if df_display.empty:
        st.info("Keine Daten für diese Auswahl.")
    else:
        # METRICS
        total_bank = df_display["Netto"].sum()
        chips_in = df_display[df_display["Aktion"].str.contains("Einzahlung", case=False, na=False)]["Betrag"].sum()
        chips_out = df_display[df_display["Aktion"].str.contains("Auszahlung", case=False, na=False)]["Betrag"].sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Bank Ergebnis", f"{total_bank:,.2f} €", delta_color="normal")
        c2.metric("Chips gekauft", f"{chips_in:,.0f} €")
        c3.metric("Chips ausgezahlt", f"{chips_out:,.0f} €")

        st.markdown("---")
        
        # RANG LISTE (Nur Spieler, keine Bank-Aktionen)
        df_players_only = df_display[~df_display["Aktion"].str.contains("Bank", case=False, na=False)]
        
        if not df_players_only.empty:
            # Group by Name
            leaderboard = df_players_only.groupby("Name")["Netto"].sum().reset_index()
            leaderboard = leaderboard.rename(columns={"Netto": "Profit"})
            leaderboard = leaderboard.sort_values("Profit", ascending=False)
            
            leaderboard["Color"] = leaderboard["Profit"].apply(lambda x: '#28a745' if x >= 0 else '#dc3545')

            fig = px.bar(leaderboard, x="Profit", y="Name", orientation='h', text="Profit", 
                         title=f"Gewinner & Verlierer ({view_mode if view_mode != 'Alle Sessions' else 'Gesamt'})")
            fig.update_traces(marker_color=leaderboard["Color"], texttemplate='%{text:+.2f} €', textposition='outside')
            fig.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="Profit (€)")
            st.plotly_chart(fig, use_container_width=True)

            # ABRECHNUNG (Nur sichtbar wenn spezifische Session gewählt)
            if view_mode != "Alle Sessions":
                with st.expander("💸 Abrechnung (Verlierer zahlen)", expanded=False):
                    losers = leaderboard[leaderboard["Profit"] < -0.01] # Kleine Toleranz
                    if losers.empty:
                        st.balloons()
                        st.success("Niemand ist im Minus! 🎉")
                    else:
                        st.write("**Wer möchte bezahlen?**")
                        cols = st.columns(2)
                        
                        # Secrets laden
                        iban = st.secrets.get("bank", {}).get("iban", "")
                        owner = st.secrets.get("bank", {}).get("owner", "Bank")

                        selected_loser = cols[0].selectbox("Spieler wählen:", losers["Name"].values)
                        if selected_loser:
                            amount = abs(losers[losers["Name"] == selected_loser]["Profit"].values[0])
                            cols[0].metric("Zu zahlen", f"{amount:.2f} €")
                            
                            if iban:
                                qr_url = generate_epc_qr_url(owner, iban, amount, f"BJ {view_mode}")
                                cols[1].image(qr_url, width=200, caption="Scan & Pay")
                            else:
                                cols[1].warning("Keine IBAN in secrets.toml")

# ==========================================
# TAB 2: SPIELER DETAILS
# ==========================================
with tab_player:
    st.header("Spieler Analyse 🕵️‍♂️")
    
    all_player_names = sorted(df["Name"].unique()) if "Name" in df.columns else []
    # Filter 'Bank' raus falls vorhanden
    all_player_names = [n for n in all_player_names if "Bank" not in n]
    
    if not all_player_names:
        st.warning("Noch keine Spielerdaten.")
    else:
        selected_player = st.selectbox("Wähle einen Spieler:", all_player_names)
        
        # Filter Daten für diesen Spieler (Lifetime)
        p_df = df[df["Name"] == selected_player].copy()
        p_df["Running_Total"] = p_df["Netto"].cumsum()
        
        # --- METRICS ---
        lifetime_profit = p_df["Netto"].sum()
        max_profit_session = 0
        min_profit_session = 0
        
        # Group by Session für Session-Stats
        p_sessions = p_df.groupby("Session_ID")["Netto"].sum().reset_index()
        if not p_sessions.empty:
            max_profit_session = p_sessions["Netto"].max()
            min_profit_session = p_sessions["Netto"].min()
            best_session_date = p_sessions.loc[p_sessions["Netto"].idxmax()]["Session_ID"]
            worst_session_date = p_sessions.loc[p_sessions["Netto"].idxmin()]["Session_ID"]
        
        # --- BADGES LOGIC ---
        badges_html = ""
        if lifetime_profit > 50: badges_html += '<span class="badge bg-success">Bankkiller 💰</span>'
        if lifetime_profit < -50: badges_html += '<span class="badge bg-danger">Dauerverlierer 💸</span>'
        if lifetime_profit < -100: badges_html += '<span class="badge bg-dark">Der Sponsor 👑</span>'
        
        buyins = len(p_df[p_df["Aktion"].str.contains("Einzahlung", case=False)])
        if buyins > 10: badges_html += '<span class="badge bg-info">Stammgast 🍺</span>'
        
        if abs(lifetime_profit) < 5 and len(p_df) > 5: badges_html += '<span class="badge bg-warning">Break-Even König ⚖️</span>'

        st.markdown(f"### {selected_player} {badges_html}", unsafe_allow_html=True)
        
        mp1, mp2, mp3, mp4 = st.columns(4)
        mp1.metric("Lifetime Profit", f"{lifetime_profit:+.2f} €")
        mp2.metric("Bester Abend", f"{max_profit_session:+.2f} €", help=f"Session: {best_session_date if not p_sessions.empty else '-'}")
        mp3.metric("Schlechtester Abend", f"{min_profit_session:+.2f} €", help=f"Session: {worst_session_date if not p_sessions.empty else '-'}")
        mp4.metric("Anzahl Abende", f"{len(p_sessions)}")
        
        # --- CHART: TIMELINE ---
        st.subheader("Verlauf (Lifetime)")
        fig_p = px.line(p_df, x="Full_Date", y="Running_Total", markers=True, title=f"Kapitalverlauf von {selected_player}")
        fig_p.add_hline(y=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig_p, use_container_width=True)
        
        # --- LISTE DER ABENDE ---
        st.subheader("Ergebnisse pro Abend")
        st.dataframe(p_sessions.sort_values("Session_ID", ascending=False).style.format({"Netto": "{:.2f} €"}), use_container_width=True)


# ==========================================
# TAB 3: HISTORY (Alle Abende)
# ==========================================
with tab_history:
    st.header("Die legendären Abende 📜")
    
    if df.empty:
        st.info("Keine Daten.")
    else:
        # Wir gruppieren alles nach Session_ID
        # Achtung: Wir brauchen: Datum, Bank-Resultat, MVP
        
        history_data = []
        
        for sid in unique_sessions:
            if sid == "Legacy_Archiv": continue # Optional ausblenden
            
            s_df = df[df["Session_ID"] == sid]
            
            # Bank Resultat
            bank_res = s_df["Netto"].sum()
            
            # MVP Berechnung
            s_players = s_df[~s_df["Aktion"].str.contains("Bank", case=False)]
            if not s_players.empty:
                s_group = s_players.groupby("Name")["Netto"].sum().reset_index()
                mvp_row = s_group.loc[s_group["Netto"].idxmax()]
                loser_row = s_group.loc[s_group["Netto"].idxmin()]
                
                mvp_txt = f"{mvp_row['Name']} (+{mvp_row['Netto']:.0f}€)"
                loser_txt = f"{loser_row['Name']} ({loser_row['Netto']:.0f}€)"
            else:
                mvp_txt = "-"
                loser_txt = "-"
                
            history_data.append({
                "Session": sid,
                "Bank Gewinn": bank_res,
                "Größter Gewinner 🏆": mvp_txt,
                "Größter Verlierer ☠️": loser_txt
            })
            
        df_hist = pd.DataFrame(history_data)
        
        if not df_hist.empty:
            # Styling für Bank Gewinn
            st.dataframe(
                df_hist.style.format({"Bank Gewinn": "{:.2f} €"}).applymap(
                    lambda v: 'color: green;' if v > 0 else 'color: red;', subset=['Bank Gewinn']
                ),
                use_container_width=True,
                hide_index=True
            )

# ==========================================
# TAB 4: BUCHEN (Eingabe)
# ==========================================
with tab_booking:
    st.header(f"Buchung für: {st.session_state.active_session}")
    
    with st.form("buchung_form", clear_on_submit=True):
        col_b1, col_b2 = st.columns(2)
        
        # Bekannte Namen aus der DB laden + Option für neu
        known_names = sorted(list(set(df["Name"].unique()) - {"Bank Einnahme", "Bank Ausgabe"})) if not df.empty else ["Spieler 1"]
        
        with col_b1:
            name_input = st.selectbox("Name", known_names + ["Neuer Spieler..."])
            if name_input == "Neuer Spieler...":
                new_name = st.text_input("Name eingeben:")
            else:
                new_name = name_input
                
        with col_b2:
            betrag_input = st.number_input("Betrag", min_value=0.0, value=10.0, step=5.0)
            
        typ_input = st.radio("Aktion", [
            "Einzahlung (Spieler kauft Chips)", 
            "Auszahlung (Spieler gibt Chips ab)",
            "Bank Einnahme (Sonstiges)",
            "Bank Ausgabe (Getränke etc.)"
        ])
        
        submitted = st.form_submit_button("Buchen ✅", type="primary")
        
        if submitted:
            final_name = new_name if name_input == "Neuer Spieler..." else name_input
            if not final_name:
                st.error("Bitte Name eingeben.")
            else:
                # Mapping der Radio Buttons zu Datenbank-Werten
                typ_short = "Einzahlung"
                if "Auszahlung" in typ_input: typ_short = "Auszahlung"
                if "Bank Einnahme" in typ_input: typ_short = "Bank Einnahme"
                if "Bank Ausgabe" in typ_input: typ_short = "Bank Ausgabe"
                
                # Neue Zeile erstellen
                new_row = pd.DataFrame([{
                    "Datum": get_current_date_str(),
                    "Zeitstempel": get_current_time_str(),
                    "Name": final_name,
                    "Aktion": typ_short,
                    "Betrag": betrag_input,
                    "Session_ID": st.session_state.active_session
                }])
                
                # Schreiben
                try:
                    # Wir laden die rohen Daten nochmal um sicherzugehen
                    raw_df = conn.read(worksheet="Buchungen", ttl=0)
                    
                    # Schema Anpassung beim Schreiben falls nötig
                    if "Session_ID" not in raw_df.columns:
                        raw_df["Session_ID"] = "Legacy_Archiv"
                    
                    # Spaltennamen Mapping für raw_df sicherstellen (falls Sheet headers anders sind)
                    # Wir gehen davon aus, das Sheet hat die Header die wir erwarten. 
                    # Falls nicht, einfach appenden.
                    
                    updated_df = pd.concat([raw_df, new_row], ignore_index=True)
                    conn.update(worksheet="Buchungen", data=updated_df)
                    st.toast(f"Gebucht: {final_name} {betrag_input}€")
                    st.cache_data.clear()
                    st.rerun() # Refresh um Daten im Dashboard zu zeigen
                    
                except Exception as e:
                    st.error(f"Fehler beim Speichern: {e}")
