import streamlit as st
import matplotlib.pyplot as plt
import plotly.express as px

from packages.database_extraction.database_extractor import GTNHDatabase, load_database
from packages.recipes_db.voltage_tiers import VoltageTier


# Run via: streamlit run ./src/gtnh_calculator/GTNH_Calculator.py
# Colors: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Values/named-color

# Deploy: Install poetry plugin: poetry self add poetry-plugin-export
# Then create requirements.txt: poetry export -f requirements.txt -o requirements.txt

st.set_page_config(layout="wide")

st.set_page_config(
    page_title="GTNH Calculator",
    page_icon="⚙️",
    layout="wide"
)

st.write("# Welcome to the GTNH Calculator! ️")
database: GTNHDatabase = load_database()

a, b = st.columns(2)
c, d = st.columns(2)

a.metric("Materials", len(database.extracted_materials), border=True)
b.metric("Recipes", database.df_recipes.shape[0], border=True)
c.metric("Machines", len(database.extracted_machines), border=True)
d.metric("Machine Types", len(set().union(*[m.machine_types for m in database.extracted_machines.values()])), border=True)

col_1, col_2, col_3 = st.columns(3)
with col_1:
    counts = database.df_recipes["CATEGORY"].value_counts()
    fig = px.pie(
        names=counts.index,
        values=counts.values,
        title='Recipe Distribution by Mod',
        hole=0.4
    )
    st.plotly_chart(fig, width=500)

with col_2:
    NUMBER_OF_MACHINE_TYPES = 20
    df = database.df_recipes.assign(MACHINE_TYPES=database.df_recipes["MACHINES"].apply(lambda machines: list(set().union(*[m.machine_types for m in machines]))))
    counts = df["MACHINE_TYPES"].explode().value_counts().nlargest(NUMBER_OF_MACHINE_TYPES)
    fig = px.pie(
        names=[machine_type.name for machine_type in counts.index],
        values=counts.values,
        title=f'Machine Type Distribution (Top {NUMBER_OF_MACHINE_TYPES})',
        hole=0.4
    )
    st.plotly_chart(fig, width=500)

with col_3:
    counts = database.df_recipes["VOLTAGE_TIER"].value_counts()
    fig = px.pie(
        names=[VoltageTier.voltage_tier_name(v) for v in counts.index],
        values=counts.values,
        title=f'Voltage Tier Distribution',
        hole=0.4
    )
    st.plotly_chart(fig, width=500)
