import streamlit as st
import plotly.express as px
from collections import Counter
import logging
import sys

from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.streamlit.streamlit_recipes import load_database, show_memory_usage
from packages.database_algorithms.bfs import calculate_unlock_tiers
from packages.recipes_db.voltage_tiers import VoltageTier
from packages.utility.general_utility import print_df
from packages.database_extraction.recipe_initialization import RecipeInitializer

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


# Run via: poetry run streamlit run ./src/gtnh_calculator/GTNH_Calculator.py
# Colors: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Values/named-color

# Deploy: Install poetry plugin: poetry self add poetry-plugin-export
# Then create requirements.txt: poetry export -f requirements.txt -o requirements.txt

VALIDITY_CHECKS = True

st.set_page_config(layout="wide")

st.set_page_config(
    page_title="GTNH Calculator",
    page_icon="⚙️",
    layout="wide"
)

st.write("# Welcome to the GTNH Calculator! ️")
database: GTNHDatabase = load_database()
show_memory_usage(database)

a, b = st.columns(2)
c, d = st.columns(2)

a.metric("Materials", len(database.extracted_materials), border=True)
b.metric("Recipes", database.df_recipes.shape[0], border=True)
c.metric("Machines", len(database.extracted_machines), border=True)
d.metric("Machine Types", len(set().union(*[m.machine_types for m in database.extracted_machines.values()])), border=True)

if VALIDITY_CHECKS:
    import pandas as pd

    df_recipes = database.df_recipes.copy()
    recipe_initializer = RecipeInitializer(machine_options_book=database.machine_options_book)
    df_recipes[["SELECTED_MACHINE", "SELECTED_VOLTAGE_TIER"]] = pd.DataFrame(
        df_recipes["RECIPE"]
            .apply(recipe_initializer.get_default_machine_and_voltage_tier)
            .tolist(),
        index=df_recipes.index,
    )
    instantiated_recipes = recipe_initializer.instantiate_recipes_from_raw(df_recipes, pick_any=True)
        
    _LOGGER.info('Checking instantiated recipes for throughput calculation...')
    for instantiated_recipe in instantiated_recipes.values():
        try:
            throughput = instantiated_recipe.adapted_recipe.get_throughput(instantiated_recipe.base_recipe.raw_recipe)
            if throughput <= 0:
                _LOGGER.error(f"Non-positive throughput {throughput} for instantiated recipe: {instantiated_recipe}")
        except ValueError as e:
            _LOGGER.error(f"Throughput calculation failed for instantiated recipe: {instantiated_recipe.id}. Error: {e}")

# col_1, col_2, col_3 = st.columns(3)
# with col_1:
#     counts = database.df_recipes["CATEGORY"].value_counts()
#     fig = px.pie(
#         names=counts.index,
#         values=counts.values,
#         title='Recipe Distribution by Mod',
#         hole=0.4
#     )
#     st.plotly_chart(fig, width=500)

# with col_2:
#     NUMBER_OF_MACHINE_TYPES = 20
#     df = database.df_recipes.assign(MACHINE_TYPES=database.df_recipes["MACHINES"].apply(lambda machines: list(set().union(*[m.machine_types for m in machines]))))
#     counts = df["MACHINE_TYPES"].explode().value_counts().nlargest(NUMBER_OF_MACHINE_TYPES)
#     fig = px.pie(
#         names=[machine_type.name for machine_type in counts.index],
#         values=counts.values,
#         title=f'Machine Type Distribution (Top {NUMBER_OF_MACHINE_TYPES})',
#         hole=0.4
#     )
#     st.plotly_chart(fig, width=500)

# with col_3:
#     counts = database.df_recipes["VOLTAGE_TIER"].value_counts()
#     fig = px.pie(
#         names=[VoltageTier.voltage_tier_name(v) for v in counts.index],
#         values=counts.values,
#         title=f'Voltage Tier Distribution',
#         hole=0.4
#     )
#     st.plotly_chart(fig, width=500)


# unlock_tiers = calculate_unlock_tiers(database.df_recipes, database.extracted_materials)
# counts = Counter(unlock_tiers.values())
# fig = px.pie(
#     names=counts.keys(),
#     values=counts.values(),
#     title='Unlock Tiers',
#     hole=0.4
# )
# st.plotly_chart(fig, width=500)

