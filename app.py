import streamlit as st
import pandas as pd

# ----------------- READ VERSION (FOR CACHE CONTROL) -----------------
try:
    with open("version.txt", "r") as f:
        VERSION = f.read().strip()
except FileNotFoundError:
    VERSION = "v1.1.0"

# ----------------- APP HEADER -----------------
st.title("ET 2-Layer Threshold Lab Tool")
st.caption(f"Version: {VERSION}")

st.markdown(
    """
This tool estimates **metabolic** and **autonomic** stress during an incremental
exercise test using a two-layer ET model:

- **VO₂-ET layer** reflects *metabolic load*.
- **HRV-ET layer** reflects *autonomic load*.

Only final ET-based alerts and scientific interpretation are displayed.
"""
)

# ----------------- SECTION 1: STEP DATA INPUT -----------------
st.header("1. Step data (VO₂ and HRV)")

st.markdown(
    """
Paste your data below. Each line = one step.

Use the format:

`VO2  HRV`

Examples:
Spaces, tabs or commas between numbers are all accepted.
"""
)

raw_text = st.text_area(
    "VO₂ (ml/kg/min) and HRV (ms) per step",
    value="20 78\n30 70\n36 60\n42 48\n50 36",
    height=200,
)

analyze = st.button("Analyze test")

# ----------------- HELPER FUNCTIONS -----------------
def parse_input(text: str) -> pd.DataFrame:
    rows = []
    for idx, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        # Split by space, tab, or comma
        parts = [p for p in line.replace(",", " ").split() if p]
        if len(parts) < 2:
            continue
        try:
            vo2 = float(parts[0])
            hrv = float(parts[1])
        except ValueError:
            continue
        rows.append({"Step": idx, "VO2_current": vo2, "HRV_current": hrv})
    return pd.DataFrame(rows)


def compute_et_layers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute ET for VO2 and HRV layers.
    Normalisation is internal:
    - VO2 is normalised by max VO2 in the test.
    - HRV is normalised by max HRV in the test.
    """
    if df.empty:
        return df

    vo2max = df["VO2_current"].max()
    hrv_rest = df["HRV_current"].max()

    e_vo2_list = []
    e_hrv_list = []

    for _, row in df.iterrows():
        vo2 = float(row["VO2_current"])
        hrv = float(row["HRV_current"])

        # VO2 layer: relative intensity vs max VO2 of this test
        x_vo2 = vo2 / vo2max if vo2max > 0 else 0.0
        if x_vo2 < 0:
            x_vo2 = 0.0
        e_vo2 = 1.0 - x_vo2**2

        # HRV layer: relative HRV loss vs max HRV of this test
        x_hrv = (hrv_rest - hrv) / hrv_rest if hrv_rest > 0 else 0.0
        if x_hrv < 0:
            x_hrv = 0.0
        if x_hrv > 1:
            x_hrv = 1.0
        e_hrv = 1.0 - x_hrv**2

        e_vo2_list.append(e_vo2)
        e_hrv_list.append(e_hrv)

    df_out = df.copy()
    df_out["E_VO2"] = e_vo2_list
    df_out["E_HRV"] = e_hrv_list
    return df_out


def classify_overall(df_et: pd.DataFrame):
    """
    Overall ET status based on the minimum ET value across both layers.
    """
    min_e_vo2 = df_et["E_VO2"].min()
    min_e_hrv = df_et["E_HRV"].min()
    min_e = min(min_e_vo2, min_e_hrv)

    if min_e >= 0.70:
        status = "GREEN"
    elif min_e >= 0.40:
        status = "YELLOW"
    else:
        status = "RED"

    # Which layer is more limiting?
    if min_e_hrv < min_e_vo2 - 0.05:
        limiter = "autonomic"
    elif min_e_vo2 < min_e_hrv - 0.05:
        limiter = "metabolic"
    else:
        limiter = "balanced"

    return status, min_e, min_e_vo2, min_e_hrv, limiter


# ----------------- SECTION 2: RESULTS -----------------
st.header("2. Results")

if analyze:
    df_raw = parse_input(raw_text)

    if df_raw.empty:
        st.error("No valid data found. Please paste VO₂ and HRV values (two numbers per line).")
    else:
        df_et = compute_et_layers(df_raw)

        status, min_e, min_e_vo2, min_e_hrv, limiter = classify_overall(df_et)

        # ---------- STATUS PANEL ----------
        col_a, col_b = st.columns([1, 2])
        with col_a:
            if status == "GREEN":
                st.success("OVERALL STATUS: GREEN")
            elif status == "YELLOW":
                st.warning("OVERALL STATUS: YELLOW")
            else:
                st.error("OVERALL STATUS: RED")

            st.write(f"Minimum ET across steps (both layers): **{min_e:.3f}**")

        with col_b:
            st.markdown("**Scientific interpretation**")
            if status == "GREEN":
                st.markdown(
                    """
- ET depression is mild → biological time is largely preserved across the protocol.
- Metabolic and autonomic systems buffer the incremental load with adequate reserve.
- This pattern is compatible with sustainable training for most well-conditioned athletes.
                    """
                )
            elif status == "YELLOW":
                st.markdown(
                    """
- ET shows moderate contraction → regulation works harder to stabilise internal milieu.
- Recurrent YELLOW patterns may accumulate hidden fatigue (“time debt”) if recovery is suboptimal.
- Suitable for overload blocks, but training density and recovery windows must be tightly controlled.
                    """
                )
            else:  # RED
                st.markdown(
                    """
- ET exhibits marked contraction, indicating high integrated stress on metabolic and autonomic systems.
- Such responses are close to or beyond individual thresholds; frequent repetition increases risk of maladaptation.
- This zone should be reserved for controlled testing or occasional peak sessions under professional supervision.
                    """
                )

            if limiter == "autonomic":
                st.markdown(
                    "- **Autonomic ET drops earlier and deeper than metabolic ET → autonomic regulation is the primary limiting factor in this test.**"
                )
            elif limiter == "metabolic":
                st.markdown(
                    "- **Metabolic ET drops earlier and deeper than autonomic ET → peripheral/metabolic capacity is the main limiter.**"
                )
            else:
                st.markdown(
                    "- **Both layers contract in parallel → metabolic and autonomic loads are well coupled in this protocol.**"
                )

        # ---------- OPTIONAL DETAILS ----------
        with st.expander("Show ET values per step"):
            st.dataframe(
                df_et[["Step", "VO2_current", "HRV_current", "E_VO2", "E_HRV"]],
                use_container_width=True,
            )
else:
    st.info("Paste VO₂ and HRV data, then press **Analyze test** to compute ET status.")
