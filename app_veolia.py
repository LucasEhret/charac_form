import streamlit as st
import datetime as dt
import pandas as pd
import matplotlib.pyplot as plt
import io
import dropbox


DEV_MODE = False


MATERIALS_FILE = "list_classes.csv"

SENSORS_FILE = "list_sensors.csv"

FACILITY_NAME = "Veolia Bonneuil"  # ← change this for each deployment
# FACILITY_NAME = "TVL"  # ← change this for each deployment

@st.cache_data
def load_column_from_csv(csv_file: str) -> list[str]:
    df = pd.read_csv(csv_file, encoding="utf-8", sep=";")
    if FACILITY_NAME not in df.columns:
        st.error(
            f"Le fichier '{csv_file}' ne contient pas de colonne '{FACILITY_NAME}'. "
            f"Colonnes disponibles : {', '.join(df.columns.tolist())}"
        )
        st.stop()
    return (
        df[FACILITY_NAME]
        .dropna()
        .astype(str)
        .str.strip()
        .loc[lambda s: s != ""]
        .tolist()
    )


material_classes = load_column_from_csv(MATERIALS_FILE)
sensor_list  = load_column_from_csv(SENSORS_FILE)

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Résultat de caractérisation",
    page_icon="⚖️",
    layout="centered",
)

# ── SESSION STATE INIT ────────────────────────────────────────────────────────
DEFAULTS = {
    "container_error": "",
    "weighing_error":  "",
    "saved_operator_name": "",
    "saved_test_date":    dt.date.today(),
    "saved_sensor_name":  "1",
    "saved_nb_sample":    1,
    "df_containers": pd.DataFrame({
        "Contenant": pd.Series(dtype="str"),
        "Poids à vide": pd.Series(dtype="float")
    }),
    "df_collect_times": pd.DataFrame({
        "Echantillon": pd.Series(dtype="int"),
        "Date": pd.Series(dtype="object"),
        "Heure de début": pd.Series(dtype="str"),
        "Heure de fin": pd.Series(dtype="str")
    }),
    "df_weighings": pd.DataFrame({
        "N° échantillon":     pd.Series(dtype="int"),
        "Début":              pd.Series(dtype="object"), # ou "datetime64[ns]" si besoin
        "Fin":                pd.Series(dtype="object"),
        "Classe de matériau": pd.Series(dtype="str"),
        "Contenant utilisé":  pd.Series(dtype="str"),
        "Poids brut":         pd.Series(dtype="float"),
        "Poids net":          pd.Series(dtype="float"),
    }),
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ── HELPERS ───────────────────────────────────────────────────────────────────
def check_entry_typo(text: str) -> bool:
    parts = text.strip().split()
    if not parts:
        return False
    try:
        for part in parts:
            float(part.replace(",", "."))
        return True
    except ValueError:
        return False


def get_sample_collect_times(sample_id: int):
    existing = st.session_state["df_collect_times"]
    if existing.empty or "Echantillon" not in existing.columns:
        return None
    row = existing.loc[existing["Echantillon"] == sample_id]
    if row.empty:
        return None
    
    # On récupère la date de l'échantillon (ou la date globale par défaut)
    sample_date = row.iloc[0]["Date"] if "Date" in row.columns else st.session_state["saved_test_date"]
    
    t_start = dt.time.fromisoformat(row.iloc[0]["Heure de début"])
    t_end   = dt.time.fromisoformat(row.iloc[0]["Heure de fin"])
    
    # On combine la date et l'heure pour l'export
    return {
        "Début": dt.datetime.combine(sample_date, t_start),
        "Fin":   dt.datetime.combine(sample_date, t_end),
    }


def get_container_weight(container_name: str) -> float:
    if not container_name:
        return 0.0
    row = st.session_state["df_containers"].loc[
        st.session_state["df_containers"]["Contenant"] == container_name
    ]
    if row.empty:
        return 0.0
    return float(row.iloc[0]["Poids à vide"])


def _clean_time_widget_keys(nb_sample: int) -> None:
    i = nb_sample + 1
    while f"_start_{i}_h" in st.session_state:
        for key in (f"_start_{i}_h", f"_start_{i}_m", f"_start_{i}_s",
                    f"_end_{i}_h",   f"_end_{i}_m",   f"_end_{i}_s"):
            st.session_state.pop(key, None)
        i += 1


def init_metadata_widget_state() -> None:
    if "_operator_name" not in st.session_state:
        st.session_state["_operator_name"] = st.session_state["saved_operator_name"]
    if "_test_date" not in st.session_state:
        st.session_state["_test_date"] = st.session_state["saved_test_date"]
    if "_sensor_name" not in st.session_state:
        st.session_state["_sensor_name"] = st.session_state["saved_sensor_name"]
    if "_nb_sample" not in st.session_state:
        st.session_state["_nb_sample"] = st.session_state["saved_nb_sample"]

    nb_sample = int(st.session_state["_nb_sample"])
    existing  = st.session_state["df_collect_times"]

    for i in range(1, nb_sample + 1):
        if existing.empty or "Echantillon" not in existing.columns:
            start, end = dt.time(0, 0, 0), dt.time(0, 0, 0)
            sample_date = st.session_state["saved_test_date"]
        else:
            row   = existing.loc[existing["Echantillon"] == i]
            start = dt.time.fromisoformat(row.iloc[0]["Heure de début"]) if not row.empty else dt.time(0, 0, 0)
            end   = dt.time.fromisoformat(row.iloc[0]["Heure de fin"])   if not row.empty else dt.time(0, 0, 0)
            sample_date = row.iloc[0]["Date"] if (not row.empty and "Date" in row.columns) else st.session_state["saved_test_date"]

        for suffix, val in (
            (f"_start_{i}_h", start.hour), (f"_start_{i}_m", start.minute), (f"_start_{i}_s", start.second),
            (f"_end_{i}_h",   end.hour),   (f"_end_{i}_m",   end.minute),   (f"_end_{i}_s",   end.second),
        ):
            if suffix not in st.session_state:
                st.session_state[suffix] = val

                # Initialisation de la date spécifique
        if f"_date_{i}" not in st.session_state:
            st.session_state[f"_date_{i}"] = sample_date


def save_metadata() -> None:
    nb_sample = st.session_state["_nb_sample"]
    rows = []
    for i in range(1, nb_sample + 1):
            s_date = st.session_state.get(f"_date_{i}") or st.session_state["_test_date"]
            # On utilise .get() avec une valeur par défaut de 0 si le champ est None
            h_s = st.session_state.get(f"_start_{i}_h") or 0
            m_s = st.session_state.get(f"_start_{i}_m") or 0
            s_s = st.session_state.get(f"_start_{i}_s") or 0
            
            h_e = st.session_state.get(f"_end_{i}_h") or 0
            m_e = st.session_state.get(f"_end_{i}_m") or 0
            s_e = st.session_state.get(f"_end_{i}_s") or 0
            
            rows.append({
                "Echantillon": i,
                "Date": s_date,
                "Heure de début": f"{int(h_s):02d}:{int(m_s):02d}:{int(s_s):02d}",
                "Heure de fin":   f"{int(h_e):02d}:{int(m_e):02d}:{int(s_e):02d}"
            })
    
    st.session_state["df_collect_times"] = pd.DataFrame(rows)
    st.session_state["saved_sensor_name"] = st.session_state["_sensor_name"]
    st.session_state["saved_nb_sample"] = nb_sample


def add_container() -> None:
    container_name   = st.session_state["container_name"].strip()
    # On s'assure que le poids est bien un float
    try:
        container_weight = float(st.session_state["container_weight"])
    except ValueError:
        st.session_state["container_error"] = "Le poids doit être un nombre valide."
        return

    if not container_name:
        st.session_state["container_error"] = "Veuillez renseigner un identifiant de contenant."
        return
        
    if container_name in st.session_state["df_containers"]["Contenant"].tolist():
        st.session_state["container_error"] = "Ce contenant existe déjà."
        return

    # Création du petit DataFrame à ajouter avec types explicites
    new_data = pd.DataFrame({
        "Contenant": [container_name], 
        "Poids à vide": [container_weight]
    }).astype({"Contenant": str, "Poids à vide": float})

    # Concaténation
    st.session_state["df_containers"] = pd.concat(
        [st.session_state["df_containers"], new_data],
        ignore_index=True,
    )
    
    # Nettoyage et rafraîchissement
    st.session_state["container_name"]   = ""
    st.session_state["container_weight"] = 0.0
    st.session_state["container_error"] = ""


def remove_container(container_name: str) -> None:
    st.session_state["df_containers"] = (
        st.session_state["df_containers"]
        .loc[st.session_state["df_containers"]["Contenant"] != container_name]
        .reset_index(drop=True)
    )
    # Cascade: remove weighings that used this container
    st.session_state["df_weighings"] = (
        st.session_state["df_weighings"]
        .loc[st.session_state["df_weighings"]["Contenant utilisé"] != container_name]
        .reset_index(drop=True)
    )
    st.session_state["container_error"] = ""
    st.rerun()


def add_weighing() -> None:
    gross_weight_text = st.session_state["gross_weight"].strip()

    if not check_entry_typo(gross_weight_text):
        st.session_state["weighing_error"] = (
            "Veuillez vérifier la saisie des poids bruts. "
            "Séparez les poids par des espaces, avec virgule ou point décimal."
        )
        return

    sample_id      = st.session_state["sample_nb"]
    material_class = st.session_state["material_class"]
    container_used = st.session_state["container_used"]

    if sample_id is None:
        st.session_state["weighing_error"] = "Veuillez choisir un numéro d'échantillon."
        return
    if material_class is None:
        st.session_state["weighing_error"] = "Veuillez choisir une classe de matériau."
        return
    st.toast("Pesée ajoutée !", icon="⚖️")

    times = get_sample_collect_times(sample_id)
    if times is None:
        # st.session_state["error_message"] = (
        #     "Impossible de trouver les heures de prélèvement de cet échantillon. "
        #     "Pensez à enregistrer les métadonnées."
        # )
        return

    tare_weight = get_container_weight(container_used)
    weights     = [float(w.replace(",", ".")) for w in gross_weight_text.split()]

    new_rows = []
    for gross_weight in weights:
        net_weight = gross_weight - tare_weight
        if net_weight < 0:
            st.session_state["weighing_error"] = (
                f"Le poids net calculé est négatif ({net_weight:.3f} kg). "
                "Vérifiez le contenant sélectionné et les poids saisis."
            )
            return
        new_rows.append({
            "N° échantillon":     sample_id,
            "Début":              times["Début"],
            "Fin":                times["Fin"],
            "Classe de matériau": material_class,
            "Contenant utilisé":  container_used or "",
            "Poids brut":         gross_weight,
            "Poids net":          net_weight,
        })

    new_df = pd.DataFrame(new_rows)

    new_df["Poids brut"] = new_df["Poids brut"].astype(float)
    new_df["Poids net"] = new_df["Poids net"].astype(float)

    if st.session_state["df_weighings"].empty:
        st.session_state["df_weighings"] = new_df
    else:
        st.session_state["df_weighings"] = pd.concat(
            [st.session_state["df_weighings"], new_df],
            ignore_index=True,
        )

    st.session_state["sample_nb"]      = 1
    st.session_state["material_class"] = None
    st.session_state["container_used"] = None
    st.session_state["gross_weight"]   = ""
    st.session_state["weighing_error"]  = ""


def delete_weighing(idx: int) -> None:
    st.session_state["df_weighings"] = (
        st.session_state["df_weighings"]
        .drop(index=idx)
        .reset_index(drop=True)
    )
    st.session_state["weighing_error"] = ""
    st.rerun()


def summarize_by_material(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=["Classe de matériau", "Poids net", "Pourcentage de la masse totale"]
        )
    summary = (
        df.groupby("Classe de matériau", as_index=False)[["Poids net"]]
        .sum()
        .sort_values("Poids net", ascending=False)
        .reset_index(drop=True)
    )
    total = summary["Poids net"].sum()
    summary["Pourcentage de la masse totale"] = (
        summary["Poids net"] / total * 100 if total > 0 else 0.0
    )
    return summary


def build_excel_export() -> io.BytesIO:
    buf    = io.BytesIO()
    df     = st.session_state["df_weighings"].copy()
    sensor = st.session_state["saved_sensor_name"]
    date   = st.session_state["saved_test_date"]

    # Aggregate: one row per sample × material class
    df_agg = (
        df.groupby(["N° échantillon", "Classe de matériau"], as_index=False)
        .agg(Début=("Début", "first"), Fin=("Fin", "first"), Poids_net=("Poids net", "sum"))
    )

    # Per-sample totals (used in per-sample sheets)
    sample_totals = (
        df_agg.groupby("N° échantillon")["Poids_net"]
        .sum()
        .rename("Masse totale échantillon")
    )
    df_agg = df_agg.merge(sample_totals, left_on="N° échantillon", right_index=True, how="left")
    df_agg["% of sample total"] = df_agg["Poids_net"] / df_agg["Masse totale échantillon"] * 100

    # Grand total (used in global sheet)
    grand_total = df_agg["Poids_net"].sum()
    df_agg["% of grand total"] = df_agg["Poids_net"] / grand_total * 100 if grand_total > 0 else 0.0

    df_agg["sensor name"] = sensor
    df_agg["date"]        = date

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:

        # ── Sheet 1: global summary ───────────────────────────────────────────
        sheet1 = df_agg[[
            "sensor name", "date",
            "N° échantillon", "Début", "Fin",
            "Classe de matériau", "Poids_net", "% of grand total",
        ]].rename(columns={
            "N° échantillon":     "sample number",
            "Début":              "start time",
            "Fin":                "end time",
            "Classe de matériau": "Material class",
            "Poids_net":          "Net weight (kg)",
        })

        total_row = pd.DataFrame([{
            "sensor name":    sensor,
            "date":           date,
            "sample number":  "TOTAL",
            "start time":     "",
            "end time":       "",
            "Material class": "",
            "Net weight (kg)": grand_total,
            "% of grand total": 100.0,
        }])
        sheet1 = pd.concat([sheet1, total_row], ignore_index=True)
        sheet1.to_excel(writer, sheet_name="Global results", index=False)

        # ── One sheet per sample ──────────────────────────────────────────────
        for sample_id in sorted(df_agg["N° échantillon"].unique()):
            df_s       = df_agg[df_agg["N° échantillon"] == sample_id].iloc[0]
            start_time = df_s["Début"]
            end_time   = df_s["Fin"]

            times_df = pd.DataFrame([
                {"": "Start time", " ": str(start_time)},
                {"": "End time",   " ": str(end_time)},
            ])

            df_sample = (
                df_agg[df_agg["N° échantillon"] == sample_id][[
                    "Classe de matériau", "Poids_net", "% of sample total",
                ]]
                .rename(columns={
                    "Classe de matériau": "Material class",
                    "Poids_net":          "Net weight (kg)",
                })
                .copy()
            )

            total_row_s = pd.DataFrame([{
                "Material class":   "TOTAL",
                "Net weight (kg)":  df_sample["Net weight (kg)"].sum(),
                "% of sample total": 100.0,
            }])
            df_sample = pd.concat([df_sample, total_row_s], ignore_index=True)

            sheet_name = f"Sample {int(sample_id)}"
            times_df.to_excel( writer, sheet_name=sheet_name, index=False, startrow=0)
            df_sample.to_excel(writer, sheet_name=sheet_name, index=False, startrow=len(times_df) + 2)
        # ── Metadata sheet ────────────────────────────────────────────────────
        df_weighings = st.session_state["df_weighings"]
        pd.DataFrame([
            {"field": "Operator name",       "value": st.session_state["saved_operator_name"]},
            {"field": "Test date",           "value": str(st.session_state["saved_test_date"])},
            {"field": "Sensor name",         "value": st.session_state["saved_sensor_name"]},
            {"field": "Number of samples",   "value": st.session_state["saved_nb_sample"]},
            {"field": "Number of weighings", "value": len(df_weighings)},
            {"field": "Total net weight (kg)", "value": round(df_weighings["Poids net"].sum(), 4) if not df_weighings.empty else 0},
            {"field": "Material classes used", "value": ", ".join(sorted(df_weighings["Classe de matériau"].unique())) if not df_weighings.empty else ""},
            {"field": "Containers used",     "value": ", ".join(sorted(df_weighings["Contenant utilisé"].replace("", pd.NA).dropna().unique())) if not df_weighings.empty else ""},
            {"field": "Export timestamp", "value": (dt.datetime.now(dt.timezone(dt.timedelta(hours=2))).strftime("%Y-%m-%d %H:%M:%S"))},
        ]).to_excel(writer, sheet_name="Metadata", index=False)
    buf.seek(0)
    return buf


def upload_to_dropbox(excel_buffer, file_name):
    try:
        # Initialisation avec Refresh Token pour une connexion permanente
        dbx = dropbox.Dropbox(
            app_key=st.secrets["DROPBOX_APP_KEY"],
            app_secret=st.secrets["DROPBOX_APP_SECRET"],
            oauth2_refresh_token=st.secrets["DROPBOX_REFRESH_TOKEN"]
        )
        
        path = st.secrets.get("DROPBOX_DESTINATION_PATH", "/")
        full_path = f"{path}{file_name}".replace("//", "/")
        
        dbx.files_upload(
            excel_buffer.getvalue(), 
            full_path, 
            mode=dropbox.files.WriteMode.overwrite
        )
        return True
    except Exception as e:
        st.error(f"Erreur lors de l'envoi vers Dropbox : {e}")
        return False
    

def hms_widget(label, key_prefix, on_change_callback):
    st.write(label)
    cols = st.columns([1, 1, 1])
    with cols[0]:
        st.markdown("<center style='font-size:11px;color:grey'>HH</center>", unsafe_allow_html=True)
        h = st.number_input("H", 0, 23, value=None, key=f"{key_prefix}_h", on_change=on_change_callback, label_visibility="collapsed")
    with cols[1]:
        st.markdown("<center style='font-size:11px;color:grey'>MM</center>", unsafe_allow_html=True)
        m = st.number_input("M", 0, 59, value=None, key=f"{key_prefix}_m", on_change=on_change_callback, label_visibility="collapsed")
    with cols[2]:
        st.markdown("<center style='font-size:11px;color:grey'>SS</center>", unsafe_allow_html=True)
        s = st.number_input("S", 0, 59, value=None, key=f"{key_prefix}_s", on_change=on_change_callback, label_visibility="collapsed")

    if h is None or m is None or s is None:
        return None
    return dt.time(h, m, s)

# ── TITLE ─────────────────────────────────────────────────────────────────────
st.title("Résultat de caractérisation")

# ── TABS ──────────────────────────────────────────────────────────────────────
tab_metadata, tab_containers, tab_weighing, tab_summary = st.tabs(
    ["Métadonnées", "Contenants", "Résultats de pesée", "Résumé de la caractérisation"]
)


# ── TAB 1 : METADATA ──────────────────────────────────────────────────────────
with tab_metadata:
    init_metadata_widget_state()
    with st.expander("📖 Voir le guide du processus de caractérisation (Aide)"):
        st.image(".streamlit/images/process carac.png", width='stretch')
        st.space()
        st.markdown("""
        ### ➡️ Bien démarrer
        Ce formulaire est conçu pour capturer les données de caractérisation en temps réel sur le terrain. 
        **Toutes les modifications sont enregistrées automatiquement** dès que vous changez de champ.

        ---

        ### 1️⃣ Configuration (Métadonnées)
        * **Nom du capteur :** Sélectionnez le capteur testé. C'est ce nom qui sera utilisé pour nommer votre fichier final.
        * **Heures de prélèvement :** Saisissez l'heure, les minutes et les secondes. 
            * *Astuce :* Si vous laissez un champ vide (affichage `HH`), il sera considéré comme `00`.
            * *Important :* Vérifiez bien la date pour chaque échantillon si le test dure plus de 24h.

        ### 2️⃣ Gestion des Contenants
        * Avant de peser, enregistrez vos bacs/cartons dans l'onglet **Contenants**.
        * Donnez-leur un nom clair (ex: "Bac Bleu 1") et saisissez leur **poids à vide (tare)**.
        * L'application calculera automatiquement le **poids net** en soustrayant cette tare.
        * Il est possible de ne renseigner aucun contenant, dans le cas où vous avez procédé autrement.

        ### 3️⃣ Saisie des Pesées
        * Sélectionnez le matériau et le contenant utilisé.
        * **Erreur courante :** Si vous saisissez du texte à la place d'un chiffre pour le poids, une erreur rouge apparaîtra. 
        * Utilisez le bouton `X` pour supprimer une ligne en cas d'erreur de saisie.

        ---
        """)
        st.success("✅ **Une fois fini :** Allez dans l'onglet 'Résumé' pour télécharger les données, et les sauvegarder en ligne.")
    # st.subheader("Métadonnées")

    with st.container(border=True):
        st.markdown("### Informations spécifiques au test")
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        with r1c1: st.text_input("Nom", placeholder="Entrez votre nom", key="_operator_name")
        with r1c2: st.date_input("Date du jour", key="_test_date")
        with r1c3: st.selectbox("Nom du capteur", sensor_list, key="_sensor_name", index=0)
        with r1c4:
            st.number_input(
                "Nombre d'échantillons",
                step=1, 
                min_value=1, 
                format="%d",
                key="_nb_sample",
            )

        # Dans tab_metadata, remplacez la boucle for par celle-ci :
        for i in range(1, int(st.session_state["_nb_sample"]) + 1):
            st.divider()
            st.subheader(f"Prélèvement de l'échantillon {i}")
            
            # Nouveau widget de date par échantillon
            st.date_input("Date du prélèvement", key=f"_date_{i}", on_change=save_metadata)
            
            col_start, col_end = st.columns(2)
            with col_start:
                hms_widget("Heure de début", f"_start_{i}", save_metadata)
            with col_end:
                hms_widget("Heure de fin", f"_end_{i}", save_metadata)

        st.space()
        # st.button(
        #     "💾 Enregistrer les métadonnées",
        #     on_click=save_metadata,
        #     key="save_metadata_button",
        # )

    st.dataframe(st.session_state["df_collect_times"], hide_index=True)


# ── TAB 2 : CONTAINERS ────────────────────────────────────────────────────────
with tab_containers:
    st.subheader("Contenants")

    with st.container(border=True):
        if st.session_state["container_error"]:
            st.warning(st.session_state["container_error"])
        st.markdown("### Ajout de contenants")
        st.caption(
            "Ajoutez les contenants utilisés pour peser les matériaux. "
            "Si vous n'avez pas utilisé de contenants, laissez cette section vide."
        )
        col1, col2, col3 = st.columns(3, vertical_alignment="bottom")
        with col1:
            st.text_input(
                "Identificateur du contenant",
                placeholder="Veuillez renseigner le nom du contenant",
                key="container_name",
            )
        with col2:
            st.number_input(
                "Poids du contenant vide (kg)",
                min_value=0.0, step=0.1, format="%.3f",
                key="container_weight",
            )
        with col3:
            st.button(
                "✅ Ajouter contenant",
                width='stretch',
                on_click=add_container,
                key="add_container_button",
            )


    if st.session_state["df_containers"].empty:
            st.info("Aucun contenant enregistré.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.markdown("**Nom du contenant**")
        c2.markdown("**Poids à vide**")
        for _, row in st.session_state["df_containers"].iterrows():
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(row["Contenant"])
            c2.write(f"{row['Poids à vide']:.3f} kg")
            # Suppression du st.rerun() ici aussi
            if c3.button("Supprimer", key=f"del_{row['Contenant']}"):
                remove_container(row["Contenant"])


# ── TAB 3 : WEIGHING ──────────────────────────────────────────────────────────
with tab_weighing:
    st.subheader("Résultats de pesée")
    disable_weighing = False
    if st.session_state["df_collect_times"].empty:
        disable_weighing = True
        st.warning("Aucune heure de prélèvement n'a été renseignée.")
    with st.container(border=True):
        if st.session_state["weighing_error"]:
            st.warning(st.session_state["weighing_error"])
        st.markdown("### Entrée de pesée")
        col1, col2, col3, col4, col5 = st.columns(5, vertical_alignment="bottom")

        with col1:
            st.selectbox(
                "Numéro de l'échantillon",
                list(range(1, st.session_state["saved_nb_sample"] + 1)),
                key="sample_nb",
                index=0, 
                disabled=disable_weighing
            )
        with col2:
            st.selectbox(
                "Classe de matériau",
                material_classes,
                key="material_class",
                index=None,
                placeholder="Choisir...",
                disabled=disable_weighing,
                accept_new_options=True
            )
        with col3:
            st.selectbox(
                "Contenant utilisé",
                st.session_state["df_containers"]["Contenant"].tolist(),
                disabled=st.session_state["df_containers"].empty,
                key="container_used",
                index=None,
                placeholder="Choisir...",
            )
        with col4:
            weights_input = st.text_input(
                "Poids brut (kg)",
                key="gross_weight",
                placeholder="Ex: 12.5 14.2",
                disabled=disable_weighing
            )


        with col5:
            disable_add_weight = True
            if st.session_state["sample_nb"] and st.session_state["material_class"]:
                disable_add_weight = False
            st.button("✅ Ajouter la pesée", on_click=add_weighing, key="add_weighing_button", width='stretch', disabled=disable_add_weight)

                    # Validation en direct (Point 2 précédent)
        if weights_input:
            if check_entry_typo(weights_input):
                vals = [float(w.replace(",", ".")) for w in weights_input.split()]
                st.caption(f"✅ {len(vals)} pesée(s). Total : **{sum(vals):.3f} kg**")

    # Affichage du tableau
    df_w = st.session_state["df_weighings"]
    if df_w.empty:
        st.info("Aucune pesée enregistrée.")
    else:
        h_cols = st.columns([1, 2, 2, 1.5, 1.5, 1])
        labels = ["#échant.", "Classe", "Contenant", "Brut", "Net", ""]
        for col, label in zip(h_cols, labels):
            col.markdown(f"**{label}**")
            
        for idx, row in df_w.iterrows():
            r = st.columns([1, 2, 2, 1.5, 1.5, 1])
            r[0].write(int(row["N° échantillon"]))
            # r[1].write(str(row["Début"]))
            # r[2].write(str(row["Fin"]))
            r[1].write(row["Classe de matériau"])
            r[2].write(row["Contenant utilisé"])
            r[3].write(f"{row['Poids brut']:.3f}")
            r[4].write(f"{row['Poids net']:.3f}")
            # Suppression sans st.rerun()
            if r[5].button("✕", key=f"del_w_{idx}"):
                delete_weighing(idx)
    # weighing_section() 


# ── TAB 4 : SUMMARY ───────────────────────────────────────────────────────────
with tab_summary:
    # st.subheader("Résumé de la caractérisation")

    df_summary_by_material = summarize_by_material(st.session_state["df_weighings"])
    total_net_mass = df_summary_by_material["Poids net"].sum() if not df_summary_by_material.empty else 0.0

    st.write(f"### Résumé global — masse totale : {total_net_mass:.2f} kg")
    st.dataframe(df_summary_by_material, hide_index=True)

    with st.container(border=True):
        if not df_summary_by_material.empty and total_net_mass > 0:
            fig, ax = plt.subplots()
            ax.pie(
                df_summary_by_material["Pourcentage de la masse totale"],
                labels=df_summary_by_material["Classe de matériau"],
                autopct="%1.1f%%",
            )
            ax.set_title("Répartition par classe de matériau")
            st.pyplot(fig)
            plt.close(fig)
        else:
            st.info("Aucune pesée enregistrée — le graphique s'affichera ici.")

    st.divider()
    st.markdown("### Résumé par échantillon")

    sample_ids = sorted(
        st.session_state["df_weighings"]["N° échantillon"].dropna().unique()
    )
    for sample_id in sample_ids:
        df_sample = st.session_state["df_weighings"][
            st.session_state["df_weighings"]["N° échantillon"] == sample_id
        ]
        df_sample_summary = summarize_by_material(df_sample)
        total_sample_net  = df_sample_summary["Poids net"].sum() if not df_sample_summary.empty else 0.0
        st.markdown(f"#### Échantillon {int(sample_id)} — masse totale : {total_sample_net:.2f} kg")
        st.dataframe(df_sample_summary, hide_index=True)
        st.divider()

    if not st.session_state["df_weighings"].empty:
        # Génération du fichier en mémoire
        excel_data = build_excel_export()
        
        # Nom du fichier basé sur la date et le capteur
        timestamp = (dt.datetime.now(dt.timezone(dt.timedelta(hours=2))).strftime("%Y%m%d_%H%M"))
        sensor_name = st.session_state["saved_sensor_name"].replace(" ", "_")
        filename = f"Resultat_{FACILITY_NAME}_{sensor_name}_{timestamp}.xlsx"

        # 1. Bouton de téléchargement local (pour l'utilisateur)
        st.download_button(
            "⬇️ Télécharger le fichier Excel localement",
            data=excel_data,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # 2. Bouton pour envoyer vers Dropbox (Cloud)
        if not DEV_MODE:
            if st.button("☁️ Sauvegarder dans le Cloud (Dropbox)"):
                with st.status("Préparation de l'envoi...", expanded=True) as status:
                    st.write("Génération de l'Excel...")
                    excel_data = build_excel_export()
                    st.write("Connexion à Dropbox...")
                    if upload_to_dropbox(excel_data, filename):
                        status.update(label="✅ Sauvegardé sur Dropbox !", state="complete", expanded=False)
                    else:
                        status.update(label="❌ Échec de l'envoi", state="error")
        else:
            st.info("DEV MODE — Dropbox upload désactivé.")
    else:
        st.info("Aucune pesée enregistrée — l'export sera disponible ici.")