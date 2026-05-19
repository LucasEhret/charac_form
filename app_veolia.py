import streamlit as st
import datetime as dt
import pandas as pd
import matplotlib.pyplot as plt
import io
import dropbox
import zipfile 
import json
import uuid
from pathlib import Path
from streamlit_extras.card_selector import card_selector

import tempfile
TEMP_DIR = Path(tempfile.gettempdir()) / "wastechar_sessions"
TEMP_DIR.mkdir(exist_ok=True)

DEV_MODE = False


MATERIALS_FILE = ".streamlit/ressources/list_classes.csv"

SENSORS_FILE = ".streamlit/ressources/list_sensors.csv"

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
    "Image": pd.Series(dtype="object"),
    "image_uploader_key": 0,
    "saved_workflow" : 0,
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
        "N° échantillon": pd.Series(dtype="str"),
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


# ── SESSION PERSISTENCE (F5 protection) ───────────────────────────────────────
def _session_file() -> Path:
    return TEMP_DIR / f"{st.query_params.get('session', 'nosession')}.json"


def save_session() -> None:
    """Write current session to a temp file. Called after every data action."""
    try:
        data = {
            "df_weighings": (
                st.session_state["df_weighings"]
                .drop(columns=["Image"], errors="ignore")
                .to_json(orient="records")
            ),
            "df_containers":    st.session_state["df_containers"].to_json(orient="records"),
            "df_collect_times": (
                st.session_state["df_collect_times"]
                .astype({"Date": str}, errors="ignore")
                .to_json(orient="records")
            ),
            "metadata": {
                "workflow": st.session_state.get("saved_workflow", 0),
                "operator":  st.session_state.get("saved_operator_name", ""),
                "sensor":    st.session_state.get("saved_sensor_name", ""),
                "nb_sample": st.session_state.get("saved_nb_sample", 1),
                "date":      str(st.session_state.get("saved_test_date", dt.date.today())),
            },
        }
        _session_file().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _restore_df(json_str: str, dtype_map: dict, date_cols: list = []) -> pd.DataFrame | None:
    """Parse a JSON string back to a DataFrame with correct types."""
    df = pd.read_json(io.StringIO(json_str))
    if df.empty:
        return None
    for col, dtype in dtype_map.items():
        if col in df.columns:
            df[col] = df[col].astype(dtype)
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col]).dt.date
    return df


def restore_session() -> None:
    """Load session from temp file if it exists. Called once on first load."""
    f = _session_file()
    if not f.exists():
        return
    try:
        data = json.loads(f.read_text(encoding="utf-8"))

        df_w = _restore_df(data["df_weighings"],
                           {"N° échantillon": str, "Poids brut": float, "Poids net": float})
        if df_w is not None:
            st.session_state["df_weighings"] = df_w

        df_c = _restore_df(data["df_containers"],
                           {"Contenant": str, "Poids à vide": float})
        if df_c is not None:
            st.session_state["df_containers"] = df_c

        df_t = _restore_df(data["df_collect_times"],
                           {"Echantillon": int, "Heure de début": str, "Heure de fin": str},
                           date_cols=["Date"])
        if df_t is not None:
            st.session_state["df_collect_times"] = df_t

        meta = data["metadata"]
        st.session_state["saved_operator_name"] = meta.get("operator", "")
        st.session_state["saved_sensor_name"]   = meta.get("sensor", sensor_list[0])
        st.session_state["saved_nb_sample"]     = int(meta.get("nb_sample", 1))
        wf = meta.get("workflow", 0)
        if isinstance(wf, str):
            _wf_titles = ["Standard", "Closed loop", "Split samples"]
            wf = _wf_titles.index(wf) if wf in _wf_titles else 0
        st.session_state["saved_workflow"] = wf
        st.session_state["saved_test_date"]     = dt.date.fromisoformat(
            meta.get("date", str(dt.date.today()))
        )
        # Force widget state to match restored metadata
        st.session_state.pop("_operator_name", None)
        st.session_state.pop("_sensor_name", None)
        st.session_state.pop("_nb_sample", None)
        st.session_state.pop("_test_date", None)
        st.session_state.pop("workflow_type", None)
    except Exception:
        pass  # corrupt file — start fresh silently


def clear_session() -> None:
    """Delete the temp file when the operator is done."""
    try:
        _session_file().unlink(missing_ok=True)
    except Exception:
        pass


# Generate or retrieve session token from URL
if "session" not in st.query_params:
    st.query_params["session"] = uuid.uuid4().hex

# Restore on first load only
if "session_restored" not in st.session_state:
    restore_session()
    st.session_state["session_restored"] = True

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


# def _clean_time_widget_keys(nb_sample: int) -> None:
#     i = nb_sample + 1
#     while f"_start_{i}_h" in st.session_state:
#         for key in (f"_start_{i}_h", f"_start_{i}_m", f"_start_{i}_s",
#                     f"_end_{i}_h",   f"_end_{i}_m",   f"_end_{i}_s"):
#             st.session_state.pop(key, None)
#         i += 1


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
    st.session_state["saved_operator_name"] = st.session_state["_operator_name"]
    st.session_state["saved_test_date"]     = st.session_state["_test_date"]
    save_session()


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
    if st.session_state["df_containers"].empty:
        st.session_state["df_containers"] = new_data
    else:
        st.session_state["df_containers"] = pd.concat(
            [st.session_state["df_containers"], new_data],
            ignore_index=True,
        )
    
    # Nettoyage et rafraîchissement
    st.session_state["container_name"]   = ""
    st.session_state["container_weight"] = 0.0
    st.session_state["container_error"] = ""
    save_session()


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
    save_session()


def add_weighing() -> None:
    gross_weight_text = st.session_state["gross_weight"].strip()

    if not check_entry_typo(gross_weight_text):
        st.session_state["weighing_error"] = (
            "Veuillez vérifier la saisie des poids bruts. "
            "Séparez les poids par des espaces, avec virgule ou point décimal."
        )
        return

    sample_ids = st.session_state["sample_nb"]
    material_class = st.session_state["material_class"]
    container_used = st.session_state["container_used"]

    if not sample_ids:
        st.session_state["weighing_error"] = "Veuillez choisir au moins un échantillon."
        return
    if material_class is None:
        st.session_state["weighing_error"] = "Veuillez choisir une classe de matériau."
        return
    

    new_rows = []
    # replace the loop over sample_ids and new_rows building with:
    sample_label = ", ".join(map(str, sorted(sample_ids)))
    times = get_sample_collect_times(sample_ids[0])

    tare_weight = get_container_weight(container_used)
    weights     = [float(w.replace(",", ".")) for w in gross_weight_text.split()]

    new_rows = []
    img_key = f"weighing_image_{st.session_state['image_uploader_key']}"
    for gross_weight in weights:
        net_weight = gross_weight - tare_weight
        if net_weight < 0:
            st.session_state["weighing_error"] = (
                f"Le poids net calculé est négatif ({net_weight:.3f} kg). "
                "Vérifiez le contenant sélectionné et les poids saisis."
            )
            return
        new_rows.append({
            "N° échantillon":     sample_label,
            "Début":              times["Début"] if times else None,
            "Fin":                times["Fin"]   if times else None,
            "Classe de matériau": material_class,
            "Contenant utilisé":  container_used or "",
            "Poids brut":         gross_weight,
            "Poids net":          net_weight,
            "Image":              st.session_state[img_key].read() if st.session_state.get(img_key) else None,
        })

    new_df = pd.DataFrame(new_rows)

    new_df["Poids brut"] = new_df["Poids brut"].astype(float)
    new_df["Poids net"] = new_df["Poids net"].astype(float)

    st.toast("Pesée ajoutée !", icon="⚖️")
    if st.session_state["df_weighings"].empty:
        st.session_state["df_weighings"] = new_df
    else:
        st.session_state["df_weighings"] = pd.concat(
            [st.session_state["df_weighings"], new_df],
            ignore_index=True,
        )

    # st.session_state["sample_nb"] = []
    st.session_state["material_class"] = None
    st.session_state["container_used"] = None
    st.session_state["gross_weight"]   = ""
    st.session_state["weighing_error"]  = ""
    st.session_state["image_uploader_key"] += 1
    save_session()


def delete_weighing(idx: int) -> None:
    st.session_state["df_weighings"] = (
        st.session_state["df_weighings"]
        .drop(index=idx)
        .reset_index(drop=True)
    )
    st.session_state["weighing_error"] = ""
    st.rerun()
    save_session()


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

            sample_id_list = [int(s.strip()) for s in str(sample_id).split(",")]
            time_rows = []
            for sid in sample_id_list:
                times = get_sample_collect_times(sid)
                if times:
                    time_rows.append({"Echantillon": sid, "Début": str(times["Début"]), "Fin": str(times["Fin"])})
                else:
                    time_rows.append({"Echantillon": sid, "Début": "", "Fin": ""})
            times_df = pd.DataFrame(time_rows)

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

            sheet_name = f"Sample {sample_id}"[:31]
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
            mode=dropbox.files.WriteMode.overwrite # type: ignore
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


def build_zip_export() -> io.BytesIO:
    buf = io.BytesIO()
    timestamp  = dt.datetime.now(dt.timezone(dt.timedelta(hours=2))).strftime("%Y%m%d_%H%M")
    sensor_name = st.session_state["saved_sensor_name"].replace(" ", "_")
    base_name  = f"Resultat_{FACILITY_NAME}_{sensor_name}_{timestamp}"

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:

        # Excel file
        excel_buf = build_excel_export()
        zf.writestr(f"{base_name}.xlsx", excel_buf.read())

        # Images — one per material class (first image found)
        df_w = st.session_state["df_weighings"]
        if "Image" in df_w.columns:
            seen_classes = set()
            for idx, row in df_w.iterrows():
                if isinstance(row["Image"], bytes) and row["Classe de matériau"] not in seen_classes:
                    seen_classes.add(row["Classe de matériau"])
                    class_safe = row["Classe de matériau"].replace(" ", "_").replace("/", "-")
                    img_name = f"images/{class_safe}.jpg"
                    zf.writestr(img_name, row["Image"])

    buf.seek(0)
    return buf


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:

    # ── Session info ──────────────────────────────────────────────────────────
    st.markdown(f"**{FACILITY_NAME}**")
    st.caption(
        f"🧑 {st.session_state.get('saved_operator_name') or 'Opérateur non renseigné'}  \n"
        f"📅 {st.session_state.get('saved_test_date') or '—'}  \n"
        f"📡 {st.session_state.get('saved_sensor_name') or '—'}  \n"
        f"⚖️ {len(st.session_state['df_weighings'])} pesée(s) enregistrée(s)"
    )

    st.divider()

    # ── Export ────────────────────────────────────────────────────────────────
    has_data = not st.session_state["df_weighings"].empty
    if has_data:
        timestamp   = dt.datetime.now().strftime("%Y%m%d_%H%M")
        sensor_name = st.session_state["saved_sensor_name"].replace(" ", "_")
        base_name   = f"Resultat_{FACILITY_NAME}_{sensor_name}_{timestamp}"
        zip_data    = build_zip_export()

        st.download_button(
            "⬇️ Télécharger (Excel + photos)",
            data=zip_data,
            file_name=f"{base_name}.zip",
            mime="application/zip",
            use_container_width=True,
        )
        if not DEV_MODE:
            if st.button("☁️ Sauvegarder sur Dropbox", use_container_width=True):
                with st.spinner("Envoi en cours..."):
                    if upload_to_dropbox(zip_data, f"{base_name}.zip"):
                        st.toast("Sauvegardé sur Dropbox !", icon="☁️")
        else:
            st.caption("DEV MODE — Dropbox désactivé.")
    else:
        st.caption("Aucune pesée enregistrée — l'export sera disponible ici.")

    st.divider()

    # ── Session management ────────────────────────────────────────────────────
    st.caption("Démarre une session vierge et efface toutes les données.")
    if st.button("🔄 Nouvelle session", use_container_width=True, type="secondary"):
        clear_session()
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.query_params.clear()
        st.rerun()

    st.divider()

    # ── Help & links ──────────────────────────────────────────────────────────
    st.link_button("🌐 wasteflow.ai", "https://wasteflow.ai", use_container_width=True)

    with st.expander("📖 Guide d'utilisation"):
        st.info("💡 Suivez les 4 onglets dans l'ordre.")
        st.markdown("""
**1️⃣ Métadonnées** — Nom, date, capteur et heures de prélèvement.

**2️⃣ Contenants** — Cartons avec leur poids à vide (tare).

**3️⃣ Résultats de pesée** — Classe, contenant, poids brut(s) séparés par des espaces.

**4️⃣ Résumé** — Visualisation et téléchargement du fichier final.
""")
        st.success("✅ Sauvegardez localement et dans le cloud.")

    st.divider()


# ── TITLE ─────────────────────────────────────────────────────────────────────
st.title(f"Caractérisation — {FACILITY_NAME}")

# ── TABS ──────────────────────────────────────────────────────────────────────
tab_metadata, tab_containers, tab_weighing, tab_summary = st.tabs(
    ["1️⃣ Métadonnées", "2️⃣ Contenants", "3️⃣ Résultats de pesée", "4️⃣ Résumé"]
)


# ── TAB 1 : METADATA ──────────────────────────────────────────────────────────
with tab_metadata:
    init_metadata_widget_state()
    with st.expander("⁉️ Guide d'utilisation", expanded=False):
        st.image(".streamlit/images/process carac.png", width='stretch')

        st.markdown("## Comment utiliser ce formulaire ?")
        st.info("💡 Suivez les 4 onglets dans l'ordre. Les données sont sauvegardées automatiquement à chaque saisie — vous ne pouvez pas perdre ce que vous avez entré.")

        st.markdown("---")

        st.markdown("### 1️⃣ Métadonnées — *cet onglet*")
        st.markdown("""
    Renseignez les informations générales du test **avant de commencer à peser**.

    | Champ | Quoi saisir |
    |---|---|
    | **Nom** | Votre prénom et nom |
    | **Date du jour** | La date du test (pré-remplie automatiquement) |
    | **Nom du capteur** | Le capteur WasteFlow associé à ce test |
    | **Nombre d'échantillons** | Le nombre de prélèvements effectués |

    Pour chaque échantillon, saisissez :
    - **La date du prélèvement** (si différente de la date du jour)
    - **L'heure de début et de fin** du prélèvement (HH / MM / SS)

    > ⚠️ Un champ laissé vide (`HH`, `MM`, `SS`) sera interprété comme `00`.
    """)

        st.markdown("---")

        st.markdown("### 2️⃣ Contenants")
        st.markdown("""
    Les contenants sont les cartons ou bacs utilisés pour peser les matériaux. Leur poids à vide (tare) sera automatiquement soustrait pour obtenir le **poids net** du matériau.

    **Comment faire :**
    1. Donnez un nom clair à chaque contenant (ex : `Carton A`, `Bac Bleu 1`)
    2. Pesez le contenant vide et saisissez son poids
    3. Cliquez sur **Ajouter contenant**

    > Si vous n'utilisez pas de contenant (pesée directe), laissez cet onglet vide — le poids brut sera alors considéré comme le poids net.
    """)

        st.markdown("---")

        st.markdown("### 3️⃣ Résultats de pesée")
        st.markdown("""
    C'est ici que vous saisissez les pesées, **une classe de matériau à la fois**.

    **Pour chaque pesée :**
    1. Sélectionnez le ou les **numéro(s) d'échantillon** concernés
    2. Sélectionnez la **classe de matériau**
    3. Sélectionnez le **contenant utilisé** (si applicable)
    4. Saisissez le ou les **poids bruts** en kg — séparez plusieurs valeurs par un espace (ex : `12.5 8.3`)
    5. Cliquez sur ✅ **Ajouter la pesée**

    **Erreurs courantes :**
    - Mauvais contenant sélectionné → supprimez la ligne avec le bouton `✕` et recommencez
    - Oubli d'échantillon → vous pouvez sélectionner plusieurs échantillons à la fois si la pesée est commune
    """)

        st.markdown("---")

        st.markdown("### 4️⃣ Résumé")
        st.markdown("""
    Une fois toutes vos pesées saisies, l'onglet **Résumé** vous donne :
    - Le tableau récapitulatif avec les masses nettes et pourcentages par classe
    - Un graphique de répartition
    - Un résumé par échantillon

    Téléchargez ensuite le fichier Excel avec le bouton **⬇️ Télécharger** et sauvegardez-le dans le cloud avec **☁️ Sauvegarder dans le Cloud**.
    """)
        st.success("✅ Sauvegardez toujours localement **et** dans le cloud pour éviter toute perte de données.")
    # st.subheader("Métadonnées")

    with st.container(border=True):
        
        
        st.subheader("Type de workflow")
        workflow = card_selector(
            [
                dict(title="Standard", icon="📦", description="Capteur Wasteflow -> Récolte échantillon -> Pesée"),
                dict(title="Closed loop", icon="🔄", description="Les matériaux sont réintroduits dans le process"),
                dict(title="Split samples", icon="✂️", description="Plusieurs récoltes d'échantillon à des heures différentes, ensuite mélangées en une seule pesée"),
            ], # type: ignore
            selection_mode="single",
            default=st.session_state.get("saved_workflow", 0),
            key="workflow_type",
        ) # type: ignore
        st.space()
        st.markdown("### Informations spécifiques au test")
        st.session_state["saved_workflow"] = workflow
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        with r1c1: st.text_input("Nom", placeholder="Entrez votre nom", key="_operator_name", on_change=save_metadata)
        with r1c2: st.date_input("Date du jour", key="_test_date", on_change=save_metadata)
        with r1c3: st.selectbox("Nom du capteur", sensor_list, key="_sensor_name", index=0, on_change=save_metadata)
        with r1c4:
            st.number_input(
                "Nombre d'échantillons",
                step=1, min_value=1, value=1, format="%d",
                key="_nb_sample",
            )

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
    st.write(st.session_state)

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
        st.warning("⚠️ Renseignez d'abord les heures de prélèvement dans l'onglet **Métadonnées**.")
    with st.container(border=True):
        if st.session_state["weighing_error"]:
            st.warning(st.session_state["weighing_error"])
        st.markdown("### Entrée de pesée")

        # Row 1 — selection fields
        col1, col2, col3 = st.columns(3, vertical_alignment="bottom")
        with col1:
            st.multiselect(
                "Numéro(s) d'échantillon",
                list(range(1, st.session_state["saved_nb_sample"] + 1)),
                key="sample_nb",
                placeholder="Choisir...",
                disabled=disable_weighing,
            )
        with col2:
            st.selectbox(
                "Classe de matériau",
                material_classes,
                key="material_class",
                index=None,
                placeholder="Choisir...",
                disabled=disable_weighing,
                accept_new_options=True,
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
        # Optional image
        img_file = st.file_uploader(
            "Photo du matériau (optionnel)",
            type=["jpg", "jpeg", "png"],
            key=f"weighing_image_{st.session_state['image_uploader_key']}",
        )
        if img_file:
            st.image(img_file, width=200)
        # Row 2 — weight input and submit
        col4, col5 = st.columns([3, 1], vertical_alignment="bottom")
        with col4:
            weights_input = st.text_input(
                "Poids brut (kg)",
                key="gross_weight",
                placeholder="Ex: 12.5 14.2 — séparez plusieurs pesées par un espace",
                disabled=disable_weighing,
            )
        with col5:
            disable_add_weight = not (st.session_state["sample_nb"] and st.session_state["material_class"])
            st.button(
                "✅ Ajouter la pesée",
                on_click=add_weighing,
                key="add_weighing_button",
                use_container_width=True,
                disabled=disable_add_weight,
            )


        if weights_input:
            if check_entry_typo(weights_input):
                vals = [float(w.replace(",", ".")) for w in weights_input.split()]
                st.caption(f"✅ {len(vals)} pesée(s) détectée(s) — Total brut : **{sum(vals):.3f} kg**")

    # Affichage du tableau
    df_w = st.session_state["df_weighings"]
    if df_w.empty:
        st.info("Aucune pesée enregistrée.")
    else:
        h_cols = st.columns([1, 2, 2, 1.5, 1.5, 1])
        labels = ["#échant.", "Classe", "Contenant", "Brut (kg)", "Net (kg)", ""]
        for col, label in zip(h_cols, labels):
            col.markdown(f"**{label}**")
            
        for idx, row in df_w.iterrows():
            r = st.columns([1, 2, 2, 1.5, 1.5, 1])
            r[0].write(row["N° échantillon"])
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
    if not st.session_state["df_weighings"].empty:
        timestamp   = dt.datetime.now(dt.timezone(dt.timedelta(hours=2))).strftime("%Y%m%d_%H%M")
        sensor_name = st.session_state["saved_sensor_name"].replace(" ", "_")
        base_name   = f"Resultat_{FACILITY_NAME}_{sensor_name}_{timestamp}"

        zip_data = build_zip_export()
        with st.container(border=True):
            st.subheader("Sauvegarde")
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "⬇️ Télécharger (Excel + photos)",
                    data=zip_data,
                    file_name=f"{base_name}.zip",
                    mime="application/zip",
                )
            with col2:
                if not DEV_MODE:
                    if st.button("☁️ Sauvegarder dans le Cloud (Dropbox)"):
                        with st.status("Envoi en cours...", expanded=True) as status:
                            st.write("Connexion à Dropbox...")
                            if upload_to_dropbox(zip_data, f"{base_name}.zip"):
                                status.update(label="✅ Sauvegardé sur Dropbox !", state="complete", expanded=False)
                            else:
                                status.update(label="❌ Échec de l'envoi", state="error")
                else:
                    st.info("DEV MODE — Dropbox upload désactivé.")
            if st.button("🗑️ Terminer et effacer la session"):
                clear_session()
                st.query_params.clear()
                st.rerun()
    else:
        st.info("Aucune pesée enregistrée — l'export sera disponible ici.")
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
                labels=df_summary_by_material["Classe de matériau"], # type: ignore
                autopct="%1.1f%%",
            )
            ax.set_title("Répartition par classe de matériau")
            st.pyplot(fig)
            plt.close(fig)
        else:
            st.info("Aucune pesée enregistrée — le graphique s'affichera ici.")

    # st.divider()
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
        st.markdown(f"#### Échantillon {sample_id} — masse totale : {total_sample_net:.2f} kg")
        st.dataframe(df_sample_summary, hide_index=True)
        st.divider()

