import streamlit as st
import pandas as pd
import numpy as np

# ----------------- READ VERSION (FOR CACHE CONTROL) -----------------
try:
    with open("version.txt", "r") as f:
        VERSION = f.read().strip()
except FileNotFoundError:
    VERSION = "v1.0.0"

# ----------------- APP HEADER -----------------
st.title("ET 2-Layer Threshold Lab Tool")
st.caption(f"Version: {VERSION}")

st.markdown(
    """
This tool estimates **metabolic** and **autonomic** thresholds from an incremental
exercise test using a two-layer ET model:

- **VO₂-ET layer** reflects *metabolic load*.
- **HRV-ET layer** reflects *autonomic load*.

All internal calculations follow the Lorentz-type ET mapping; only the final results
and scientific interpretation are shown here.
"""
)

# ----------------- SECTION 1: BASELINE CONFIG -----------------
st.header("1. Baseline configuration")

col1, col2, col3 = st.columns(3)
with col1:
    vo2max = st.number_input(
        "VO₂max (ml/kg/min)",
        min_value=10.0,
        max_value=90.0,
        value=60.0,
        step=1.0,
    )
with col2:
    hrv_rest = st.number_input(
        "HRV at rest (ms, e.g. RMSSD)",
        min_value=10.0,
        max_value=200.0,
        value=80.0,
        step=1.0,
    )
with col3:
    n_steps = st.number_input(
        "Number of test steps",
        min_value=3,
        max_value=10,
        value=5,
        step=1,
    )

st.markdown(
    "- VO₂max is used as the reference for **metabolic intensity**.\n"
    "- Resting HRV is used as the reference for **autonomic regulation**."
)

# ----------------- SECTION 2: STEP DATA INPUT -----------------
st.header("2. Step data")

# Default example protocol
default_steps = [
    {"Step": 1, "Label": "Very light",  "Duration_min": 3, "VO2_current": 20.0, "HRV_current": 78.0},
    {"Step": 2, "Label": "Light",       "Duration_min": 3, "VO2_current": 30.0, "HRV_current": 70.0},
    {"Step": 3, "Label": "Moderate",    "Duration_min": 3, "VO2_current": 36.0, "HRV_current": 60.0},
    {"Step": 4, "Label": "Heavy",       "Duration_min": 3, "VO2_current": 42.0, "HRV_current": 48.0},
    {"Step": 5, "Label": "Very heavy",  "Duration_min": 3, "VO2_current": 50.0, "HRV_current": 36.0},
]

# Resize list to match chosen n_steps
if n_steps != len(default_steps):
    if n_steps < len(default_steps):
        default_steps = default_steps[:n_steps]
    else:
        last = default_steps[-1]
        current_len = len(default_steps)
        for i in range(current_len + 1, n_steps + 1):
            default_steps.append(
                {
                    "Step": i,
                    "Label": f"Step {i}",
                    "Duration_min": last["Duration_min"],
                    "VO2_current": last["VO2_current"],
                    "HRV_current": last["HRV_current"],
                }
            )

df_steps = pd.DataFrame(default_steps)

st.markdown("Edit VO₂ and HRV values for each step according to your lab measurements:")

edited_df = st.data_editor(
    df_steps,
    num_rows="dynamic",
    use_container_width=True,
)

analyze = st.button("Analyze test")

# ----------------- HELPER FUNCTIONS -----------------
def compute_et_layers(df, vo2max, hrv_rest):
    """
    Compute ET values for VO2 and HRV layers.
    All intermediate math is kept internal; only ET outputs are returned.
    """
    x_vo2_list = []
    e_vo2_list = []
    x_hrv_list = []
    e_hrv_list = []

    for _, row in df.iterrows():
        vo2 = float(row["VO2_current"])
        hrv = float(row["HRV_current"])

        # VO2 layer: relative intensity vs VO2max
        x_vo2 = vo2 / vo2max
        if x_vo2 < 0:
            x_vo2 = 0.0
        # x_vo2 > 1 is allowed (supra-max), ET can become negative
        e_vo2 = 1.0 - x_vo2**2

        # HRV layer: relative HRV loss vs resting value
        x_hrv = (hrv_rest - hrv) / hrv_rest
        if x_hrv < 0:
            x_hrv = 0.0
        if x_hrv > 1:
            x_hrv = 1.0
        e_hrv = 1.0 - x_hrv**2

        x_vo2_list.append(x_vo2)
        e_vo2_list.append(e_vo2)
        x_hrv_list.append(x_hrv)
        e_hrv_list.append(e_hrv)

    df_out = df.copy()
    df_out["E_VO2"] = e_vo2_list
    df_out["E_HRV"] = e_hrv_list
    return df_out


def classify_overall(df_et):
    """
    Derive overall ET status (GREEN/YELLOW/RED) from min ET values.
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


def find_threshold_step(df_et, column, cut):
    """
    First step where ET value <= cut. Returns step index or None.
    """
    for _, row in df_et.iterrows():
        if row[column] <= cut:
            return int(row["Step"])
    return None

# ----------------- SECTION 3: RESULTS -----------------
st.header("3. Results")

if analyze:
    if vo2max <= 0 or hrv_rest <= 0:
        st.error("VO₂max and HRV_rest must be greater than zero.")
    else:
        df_et = compute_et_layers(edited_df, vo2max, hrv_rest)

        # Overall classification
        status, min_e, min_e_vo2, min_e_hrv, limiter = classify_overall(df_et)

        # Thresholds (cut-offs can be tuned)
        metabolic_cut = 0.50
        autonomic_cut = 0.70
        metabolic_step = find_threshold_step(df_et, "E_VO2", metabolic_cut)
        autonomic_step = find_threshold_step(df_et, "E_HRV", autonomic_cut)

        # ---------- 3.1 STATUS PANEL ----------
        col_a, col_b = st.columns([1, 2])
        with col_a:
            if status == "GREEN":
                st.success("OVERALL STATUS: GREEN")
            elif status == "YELLOW":
                st.warning("OVERALL STATUS: YELLOW")
            else:
                st.error("OVERALL STATUS: RED")

            st.write(f"Minimum ET across steps: **{min_e:.3f}**")

        with col_b:
            st.markdown("**Scientific summary**")

            if status == "GREEN":
                st.markdown(
                    """
- ET depression remains mild in both layers → biological time is largely preserved.
- The autonomic and metabolic systems handle the incremental load with adequate reserve.
- This pattern is compatible with sustainable training loads for most well-conditioned athletes.
                    """
                )
            elif status == "YELLOW":
                st.markdown(
                    """
- ET shows moderate contraction → regulation works harder to stabilise internal milieu.
- Repeated sessions at this pattern may accumulate hidden fatigue (“time debt”) if recovery is insufficient.
- Useful for targeted overload, but training density and recovery windows must be monitored carefully.
                    """
                )
            else:  # RED
                st.markdown(
                    """
- ET exhibits marked contraction, indicating high integrated stress on metabolic and autonomic systems.
- Such responses are typically close to or beyond individual threshold; frequent repetition increases risk of maladaptation.
- This zone should be reserved for controlled testing or occasional peak sessions under professional supervision.
                    """
                )

            if limiter == "autonomic":
                st.markdown(
                    "- **Autonomic ET drops earlier and deeper than metabolic ET → the autonomic nervous system appears to be the primary limiting factor in this test.**"
                )
            elif limiter == "metabolic":
                st.markdown(
                    "- **Metabolic ET drops earlier and deeper than autonomic ET → peripheral/metabolic capacity is the primary limiter in this test.**"
                )
            else:
                st.markdown(
                    "- **Both layers depress in parallel → metabolic and autonomic loads are well coupled in this protocol.**"
                )

        # ---------- 3.2 THRESHOLDS ----------
        st.subheader("3.2. Suggested ET thresholds")

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            if metabolic_step is not None:
                st.markdown(
                    f"- **Metabolic ET threshold:** first step with ET₍VO₂₎ ≤ {metabolic_cut:.2f} "
                    f"is **Step {metabolic_step}**."
                )
            else:
                st.markdown(
                    f"- **Metabolic ET threshold:** no step reached ET₍VO₂₎ ≤ {metabolic_cut:.2f} (sub-threshold test)."
                )
        with col_t2:
            if autonomic_step is not None:
                st.markdown(
                    f"- **Autonomic ET threshold:** first step with ET₍HRV₎ ≤ {autonomic_cut:.2f} "
                    f"is **Step {autonomic_step}**."
                )
            else:
                st.markdown(
                    f"- **Autonomic ET threshold:** no step reached ET₍HRV₎ ≤ {autonomic_cut:.2f} (autonomic reserve preserved)."
                )

        # ---------- 3.3 OPTIONAL DETAILS ----------
        with st.expander("Show detailed ET values per step"):
            st.dataframe(
                df_et[[
                    "Step", "Label", "Duration_min",
                    "VO2_current", "HRV_current",
                    "E_VO2", "E_HRV"
                ]],
                use_container_width=True,
            )
else:
    st.info("Edit the step data if needed, then press **Analyze test** to compute ET thresholds.")
