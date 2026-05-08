import streamlit as st
import datetime as dt
import pandas as pd
import matplotlib.pyplot as plt
import io
import dropbox

MATERIALS_FILE = "list_classes.csv"

SENSORS_FILE = "list_sensors.csv"

FACILITY_NAME = "Veolia Bonneuil"  # ← change this for each deployment
# FACILITY_NAME = "TVL"  # ← change this for each deployment

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
    "error_message":      "",
    "saved_operator_name": "",
    "saved_test_date":    dt.date.today(),
    "saved_sensor_name":  "1",
    "saved_nb_sample":    1,
    "df_containers": pd.DataFrame(columns=["Contenant", "Poids à vide"]),
    "df_collect_times": pd.DataFrame(columns=["N° échantillon", "Début", "Fin"]),
    "df_weighings": pd.DataFrame(columns=[
        "N° échantillon", "Début", "Fin",
        "Classe de matériau", "Contenant utilisé",
        "Poids brut", "Poids net",
    ]),
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
    row = st.session_state["df_collect_times"].loc[
        st.session_state["df_collect_times"]["N° échantillon"] == sample_id
    ]
    if row.empty:
        return None
    return {"Début": row.iloc[0]["Début"], "Fin": row.iloc[0]["Fin"]}


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
    """Remove orphan widget keys left over when nb_sample is decreased."""
    i = nb_sample
    while any(f"_hs{i}" in st.session_state for _ in [None]):
        for prefix in ("_hs", "_ms", "_ss", "_he", "_me", "_se"):
            st.session_state.pop(f"{prefix}{i}", None)
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

    for i in range(nb_sample):
        sample_id = i + 1
        row   = existing.loc[existing["N° échantillon"] == sample_id]
        start = row.iloc[0]["Début"] if not row.empty else dt.time(0, 0, 0)
        end   = row.iloc[0]["Fin"]   if not row.empty else dt.time(0, 0, 0)

        for prefix, val in (
            ("_hs", start.hour), ("_ms", start.minute), ("_ss", start.second),
            ("_he", end.hour),   ("_me", end.minute),   ("_se", end.second),
        ):
            if f"{prefix}{i}" not in st.session_state:
                st.session_state[f"{prefix}{i}"] = val


def save_metadata() -> None:
    nb_sample = int(st.session_state["_nb_sample"])
    rows = []
    for i in range(nb_sample):
        start = dt.time(st.session_state[f"_hs{i}"], st.session_state[f"_ms{i}"], st.session_state[f"_ss{i}"])
        end   = dt.time(st.session_state[f"_he{i}"], st.session_state[f"_me{i}"], st.session_state[f"_se{i}"])
        if end <= start:
            st.session_state["error_message"] = (
                f"Échantillon {i + 1} : l'heure de fin doit être postérieure à l'heure de début."
            )
            return
        rows.append({"N° échantillon": i + 1, "Début": start, "Fin": end})

    st.session_state["saved_operator_name"] = st.session_state["_operator_name"]
    st.session_state["saved_test_date"]     = st.session_state["_test_date"]
    st.session_state["saved_sensor_name"]   = st.session_state["_sensor_name"]
    st.session_state["saved_nb_sample"]     = nb_sample
    st.session_state["df_collect_times"]    = pd.DataFrame(rows)
    st.session_state["error_message"]       = ""
    _clean_time_widget_keys(nb_sample)


def add_container() -> None:
    container_name   = st.session_state["container_name"].strip()
    container_weight = float(st.session_state["container_weight"])

    if not container_name:
        st.session_state["error_message"] = "Veuillez renseigner un identifiant de contenant."
        return
    if container_name in st.session_state["df_containers"]["Contenant"].tolist():
        st.session_state["error_message"] = "Ce contenant existe déjà."
        return

    st.session_state["df_containers"] = pd.concat(
        [
            st.session_state["df_containers"],
            pd.DataFrame({"Contenant": [container_name], "Poids à vide": [container_weight]}),
        ],
        ignore_index=True,
    )
    st.session_state["container_name"]   = ""
    st.session_state["container_weight"] = 0.0
    st.session_state["error_message"]    = ""


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
    st.session_state["error_message"] = ""


def add_weighing() -> None:
    gross_weight_text = st.session_state["gross_weight"].strip()

    if not check_entry_typo(gross_weight_text):
        st.session_state["error_message"] = (
            "Veuillez vérifier la saisie des poids bruts. "
            "Séparez les poids par des espaces, avec virgule ou point décimal."
        )
        return

    sample_id      = st.session_state["sample_nb"]
    material_class = st.session_state["material_class"]
    container_used = st.session_state["container_used"]

    if sample_id is None:
        st.session_state["error_message"] = "Veuillez choisir un numéro d'échantillon."
        return
    if material_class is None:
        st.session_state["error_message"] = "Veuillez choisir une classe de matériau."
        return

    times = get_sample_collect_times(sample_id)
    if times is None:
        st.session_state["error_message"] = (
            "Impossible de trouver les heures de prélèvement de cet échantillon. "
            "Pensez à enregistrer les métadonnées."
        )
        return

    tare_weight = get_container_weight(container_used)
    weights     = [float(w.replace(",", ".")) for w in gross_weight_text.split()]

    new_rows = []
    for gross_weight in weights:
        net_weight = gross_weight - tare_weight
        if net_weight < 0:
            st.session_state["error_message"] = (
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

    st.session_state["df_weighings"] = pd.concat(
        [st.session_state["df_weighings"], pd.DataFrame(new_rows)],
        ignore_index=True,
    )
    st.session_state["sample_nb"]      = 0
    st.session_state["material_class"] = None
    st.session_state["container_used"] = None
    st.session_state["gross_weight"]   = ""
    st.session_state["error_message"]  = ""


def delete_weighing(idx: int) -> None:
    st.session_state["df_weighings"] = (
        st.session_state["df_weighings"]
        .drop(index=idx)
        .reset_index(drop=True)
    )
    st.session_state["error_message"] = ""


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
            {"field": "Export timestamp",    "value": str(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))},
        ]).to_excel(writer, sheet_name="Metadata", index=False)
    buf.seek(0)
    return buf


def upload_to_dropbox(excel_buffer, file_name):
    """Envoie le buffer Excel vers le dossier Dropbox configuré."""
    try:
        # Initialisation du client avec le token des secrets
        dbx = dropbox.Dropbox(st.secrets["DROPBOX_ACCESS_TOKEN"])
        
        # Préparation du chemin complet
        path = st.secrets.get("DROPBOX_DESTINATION_PATH", "/")
        full_path = f"{path}{file_name}".replace("//", "/")
        
        # Upload du contenu du buffer (getvalue)
        dbx.files_upload(
            excel_buffer.getvalue(), 
            full_path, 
            mode=dropbox.files.WriteMode.overwrite
        )
        return True
    except Exception as e:
        st.error(f"Erreur lors de l'envoi vers Dropbox : {e}")
        return False
    
# ── TITLE ─────────────────────────────────────────────────────────────────────
st.title("Résultat de caractérisation")

if st.session_state["error_message"]:
    st.warning(st.session_state["error_message"])


# ── TABS ──────────────────────────────────────────────────────────────────────
tab_metadata, tab_containers, tab_weighing, tab_summary = st.tabs(
    ["Métadonnées", "Contenants", "Résultats de pesée", "Résumé de la caractérisation"]
)


# ── TAB 1 : METADATA ──────────────────────────────────────────────────────────
with tab_metadata:
    init_metadata_widget_state()
    st.subheader("Métadonnées")

    with st.container(border=True):
        st.markdown("### Informations spécifiques au test")
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        with r1c1: st.text_input("Nom", placeholder="Entrez votre nom", key="_operator_name")
        with r1c2: st.date_input("Date du jour", key="_test_date")
        with r1c3: st.selectbox("Nom du capteur", sensor_list, key="_sensor_name", index=0)
        with r1c4:
            st.number_input(
                "Nombre d'échantillons",
                step=1, min_value=1, value=1, format="%d",
                key="_nb_sample",
            )

        for i in range(int(st.session_state["_nb_sample"])):
            st.divider()
            st.subheader(f"Prélèvement de l'échantillon {i + 1}")

            c1, c2, c3, c4 = st.columns(4)
            with c1: st.text("Heure de début :")
            with c2: st.selectbox("heures",   list(range(24)), width=100, key=f"_hs{i}")
            with c3: st.selectbox("minutes",  list(range(60)), width=100, key=f"_ms{i}")
            with c4: st.selectbox("secondes", list(range(60)), width=100, key=f"_ss{i}")

            c1, c2, c3, c4 = st.columns(4)
            with c1: st.text("Heure de fin :")
            with c2: st.selectbox("heures",   list(range(24)), width=100, key=f"_he{i}")
            with c3: st.selectbox("minutes",  list(range(60)), width=100, key=f"_me{i}")
            with c4: st.selectbox("secondes", list(range(60)), width=100, key=f"_se{i}")

        st.space()
        st.button(
            "💾 Enregistrer les métadonnées",
            on_click=save_metadata,
            key="save_metadata_button",
        )

    st.dataframe(st.session_state["df_collect_times"], hide_index=True)


# ── TAB 2 : CONTAINERS ────────────────────────────────────────────────────────
with tab_containers:
    st.subheader("Contenants")

    with st.container(border=True):
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
                min_value=0.0, step=0.001, format="%.3f",
                key="container_weight",
            )
        with col3:
            st.button(
                "✅ Ajouter contenant",
                use_container_width=True,
                on_click=add_container,
                key="add_container_button",
            )

    if st.session_state["df_containers"].empty:
        st.info("Aucun contenant enregistré.")
    else:
        for _, row in st.session_state["df_containers"].iterrows():
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(row["Contenant"])
            c2.write(f"{row['Poids à vide']:.3f} kg")
            if c3.button("Supprimer", key=f"del_{row['Contenant']}"):
                remove_container(row["Contenant"])
                st.rerun()


# ── TAB 3 : WEIGHING ──────────────────────────────────────────────────────────
with tab_weighing:
    st.subheader("Résultats de pesée")

    with st.container(border=True):
        st.markdown("### Entrée de pesée")
        col1, col2, col3, col4, col5 = st.columns(5, vertical_alignment="bottom")

        with col1:
            st.selectbox(
                "Numéro de l'échantillon",
                list(range(1, st.session_state["saved_nb_sample"] + 1)),
                key="sample_nb",
                index=0,
                placeholder="Choisir...",
            )
        with col2:
            st.selectbox(
                "Classe de matériau",
                material_classes,
                key="material_class",
                index=None,
                placeholder="Choisir...",
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
            st.text_input(
                "Poids brut (kg)",
                key="gross_weight",
                placeholder="Séparez chaque pesée par des espaces",
            )
        with col5:
            st.button(
                "✅ Ajouter la pesée",
                on_click=add_weighing,
                key="add_weighing_button",
            )

    # with st.container(border=True):
    #     st.markdown("### Entrée de pesée")
        
    #     # Row 1 — material class (full width, needs space)
    #     st.radio(
    #         "Classe de matériau",
    #         material_classes,
    #         key="material_class",
    #         index=None,
    #         horizontal=False,
    #     )

    #     # Row 2 — the rest of the fields
    #     col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
    #     with col1:
    #         st.selectbox(
    #             "Numéro de l'échantillon",
    #             list(range(1, st.session_state["saved_nb_sample"] + 1)),
    #             key="sample_nb", index=None, placeholder="Choisir...",
    #         )
    #     with col2:
    #         st.selectbox(
    #             "Contenant utilisé",
    #             st.session_state["df_containers"]["Contenant"].tolist(),
    #             disabled=st.session_state["df_containers"].empty,
    #             key="container_used", index=None, placeholder="Choisir...",
    #         )
    #     with col3:
    #         st.text_input(
    #             "Poids brut (kg)",
    #             key="gross_weight",
    #             placeholder="Séparez chaque pesée par des espaces",
    #         )
    #     with col4:
    #         st.button("✅ Ajouter la pesée", on_click=add_weighing, key="add_weighing_button")

    # Weighings table with per-row delete
    df_w = st.session_state["df_weighings"]
    if df_w.empty:
        st.info("Aucune pesée enregistrée.")
    else:
        h_cols = st.columns([1, 2, 2, 2, 2, 1.5, 1.5, 1])
        for col, label in zip(h_cols, ["#échant.", "Début", "Fin", "Classe", "Contenant", "Brut (kg)", "Net (kg)", ""]):
            col.markdown(f"**{label}**")
        for idx, row in df_w.iterrows():
            r = st.columns([1, 2, 2, 2, 2, 1.5, 1.5, 1])
            r[0].write(int(row["N° échantillon"]))
            r[1].write(str(row["Début"]))
            r[2].write(str(row["Fin"]))
            r[3].write(row["Classe de matériau"])
            r[4].write(row["Contenant utilisé"])
            r[5].write(f"{row['Poids brut']:.3f}")
            r[6].write(f"{row['Poids net']:.3f}")
            if r[7].button("✕", key=f"del_w_{idx}"):
                delete_weighing(idx)
                st.rerun()


# ── TAB 4 : SUMMARY ───────────────────────────────────────────────────────────
with tab_summary:
    st.subheader("Résumé de la caractérisation")

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
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
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
        if st.button("☁️ Sauvegarder dans le Cloud (Dropbox)"):
            with st.spinner("Envoi en cours..."):
                if upload_to_dropbox(excel_data, filename):
                    st.success(f"Fichier '{filename}' sauvegardé avec succès sur Dropbox !")
    else:
        st.info("Aucune pesée enregistrée — l'export sera disponible ici.")