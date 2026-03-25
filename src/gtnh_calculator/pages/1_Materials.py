import streamlit as st
import streamlit.components.v1 as components
import logging
import sys
from rapidfuzz import fuzz

from packages.database_extraction.database_extractor import GTNHDatabase, load_database
from packages.recipes_db.material import Material
from packages.utility.streamlit_functions import display_recipe
from packages.utility.general_utility import print_df

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
IMAGE_FOLDER = "db/images/"
MAX_DISPLAYED_OPTIONS = 300
NUMBER_OF_COLUMNS = 3

mods_materials = database.mod_set_materials()

if 'selected_material' not in st.session_state:
    st.session_state.selected_material = None

st.write("# GTNH Database ️")


def copy_button(text, key):
    components.html(f"""
        <button onclick="navigator.clipboard.writeText('{key}')"
            style="
                padding:8px 12px;
                border-radius:8px;
                border:1px solid #ccc;
                cursor:pointer;
            ">
            {text}
        </button>
    """, height=50)


def material_card(material: Material):
    with st.container(border=True, width=600):
        col1, col2 = st.columns([4, 1])

        with col1:
            if st.button(material.name, key=f"button_{material.id}", width='stretch'):
                if st.session_state.selected_material is None:
                    st.session_state.selected_material = material
                    st.rerun()
            # st.markdown(f'<span style="font-size:12px;">{material.id.replace('~', '\~')}</span>', unsafe_allow_html=True)
            st.write(f'Mod: {material.mod}')
        with col2:
            copy_button(text='Copy ID', key=material.id)
            try:
                st.image(f'db/images/{material.image_file_path}')
            except Exception as e:
                pass


if st.session_state.selected_material is None:
    selected_mods = st.sidebar.multiselect(
        "Filter by mods",
        options=mods_materials,
        default=None,
    )
    selected_type = st.sidebar.multiselect(
        "Filter by material type",
        options=['item', 'fluid'],
        default=None,
    )
    filtered_materials = [
        m for m in database.extracted_materials.values() if
        (not selected_mods or m.mod in selected_mods) and (not selected_type or m.material_type in selected_type)
    ]
    st.write(f'Found {len(filtered_materials)} materials matching the selected filters.')

    search = st.text_input("Search material")
    if search:
        search_terms = search.lower().split(' ')
        matching_materials = [m for m in filtered_materials if all(t in m.name.lower() for t in search_terms)]
        matching_materials.sort(key=lambda s: fuzz.ratio(search.lower(), s.name.lower()), reverse=True)
    else:
        matching_materials = []

    cols = st.columns(NUMBER_OF_COLUMNS)
    for i, material in enumerate(matching_materials[:MAX_DISPLAYED_OPTIONS]):
        with cols[i % NUMBER_OF_COLUMNS]:
            material_card(material)
else:
    material = st.session_state.selected_material
    material_card(material)

    if st.button('Discard material'):
        st.session_state.selected_material = None
        st.rerun()

    material_info_tab, usage_tab, recipes_tab = st.tabs(['Material Info', 'Usage', 'Recipes'], default='Recipes')

    with material_info_tab:
        st.write(material.tooltip)
    with usage_tab:
        detected_recipes = database.filter_recipes(df_recipes=database.df_recipes, inputs={material})
        for i, recipe_row in enumerate(detected_recipes.itertuples()):
            if i >= 100:
                break
            display_recipe(recipe_row)
    with recipes_tab:
        detected_recipes = database.filter_recipes(df_recipes=database.df_recipes, outputs={material})
        print_df(detected_recipes)
        for i, recipe_row in enumerate(detected_recipes.itertuples()):
            if i >= 100:
                break
            display_recipe(recipe_row)
