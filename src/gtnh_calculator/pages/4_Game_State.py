import streamlit as st
import logging
import sys

from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.streamlit.gtnh_database_exploration import GTNHDatabaseExplorer
from packages.streamlit.session_state import GameStateSessionState
from packages.factory_database.sheet_connection import connect_to_factory_database
from packages.factory_database.factories import ProductiveRecipe, TextCondition, ProductiveMachine
from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.database_extraction.recipe_initialization import RecipeInitializer
from packages.recipes_db.instantiated_recipes import InstantiatedRecipe
from packages.streamlit.streamlit_recipes import (
    display_crafting_chain_recipe, adapt_crafting_chain_recipe, load_database, show_memory_usage,
    display_factory, display_recipe_environment
)

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)
SESSION_STATE_KEY = 'game_state'

st.set_page_config(layout="wide")
st.set_page_config(
    page_title="GTNH Game State",
    page_icon="📚",
    layout="wide"
)
_LOGGER.info("Starting GTNH Game State page...")

st.write("# GTNH Game State")
database: GTNHDatabase = load_database()
session_state = GameStateSessionState.get(SESSION_STATE_KEY)
show_memory_usage(database)
recipe_initializer = RecipeInitializer(machine_options_book=database.machine_options_book)
gtnhdatabase_explorer = GTNHDatabaseExplorer(
    database=database,
    session_state=session_state,
    recipe_initializer=recipe_initializer
)


@st.fragment()
def show_selected_recipe(session_state: GameStateSessionState, database: GTNHDatabase) -> None:
    st.markdown(f'## Selected Recipe')
    instantiated_recipe = session_state.get_selected_recipe()
    if instantiated_recipe is not None:
        recipe_environment = session_state.recipe_environments_state.get_recipe_environment(
            instantiated_recipe.id, instantiated_recipe.recipe_environment).to_environment()
        recipe_initializer.update_instantiated_recipe(instantiated_recipe, recipe_environment)

        with st.container(border=True):
            a, b = st.columns(2)
            with a:
                adapt_crafting_chain_recipe(
                    instantiated_recipe, database.machine_options_book, 
                    session_state.recipe_environments_state, key_suffix='gs_selected',
                    enabled_checkbox=False
                )
                st.button(
                    label='Deselect', key=f'deselect_{instantiated_recipe.id}', type='primary',
                    on_click=session_state.deselect_recipe, args=(instantiated_recipe,)
                )
            with b:
                display_crafting_chain_recipe(instantiated_recipe)

        handle_productive_recipe(instantiated_recipe)
    else:
        st.write("Select a recipe below to edit its environment and store it in the database.")


@st.fragment()
def handle_productive_recipe(instantiated_recipe: InstantiatedRecipe) -> None:
    productive_recipe = get_productive_recipe_from_selection(instantiated_recipe)
    factory = productive_recipe.to_factory()
    validity = factory.validity
    if st.button(label='Write to database', type='primary'):
        if not validity.is_valid:
            st.warning(f"The productive recipe is invalid: {validity.message} Please correct the values in the database.")

        with st.spinner('Writing productive recipe to database...', show_time=True):
            writing_response = session_state.factory_database_connection.write_database_entries(factory.database_entries)
        if not writing_response.display:
            return
        if writing_response.success:
            st.success(f"Successfully wrote productive recipe to database.")
        else:
            st.error(f"Failed to write productive recipe to database: {writing_response.message}")


def get_productive_recipe_from_selection(instantiated_recipe: InstantiatedRecipe) -> ProductiveRecipe:
    a, b, c, d = st.columns(4)
    with a:
        amount = st.number_input(
            "Amount", min_value=1, value=1, step=1, key=f'productive_recipe_amount_{instantiated_recipe.id}'
        )
    with b:
        location = st.text_input("Location", key=f'productive_recipe_location_{instantiated_recipe.id}')
    with c:
        conditions_text = st.text_input("Conditions", key=f'productive_recipe_conditions_{instantiated_recipe.id}')
    with d:
        comment = st.text_input("Comment", key=f'productive_recipe_comment_{instantiated_recipe.id}')
    return ProductiveRecipe(
        instantiated_recipe=instantiated_recipe,
        amount=int(amount),
        conditions={TextCondition(conditions_text)} if conditions_text else set(),
        location=location,
        comment=comment,
    )


if not session_state.has_database_connection:
    session_state.factory_database_connection = connect_to_factory_database(database)
    if session_state.has_database_connection:
        st.rerun()
if session_state.has_database_connection:
    st.success(session_state.factory_database_connection.connection_message)
else:
    st.error(session_state.factory_database_connection.connection_message)

if session_state.has_database_connection:
    connection = session_state.factory_database_connection
    with st.expander("Stored Factories"):
        response = connection.read_database_entries()
        if response.success:
            factory_database = response.factory_database
            factories = factory_database.get_factories(database)
            for factory in factories:
                with st.container(border=True):
                    display_factory(factory, recipe_headline=factory.factory_name)
               
    st.divider() 
    show_selected_recipe(session_state=session_state, database=database)

    st.divider()
    gtnhdatabase_explorer.recipe_exploration(
        all_materials=database.extracted_materials
    )
