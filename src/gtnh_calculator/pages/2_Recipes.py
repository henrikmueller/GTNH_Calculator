import streamlit as st
import logging
import sys

from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.database_extraction.recipe_initialization import RecipeInitializer
from packages.recipes_db.voltage_tiers import VoltageTier
from packages.utility.streamlit_functions import load_database
from packages.utility.streamlit_functions import search_and_select_materials, display_crafting_chain_recipe

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)

MAX_DISPLAYED_RECIPES = 100


_LOGGER.warning('\n\nSTARTING NEW PAGE: Recipe Exploration')
st.set_page_config(
    page_title="GTNH: Recipes",
    page_icon="📊",
    layout="wide"
)

st.write("# GTNH Database ️")
database: GTNHDatabase = load_database()
mods_recipes = database.mod_set_recipes()
recipe_initializer = RecipeInitializer(machine_options_book=database.machine_options_book)

a, b, c = st.columns(3)
with a:
    selected_mods = st.multiselect(
        "Filter recipes by mods",
        options=mods_recipes,
        default=mods_recipes,
    )
with b:
    selected_machine_names = set(st.multiselect(
        "Filter recipes by machines",
        options=[m.name for m in database.extracted_machines.values()],
        default=None,
    ))
with c:
    selected_voltage_tiers = set(st.multiselect(
        "Filter recipes by voltage tiers",
        options=[VoltageTier.voltage_tier_name(v) for v in VoltageTier.valid_voltage_tiers()],
        default=[VoltageTier.voltage_tier_name(v) for v in VoltageTier.valid_voltage_tiers()],
    ))

with st.spinner('Applying filters...', show_time=True):
    selected_machines = {m for m in database.extracted_machines.values() if m.name in selected_machine_names}
    df = database.filter_recipes(
        database.df_recipes, 
        categories=selected_mods, 
        allowed_machines=selected_machines if selected_machine_names else None,
        voltage_tiers={VoltageTier.to_voltage_tier(v) for v in selected_voltage_tiers}
    )
    df = database.blow_up_input_groups(df, pick_any=True)

    if df.shape[0] > 0:
        df['SELECTED_MACHINE'] = df.apply(database.get_default_machine, axis=1)

    show_all = st.toggle(f'Show all filtered recipes (Max {MAX_DISPLAYED_RECIPES})', value=False)
    total_recipe_count = df.shape[0]
    df = df.head(MAX_DISPLAYED_RECIPES if show_all else 10)

st.success(f'Displaying {df.shape[0]} / {total_recipe_count} recipes matching the selected filters.', icon="✅")

if df.shape[0] > 0:
    # with st.expander("Filter by materials"):
    #     selected_materials = search_and_select_materials(
    #         database=database,
    #         key='selected_materials',
    #         multiselect=True,
    #         number_of_columns=3,
    #         max_displayed_options=30
    #     )

    for recipe_row in df.itertuples(index=False):
        recipe = recipe_initializer.create_recipe_from_row(recipe_row)
        display_crafting_chain_recipe(recipe, database.machine_options_book)
