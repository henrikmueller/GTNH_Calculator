import streamlit as st
import streamlit.components.v1 as components
import logging
import sys
from rapidfuzz import fuzz

from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.utility.streamlit_functions import load_database
from packages.database_extraction.recipe_initialization import RecipeInitializer
from packages.utility.streamlit_functions import display_crafting_chain_recipe, search_and_select_materials

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


_LOGGER.warning('\n\nSTARTING NEW PAGE: Recipe Exploration')
st.set_page_config(
    page_title="GTNH: Materials",
    page_icon="📊",
    layout="wide"
)

database: GTNHDatabase = load_database()
recipe_initializer = RecipeInitializer(machine_options_book=database.machine_options_book)
IMAGE_FOLDER = "db/images/"
MAX_DISPLAYED_OPTIONS = 300
NUMBER_OF_COLUMNS = 3

st.write("# GTNH Database ️")

selected_material = search_and_select_materials(
    database=database,
    key='selected_material',
    multiselect=False,
    number_of_columns=NUMBER_OF_COLUMNS,
    max_displayed_options=MAX_DISPLAYED_OPTIONS
)
material = next(iter(selected_material), None)

if material is not None:
    material_info_tab, usage_tab, recipes_tab = st.tabs(['Material Info', 'Usage', 'Recipes'], default='Recipes')
    with material_info_tab:
        st.write(material.tooltip)
    with usage_tab:
        detected_recipes = database.filter_recipes(df_recipes=database.df_recipes, inputs={material})
        for i, recipe_row in enumerate(detected_recipes.itertuples()):
            if i >= 100:
                break
            recipe = recipe_initializer.create_recipe_from_row(recipe_row)
            display_crafting_chain_recipe(recipe, database.machine_options_book)
    with recipes_tab:
        detected_recipes = database.filter_recipes(df_recipes=database.df_recipes, outputs={material})
        for i, recipe_row in enumerate(detected_recipes.itertuples()):
            if i >= 100:
                break
            recipe = recipe_initializer.create_recipe_from_row(recipe_row)
            display_crafting_chain_recipe(recipe, database.machine_options_book)

# if st.session_state.selected_material is None:
#     selected_mods = st.sidebar.multiselect(
#         "Filter by mods",
#         options=mods_materials,
#         default=None,
#     )
#     selected_type = st.sidebar.multiselect(
#         "Filter by material type",
#         options=['item', 'fluid'],
#         default=None,
#     )
#     filtered_materials = [
#         m for m in database.extracted_materials.values() if
#         (not selected_mods or m.mod in selected_mods) and (not selected_type or m.material_type in selected_type)
#     ]
#     st.write(f'Found {len(filtered_materials)} materials matching the selected filters.')

#     search = st.text_input("Search material")
#     if search:
#         search_terms = search.lower().split(' ')
#         matching_materials = [m for m in filtered_materials if all(t in m.name.lower() for t in search_terms)]
#         matching_materials.sort(key=lambda s: fuzz.ratio(search.lower(), s.name.lower()), reverse=True)
#     else:
#         matching_materials = []

#     cols = st.columns(NUMBER_OF_COLUMNS)
#     for i, material in enumerate(matching_materials[:MAX_DISPLAYED_OPTIONS]):
#         with cols[i % NUMBER_OF_COLUMNS]:
#             material_card(material)
# else:
#     material = st.session_state.selected_material
#     material_card(material)

#     if st.button('Discard material'):
#         st.session_state.selected_material = None
#         st.rerun()

#     material_info_tab, usage_tab, recipes_tab = st.tabs(['Material Info', 'Usage', 'Recipes'], default='Recipes')

#     with material_info_tab:
#         st.write(material.tooltip)
#     with usage_tab:
#         detected_recipes = database.filter_recipes(df_recipes=database.df_recipes, inputs={material})
#         for i, recipe_row in enumerate(detected_recipes.itertuples()):
#             if i >= 100:
#                 break
#             display_recipe(recipe_row, recipe_row.MACHINES)
#     with recipes_tab:
#         detected_recipes = database.filter_recipes(df_recipes=database.df_recipes, outputs={material})
#         for i, recipe_row in enumerate(detected_recipes.itertuples()):
#             if i >= 100:
#                 break
#             display_recipe(recipe_row, recipe_row.MACHINES)
