import streamlit as st
import datetime as dt
import pandas as pd
import matplotlib.pyplot as plt
import io

MATERIALS_FILE = "list_classes.csv"


def load_material_classes(csv_file: str) -> list[str]:
    df = pd.read_csv(csv_file, encoding="utf-8")

    # if df.shape[1] != 1:
    #     raise ValueError("Le fichier list_classes.csv doit contenir une seule colonne.")

    column_name = df.columns[0]
    # print(column_name)
    # print(df)

    return (
        df[column_name]
        .dropna()
        .astype(str)
        .str.strip()
        .loc[lambda s: s != ""]
        .tolist()
    )


material_classes = load_material_classes(MATERIALS_FILE)


# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Résultat de caractérisation",
    page_icon="⚖️",
    layout="centered",
)


# ── SESSION STATE INIT ────────────────────────────────────────────────────────
if "error_message" not in st.session_state:
    st.session_state["error_message"] = ""

if "saved_operator_name" not in st.session_state:
    st.session_state["saved_operator_name"] = ""

if "saved_test_date" not in st.session_state:
    st.session_state["saved_test_date"] = dt.date.today()

if "saved_sensor_name" not in st.session_state:
    st.session_state["saved_sensor_name"] = "1"

if "saved_nb_sample" not in st.session_state:
    st.session_state["saved_nb_sample"] = 1

if "df_containers" not in st.session_state:
    st.session_state["df_containers"] = pd.DataFrame(
        columns=["Contenant", "Poids à vide"]
    )

if "df_collect_times" not in st.session_state:
    st.session_state["df_collect_times"] = pd.DataFrame(
        columns=["N° échantillon", "Début", "Fin"]
    )

if "df_weighings" not in st.session_state:
    st.session_state["df_weighings"] = pd.DataFrame(
        columns=[
            "N° échantillon",
            "Début",
            "Fin",
            "Classe de matériau",
            "Contenant utilisé",
            "Poids brut",
            "Poids net",
        ]
    )



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
    if not container_name or container_name == "Choisir...":
        return 0.0
    row = st.session_state["df_containers"].loc[
        st.session_state["df_containers"]["Contenant"] == container_name
    ]
    if row.empty:
        return 0.0
    return float(row.iloc[0]["Poids à vide"])


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
    existing = st.session_state["df_collect_times"]

    for i in range(nb_sample):
        sample_id = i + 1
        row = existing.loc[existing["N° échantillon"] == sample_id]
        start = row.iloc[0]["Début"] if not row.empty else dt.time(0, 0, 0)
        end   = row.iloc[0]["Fin"]   if not row.empty else dt.time(0, 0, 0)

        if f"_hs{i}" not in st.session_state:
            st.session_state[f"_hs{i}"] = start.hour
        if f"_ms{i}" not in st.session_state:
            st.session_state[f"_ms{i}"] = start.minute
        if f"_ss{i}" not in st.session_state:
            st.session_state[f"_ss{i}"] = start.second
        if f"_he{i}" not in st.session_state:
            st.session_state[f"_he{i}"] = end.hour
        if f"_me{i}" not in st.session_state:
            st.session_state[f"_me{i}"] = end.minute
        if f"_se{i}" not in st.session_state:
            st.session_state[f"_se{i}"] = end.second


def save_metadata() -> None:
    nb_sample = int(st.session_state["_nb_sample"])
    rows = []
    for i in range(nb_sample):
        rows.append({
            "N° échantillon": i + 1,
            "Début": dt.time(
                st.session_state[f"_hs{i}"],
                st.session_state[f"_ms{i}"],
                st.session_state[f"_ss{i}"],
            ),
            "Fin": dt.time(
                st.session_state[f"_he{i}"],
                st.session_state[f"_me{i}"],
                st.session_state[f"_se{i}"],
            ),
        })
    st.session_state["saved_operator_name"] = st.session_state["_operator_name"]
    st.session_state["saved_test_date"]     = st.session_state["_test_date"]
    st.session_state["saved_sensor_name"]   = st.session_state["_sensor_name"]
    st.session_state["saved_nb_sample"]     = nb_sample
    st.session_state["df_collect_times"]    = pd.DataFrame(rows)
    st.session_state["error_message"]       = ""


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
    # FIX: delete by name instead of always removing the last row
    st.session_state["df_containers"] = (
        st.session_state["df_containers"]
        .loc[st.session_state["df_containers"]["Contenant"] != container_name]
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

    if sample_id in (None, "Choisir..."):
        st.session_state["error_message"] = "Veuillez choisir un numéro d'échantillon."
        return
    if material_class in (None, "Choisir..."):
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
                f"Le poids net calculé est négatif ({net_weight:.2f} kg). "
                "Vérifiez le contenant sélectionné et les poids saisis."
            )
            return
        new_rows.append({
            "N° échantillon":  sample_id,
            "Début":           times["Début"],
            "Fin":             times["Fin"],
            "Classe de matériau": material_class,
            "Contenant utilisé": (
                "" if container_used in (None, "Choisir...") else container_used
            ),
            "Poids brut": gross_weight,
            "Poids net":  net_weight,
        })

    st.session_state["df_weighings"] = pd.concat(
        [st.session_state["df_weighings"], pd.DataFrame(new_rows)],
        ignore_index=True,
    )

    # FIX: reset to None so selectboxes return to blank placeholder state
    st.session_state["sample_nb"]      = None
    st.session_state["material_class"] = None
    st.session_state["container_used"] = None
    st.session_state["gross_weight"]   = ""
    st.session_state["error_message"]  = ""


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
    buf = io.BytesIO()

    df = st.session_state["df_weighings"].copy()
    sensor = st.session_state["saved_sensor_name"]
    date   = st.session_state["saved_test_date"]

    # Aggregate: one row per sample × material class
    df_agg = (
        df.groupby(["N° échantillon", "Classe de matériau"], as_index=False)
        .agg(Début=("Début", "first"), Fin=("Fin", "first"), Poids_net=("Poids net", "sum"))
    )

    sample_totals = df_agg.groupby("N° échantillon")["Poids_net"].sum().rename("Masse totale échantillon")
    df_agg = df_agg.merge(sample_totals, left_on="N° échantillon", right_index=True, how="left")
    df_agg["%  total mass sample"] = df_agg["Poids_net"] / df_agg["Masse totale échantillon"] * 100
    df_agg["sensor name"] = sensor
    df_agg["date"]        = date

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:

        # ── Sheet 1: global summary ───────────────────────────────────────────
        sheet1 = df_agg[[
            "sensor name", "date",
            "N° échantillon", "Début", "Fin",
            "Classe de matériau", "Poids_net", "%  total mass sample",
        ]].rename(columns={
            "N° échantillon":       "sample number",
            "Début":                "start time",
            "Fin":                  "end time",
            "Classe de matériau":   "Material class",
            "Poids_net":            "Net weight",
        })

        total_row = pd.DataFrame([{
            "sensor name": sensor, "date": date,
            "sample number": "TOTAL", "start time": "", "end time": "",
            "Material class": "", "Net weight": sheet1["Net weight"].sum(),
            "%  total mass sample": 100.0,
        }])
        sheet1 = pd.concat([sheet1, total_row], ignore_index=True)
        sheet1.to_excel(writer, sheet_name="Global results", index=False)

        # ── One sheet per sample ──────────────────────────────────────────────
        sample_ids = sorted(df_agg["N° échantillon"].unique())
        for sample_id in sample_ids:
            df_s = df_agg[df_agg["N° échantillon"] == sample_id].iloc[0]
            start_time = df_s["Début"]
            end_time   = df_s["Fin"]

            # Collection times block (2 rows written manually via a small df)
            times_df = pd.DataFrame([
                {"": "Start time", " ": str(start_time)},
                {"": "End time",   " ": str(end_time)},
            ])

            # Material class table for this sample
            df_sample = df_agg[df_agg["N° échantillon"] == sample_id][[
                "Classe de matériau", "Poids_net", "%  total mass sample",
            ]].rename(columns={
                "Classe de matériau":          "Material class",
                "Poids_net":                   "Net weight (kg)",
                "%  total mass sample": "% of sample total",
            }).copy()

            total_row_s = pd.DataFrame([{
                "Material class": "TOTAL",
                "Net weight (kg)": df_sample["Net weight (kg)"].sum(),
                "% of sample total": 100.0,
            }])
            df_sample = pd.concat([df_sample, total_row_s], ignore_index=True)

            sheet_name = f"Sample {int(sample_id)}"
            times_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)
            df_sample.to_excel(writer, sheet_name=sheet_name, index=False, startrow=len(times_df) + 2)

    buf.seek(0)
    return buf


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

        with r1c1:
            st.text_input("Nom", placeholder="Entrez votre nom", key="_operator_name")
        with r1c2:
            st.date_input("Date du jour", key="_test_date")
        with r1c3:
            st.selectbox("Nom du capteur", ("1", "2"), key="_sensor_name")
        with r1c4:
            # FIX: added value=1 and format="%d" to make integer intent explicit
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
                min_value=0.0, step=0.1,
                key="container_weight",
            )
        with col3:
            st.button(
                "✅ Ajouter contenant",
                use_container_width=True,
                on_click=add_container,
                key="add_container_button",
            )

    # FIX: show a delete button per row instead of a single "remove last" button
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
                index=None,
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

        disable_containers = st.session_state["df_containers"].empty
        with col3:
            st.selectbox(
                "Contenant utilisé",
                st.session_state["df_containers"]["Contenant"].tolist(),
                disabled=disable_containers,
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

    st.dataframe(st.session_state["df_weighings"], hide_index=True)


# ── TAB 4 : SUMMARY ───────────────────────────────────────────────────────────
# FIX: removed `if tab_summary.open:` (invalid attribute) and the nested
# `with tab_summary:`. Everything now sits inside one `with tab_summary:` block.
with tab_summary:
    st.subheader("Résumé de la caractérisation")

    df_summary_by_material = summarize_by_material(st.session_state["df_weighings"])
    total_net_mass = df_summary_by_material["Poids net"].sum() if not df_summary_by_material.empty else 0.0

    st.write(f"### Résumé global — masse totale : {total_net_mass:.2f} kg")
    st.dataframe(df_summary_by_material, hide_index=True)

    # FIX: guard against empty data before plotting
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
        df_sample_summary  = summarize_by_material(df_sample)
        total_sample_net   = df_sample_summary["Poids net"].sum() if not df_sample_summary.empty else 0.0
        st.markdown(f"#### Échantillon {int(sample_id)} — masse totale : {total_sample_net:.2f} kg")
        st.dataframe(df_sample_summary, hide_index=True)
        st.divider()

    # st.divider()
    if not st.session_state["df_weighings"].empty:
        st.download_button(
            "⬇️ Télécharger le fichier Excel",
            data=build_excel_export(),
            file_name="resultats_caracterisation.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.info("Aucune pesée enregistrée — l'export sera disponible ici.")