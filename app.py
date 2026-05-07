import streamlit as st
import datetime as dt
import pandas as pd
import matplotlib.pyplot as plt
import os

MATERIALS_FILE = "list_classes.txt"
with open(MATERIALS_FILE, "r", encoding="utf-8") as f:
    material_classes = [line.strip() for line in f if line.strip()]


def go_to_tab(tab_name: str) -> None:
    st.session_state.main_tabs = tab_name


if 'error_typo' not in st.session_state:
    st.session_state['error_typo'] = False

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

    return {
        "Début": row.iloc[0]["Début"],
        "Fin": row.iloc[0]["Fin"],
    }


def get_container_weight(container_name: str) -> float:
    if not container_name or container_name == "Choisir...":
        return 0.0

    row = st.session_state["df_containers"].loc[
        st.session_state["df_containers"]["Contenant"] == container_name
    ]

    if row.empty:
        return 0.0

    return float(row.iloc[0]["Poids à vide"])



def add_weighing():
    gross_weight_text = st.session_state["gross_weight"].strip()

    if not check_entry_typo(gross_weight_text):
        st.session_state["error_typo"] = True
        return

    sample_id = st.session_state["sample_nb"]
    material_class = st.session_state["material_class"]
    container_used = st.session_state["container_used"]

    if sample_id == "Choisir..." or material_class == "Choisir...":
        st.session_state["error_typo"] = True
        return

    times = get_sample_collect_times(sample_id)
    if times is None:
        st.session_state["error_typo"] = True
        return

    tare_weight = get_container_weight(container_used)

    weights = [float(w.replace(",", ".")) for w in gross_weight_text.split()]
    # weights = [0]
    new_rows = []

    for gross_weight in weights:
        net_weight = gross_weight - tare_weight

        new_rows.append(
            {
                "N° échantillon": sample_id,
                "Début": times["Début"],
                "Fin": times["Fin"],
                "Classe de matériau": material_class,
                "Contenant utilisé": (
                    "" if container_used == "Choisir..." else container_used
                ),
                "Poids brut": gross_weight,
                "Poids net": net_weight,
            }
        )

    df_new = pd.DataFrame(new_rows)

    st.session_state["df_weighings"] = pd.concat(
        [st.session_state["df_weighings"], df_new],
        ignore_index=True,
    )

    st.session_state["error_typo"] = False
    st.session_state["sample_nb"] = "Choisir..."
    st.session_state["material_class"] = "Choisir..."
    st.session_state["container_used"] = "Choisir..."
    st.session_state["gross_weight"] = ""

def add_container():
    if st.session_state["container_name"]:
        df_temp = pd.DataFrame({
            "Contenant": [st.session_state["container_name"]],
            "Poids à vide": [st.session_state["container_weight"]],
        })

        st.session_state.df_containers = pd.concat(
            [st.session_state.df_containers, df_temp],
            axis=0,
            ignore_index=True,
                        )
        st.session_state["container_name"] = ""
        st.session_state["container_weight"] = 0.0


# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Résultat de caractérisation",
    page_icon="⚖️",
    layout="centered",
)

# ── TITLE ─────────────────────────────────────────────────────────────────────
st.title("Résultat de caractérisation")
#st.caption("App skeleton for layout and block placement")

# ── TABS ──────────────────────────────────────────────────────────────────────
if "main_tabs" not in st.session_state:
    st.session_state["main_tabs"] = "Métadonnées"
    
tab_metadata, tab_containers, tab_weighing, tab_summary = st.tabs(
    ["Métadonnées", "Contenants", "Résultats de pesée", "Résumé de la caractérisation"], key="main_tabs", on_change="rerun"
)

# ── session_state ─────────────────────────────────────────────────────────────
# if "nb_sample" not in st.session_state:
#     st.session_state["nb_sample"] = 1

if "main_tabs" not in st.session_state:
    st.session_state["main_tabs"] = "Métadonnées"

if "df_containers" not in st.session_state:
    st.session_state["df_containers"] = pd.DataFrame(columns=["Contenant", "Poids à vide"])

if "df_collect_times" not in st.session_state:
    st.session_state["df_collect_times"] = pd.DataFrame(columns=["N° échantillon", "Début", "Fin"])

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


# ── TAB 1 : METADATA ──────────────────────────────────────────────────────────
with tab_metadata:
    st.subheader("Métadonnées")

    with st.container(border=True):
        st.markdown("### Informations spécifiques au test")
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)

        with r1c1:
            st.text_input("Nom", placeholder="Entrez votre nom")

        with r1c2:
            st.date_input("Date du jour", key="test_date")

        with r1c3:
            st.selectbox("Nom du capteur", ("1", "2"), key="sensor_name")

        with r1c4:
            st.number_input("Nombre d'échantillons", step=1, min_value=1, key="nb_sample")

        #st.space()
        
        
        for i in range(st.session_state["nb_sample"]):
            st.divider()
            st.subheader(f"Prélèvement de l'échantillon {i + 1}")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.text("Heure de début :")
            with c2:
                h1 = st.selectbox("heures", list(range(24)), width=100, key = f"hs{i}")
                #st.number_input("HH", min_value=0, max_value=23, step=1, width=50, key=f"start_h_{i}")
            with c3:
                m1 = st.selectbox("minutes", list(range(60)), width=100, key = f"ms{i}")
                #st.number_input("MM", min_value=0, max_value=59, step=1, width=50, key=f"start_m_{i}")
            with c4:
                s1 = st.selectbox("secondes", list(range(60)), width=100, key = f"ss{i}")
                #st.number_input("SS", min_value=0, max_value=59, step=1, width=50, key=f"start_s_{i}")

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.text("Heure de fin :")
            with c2:
                h2 = st.selectbox("heures", list(range(24)), width=100, key = f"he{i}")
                #st.number_input("HH", min_value=0, max_value=23, step=1, width=50, key=f"end_h_{i}")
            with c3:
                m2 = st.selectbox("minutes", list(range(60)), width=100, key = f"me{i}")
                #st.number_input("MM", min_value=0, max_value=59, step=1, width=50, key=f"end_m_{i}")
            with c4:
                s2 = st.selectbox("secondes", list(range(60)), width=100, key = f"se{i}")
                #st.number_input("SS", min_value=0, max_value=59, step=1, width=50, key=f"end_s_{i}")
            
            start_time = dt.time(h1, m1, s1)
            end_time = dt.time(h2, m2, s2)
            st.session_state["df_collect_times"].loc[i] = {
                "N° échantillon": i + 1,
                "Début": start_time,
                "Fin": end_time,
            }

    # col_left, col_right = st.columns([4, 1])
    # with col_right:
    #     st.button("Définir les contenants 👉", on_click=go_to_tab, args=("Contenants",), use_container_width=True)

    st.dataframe(st.session_state["df_collect_times"], hide_index=True)
    # st.write(st.session_state)


# ── TAB 2 : CONTAINERS INFORMATION ───────────────────────────────────────────
with tab_containers:
    st.subheader("Contenants")

    #if "df_containers" not in st.session_state:
    #    st.session_state.df_containers = pd.DataFrame(columns=["Contenant", "Poids à vide"])

    with st.container(border=True):
        st.markdown("### Ajout de contenants")
        st.caption("Ajoutez les contenants utilisés pour peser les matériaux. Si vous n'avez pas utilisé de contenants, laisser cette section vide.")
        

        col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")

        with col1:
            container_name = st.text_input("Identificateur du contenant", placeholder="Veuillez renseigner le nom du contenant", key="container_name")

        with col2:
            container_weight = st.number_input("Poids du contenant vide (kg)", min_value=0.0, step=0.1, key="container_weight")

        with col3:
            st.button("✅ Ajouter contenant", use_container_width=True, on_click=add_container)

        with col4:
            if st.button("⛔ Supprimer le dernier contenant", use_container_width=True):
                if not st.session_state.df_containers.empty:
                    st.session_state.df_containers = (
                        st.session_state.df_containers.iloc[:-1].reset_index(drop=True)
                    )
            
    st.dataframe(st.session_state.df_containers, hide_index=True)


    # col_left, col_right = st.columns([4, 1])
    # with col_right:
    #     st.button("Renseigner les informations de pesée 👉", on_click=go_to_tab, args=("Résultats de pesée",), use_container_width=True)

    # st.write(st.session_state)

# ── TAB 3 : WEIGHING INFORMATIONS ────────────────────────────────────────────
with tab_weighing:
    st.subheader("Résultats de pesée")

    with st.container(border=True):
        st.markdown("### Entrée de pesée")
        col1, col2, col3, col4, col5 = st.columns(5, vertical_alignment="bottom")

        with col1:
            st.selectbox("Numéro de l'échantillon", ["Choisir..."] + list(range(1, st.session_state["nb_sample"] + 1)), key="sample_nb", index=None)
        with col2:
            st.selectbox("Classe de matériau", ["Choisir..."] + material_classes, key="material_class", index=None)

        disable_containers = True if st.session_state.df_containers.empty else False

        with col3:
            st.selectbox("Contenant utilisé", ["Choisir..."] + st.session_state.df_containers["Contenant"].tolist(), disabled=disable_containers, key="container_used", index=None if not disable_containers else 0)

        with col4:
            st.text_input("Poids brut (kg)", key="gross_weight", placeholder="Séparez chaque pesée par des espaces ")
        with col5:
            st.button("✅ Ajouter la pesée", on_click=add_weighing)
    if st.session_state["error_typo"]:
        st.warning("Veuillez vérifier la façon dont vous avez entré les pesées. Est ce que poids sont bien séparés par des espaces ?")

    # col_left, col_right = st.columns([4, 1])
    # with col_right:
    #     st.button("Visualiser l'échantillon en cours 👉", on_click=go_to_tab, args=("Résumé de la pesée",), use_container_width=True)
    st.dataframe(st.session_state["df_weighings"], hide_index=True)


    # st.write(st.session_state)


# ── TAB 4 : SUMMARY ───────────────────────────────────────────────────────────
if tab_summary.open:
    with tab_summary:
        # st.subheader("Résumé de la pesée")

        df_summary_by_material = (
            st.session_state["df_weighings"]
            .groupby("Classe de matériau", as_index=False)[["Poids net"]]
            .sum()
        )

        total_net_mass = df_summary_by_material["Poids net"].sum()

        df_summary_by_material["Pourcentage de la masse totale"] = (
            df_summary_by_material["Poids net"] / total_net_mass * 100
            if total_net_mass > 0
            else 0.0
        )

        st.write(f"### Résumé global — masse totale : {total_net_mass:.2f} kg")
        st.dataframe(df_summary_by_material, hide_index=True)

        with st.container(border=True):
            if not df_summary_by_material.empty:
                fig, ax = plt.subplots()

                ax.pie(
                    df_summary_by_material["Pourcentage de la masse totale"],
                    labels=df_summary_by_material["Classe de matériau"],
                    autopct="%1.1f%%",
                )
                ax.set_title("Répartition par classe de matériau")

                st.pyplot(fig)

        st.divider()
        st.markdown("### Résumé par échantillon")

        for sample_id in sorted(st.session_state["df_weighings"]["N° échantillon"].dropna().unique()):
            
            df_sample = st.session_state["df_weighings"][
                st.session_state["df_weighings"]["N° échantillon"] == sample_id
            ]

            df_sample_summary = (
                df_sample
                .groupby("Classe de matériau", as_index=False)[["Poids net"]]
                .sum()
            )

            total_sample_net_mass = df_sample_summary["Poids net"].sum()

            df_sample_summary["Pourcentage de la masse totale"] = (
                df_sample_summary["Poids net"] / total_sample_net_mass * 100
                if total_sample_net_mass > 0
                else 0.0
            )

            st.markdown(f"#### Échantillon {int(sample_id)} — masse totale : {total_sample_net_mass:.2f} kg")
            st.dataframe(df_sample_summary, hide_index=True)
            st.divider()



    df_export = st.session_state["df_weighings"].copy()

    sample_totals = (
        df_export.groupby("N° échantillon")["Poids net"]
        .sum()
        .rename("Masse totale échantillon")
    )

    df_export = df_export.merge(
        sample_totals,
        left_on="N° échantillon",
        right_index=True,
        how="left",
    )

    df_export["Ratio de la classe dans la masse totale de l'échantillon"] = (
        df_export["Poids net"] / df_export["Masse totale échantillon"] * 100
    )

    df_export["Nom du capteur"] = st.session_state["sensor_name"]
    df_export["Date"] = st.session_state["test_date"]

    df_export = df_export[
        [
            "Nom du capteur",
            "Date",
            "N° échantillon",
            "Début",
            "Fin",
            "Classe de matériau",
            "Poids net",
            "Ratio de la classe dans la masse totale de l'échantillon",
        ]
    ].rename(
        columns={
            "Nom du capteur": "sensor name",
            "Date": "date",
            "N° échantillon": "sample number",
            "Début": "start time",
            "Fin": "end time",
            "Classe de matériau": "Material class",
            "Poids net": "Net weight",
            "Ratio de la classe dans la masse totale de l'échantillon": "Ratio of the class in the sample total mass",
        }
    )

    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, "resultats_caracterisation.xlsx")
    df_export.to_excel(output_file, index=False)


    with open(output_file, "rb") as f:
        st.download_button(
            "Télécharger le fichier Excel",
            data=f,
            file_name=output_file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )