import streamlit as st
from io import StringIO
import logging
import sys
from streamlit_searchbox import st_searchbox

from gtnh_calculator.packages.recipes.machine_type_books import MachineTypeBook
from gtnh_calculator.packages.recipes.voltage_tiers import VoltageTier
from gtnh_calculator.packages.utility.general_utility import get_differences
from packages.configs.config import Config
from packages.crafting_chains.crafting_chain import CraftingChain
from packages.recipes.recipe_book import RecipeBook
from packages.recipes.recipe import Recipe
from packages.crafting_chains.crafting_chain_finder import CraftingChainFinder
from packages.configs.config import load_config
from packages.utility.general_utility import time_to_seconds, get_differences
from packages.recipes.machine_options.machine_option_books import load_possible_machine_options

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


# Run via: streamlit run ./src/gtnh_calculator/streamlit_app.py
# Colors: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Values/named-color

# Deploy: Install poetry plugin: poetry self add poetry-plugin-export
# Then create requirements.txt: poetry export -f requirements.txt -o requirements.txt

_LOGGER.debug('\n\nSTARTING NEW PAGE')
machine_options_path = 'config/fixed_settings/machine_options.yaml'
machine_options_book = load_possible_machine_options(machine_options_path)

st.set_page_config(layout="wide")
st.markdown('# GTNH Calculator')
st.markdown('## Recipe Lists')
st.markdown('Recipes are stored in the following Google Spreadsheet: '
            'https://docs.google.com/spreadsheets/d/1OSog0iIKua5T7ms0Iv9OZxCR1Qw45QSPtZd7EDP-FK4/edit?usp=sharing')
st.markdown('Please **DO NOT** change any recipes in existing tabs, but create a separate tab!')
st.markdown('## Config File')
crafting_chain = None
recipe_book = None
machine_type_book = None
config = None
update = 'update' in st.session_state and st.session_state['update']

uploaded_file = st.file_uploader("Choose a config file to specify the recipe chain", type='yaml')
if uploaded_file is not None:
    config, recipe_book, machine_type_book = load_config(uploaded_file, machine_options_book)
    st.write(config)

if 'recipe_book' in st.session_state:
    _LOGGER.debug('Keep recipe book')
    recipe_book = st.session_state['recipe_book']

if config is not None and recipe_book is not None:
    crafting_chain_finder = CraftingChainFinder(recipe_book)
    crafting_chain = crafting_chain_finder.optimal_crafting_chain(config, recipe_weight_factor=0.0000001)

st.markdown('---')


def calculate_crafting_chain():
    if crafting_chain is not None and recipe_book is not None and config is not None:
        time, _ = time_to_seconds(config.time)
        display_interval, display_interval_name = time_to_seconds(config.display_interval)
        if display_interval != 1:
            display_interval_name = display_interval_name + 's'

        df = crafting_chain.to_dataframe(
            time_factor=display_interval / time,
            time_interval=f'{display_interval} {display_interval_name}'
        )
        df['Checkbox'] = False
        df['Machine Group'] = ''
        st.session_state['saved_data'] = df
        statistics = crafting_chain.statistics(
            time_factor=display_interval / time,
            time_interval=f'{display_interval} {display_interval_name}'
        )
        st.session_state['statistics'] = statistics
    else:
        _LOGGER.warning(f'Could not calculate crafting chain')


def print_crafting_chain():
    if not isinstance(crafting_chain, CraftingChain):
        _LOGGER.warning(f'crafting_chain of wrong type: {type(crafting_chain)}')
        return None
    if not isinstance(recipe_book, RecipeBook):
        _LOGGER.warning(f'recipe_book of wrong type: {type(recipe_book)}')
        return None
    if not isinstance(config, Config):
        _LOGGER.warning(f'config of wrong type: {type(config)}')
        return None

    if update or 'saved_data' not in st.session_state:
        st.session_state['update'] = False
        _LOGGER.debug('Update crafting chain')
        calculate_crafting_chain()

    if 'statistics' in st.session_state:
        st.markdown('## Crafting Chain Statistics')
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(st.session_state['statistics'].markdown_inputs())
        with col2:
            st.markdown(st.session_state['statistics'].markdown_outputs())
        st.markdown(st.session_state['statistics'].markdown_eu())
        st.markdown('---')
    else:
        _LOGGER.warning(f'statistics not in st.session_state')

    if 'saved_data' in st.session_state:
        st.markdown('## Complete Crafting Chain')
        editable_column_names = ['Checkbox', 'Machine Group']
        column_config = {
            'Recipe ID': st.column_config.NumberColumn(),
            'Machine Amount': st.column_config.NumberColumn(),
            'EU/t': st.column_config.NumberColumn(),
            'Checkbox': st.column_config.CheckboxColumn('Checkbox', width='small')
        }

        with st.form(key='recipe_chain_config'):
            changed_data = st.data_editor(
                st.session_state['saved_data'], column_config=column_config, width='stretch', height='auto',
                disabled=[col for col in list(st.session_state['saved_data'].columns) if
                          col not in editable_column_names]
            )

            def recalculate_button():
                st.session_state['update'] = True

            if st.form_submit_button(
                label='Recalculate',
                on_click=recalculate_button
            ):
                st.info(f'Crafting Chain updated', icon='🛠')
    else:
        _LOGGER.warning(f'saved_data not in st.session_state')
    st.markdown('---')


print_crafting_chain()


def is_contained_in(text: str, text_list: list[str], case_sensitive=True) -> bool:
    if case_sensitive:
        return any(text in s for s in text_list)
    lowercase_text = text.lower()
    return any(lowercase_text in s.lower() for s in text_list)


@st.fragment()
def recipe_configuration():
    _LOGGER.debug(f'----------------------- STARTING FRAGMENT -------------------------')
    recipe_options = [recipe.__str__() for recipe in crafting_chain.recipes.values()]

    def search_recipe(text: str) -> list:
        return [
            recipe.__str__() for recipe_id, recipe in crafting_chain.recipes.items()
            if text in str(recipe_id) or is_contained_in(
                text,
                [recipe.machine.name] + [m.name for m in recipe.get_inputs() + recipe.get_outputs()],
                case_sensitive=False
            )
        ]

    st.markdown('## Recipe Configuration')

    selected_recipe = st_searchbox(
        search_recipe,
        placeholder="Select Recipe",
        key="select_recipe",
        rerun_scope='fragment',
        label='Recipe',
        default_options=recipe_options
    )
    _LOGGER.debug(f'Selected Recipe: {selected_recipe}')
    display_recipe(selected_recipe)


def initiate_update():
    _LOGGER.debug(f'Set update to True')
    st.session_state['update'] = True


@st.fragment()
def display_recipe(selected_recipe):
    """
    :param selected_recipe:
    :return: True, if the recipe was changed by the used
    """
    if selected_recipe is None:
        return None
    index = selected_recipe.find('|')
    recipe_id = int(selected_recipe[:index].strip())
    recipe = recipe_book.recipes[recipe_id]
    voltage_tier_names = VoltageTier.voltage_tiers(recipe.minimum_voltage_tier)

    if machine_type_book is not None:
        col1, col2 = st.columns(2)

        with col1:
            if 'selected_recipe' not in st.session_state or st.session_state['selected_recipe'].id != recipe.id:
                # Preselect the voltage tier of the recipe, which was switched to
                st.session_state['select_machine'] = recipe.machine.name

            possible_machine_names = [
                t.name for t in machine_type_book.get_machine_type_options(recipe.base_machine_type)
            ]

            selected_machine = st.selectbox(
                label="Select the Machine",
                options=possible_machine_names,
                key='select_machine'
            )

        with col2:
            if 'selected_recipe' not in st.session_state or st.session_state['selected_recipe'].id != recipe.id:
                # Preselect the voltage tier of the recipe, which was switched to
                st.session_state['select_voltage_tier'] = recipe.voltage_tier_name

            selected_voltage_tier = st.selectbox(
                label="Select the Voltage Tier",
                options=voltage_tier_names,
                key='select_voltage_tier'
            )

        new_machine_type = machine_type_book.get_machine_type(selected_machine)
        _LOGGER.debug(f'New machine: {new_machine_type}')
        if new_machine_type is not None:
            recipe.machine.machine_type = new_machine_type
        new_voltage_tier = VoltageTier.to_voltage_tier(selected_voltage_tier)
        recipe.machine.voltage_tier = new_voltage_tier
        recipe.machine.voltage_tier = VoltageTier.to_voltage_tier(selected_voltage_tier)
        recipe.fit_to_machine()
        _LOGGER.debug(f'New recipe: {recipe.__repr__()}')
        recipe_book.recipes[recipe_id] = recipe
        st.session_state['recipe_book'] = recipe_book

    with st.container(border=True):
        st.markdown(f'### {recipe.machine.name} ({recipe.machine.voltage_tier_name})')
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(recipe.markdown_inputs())
        with col2:
            st.markdown(recipe.markdown_outputs())
        with col3:
            st.markdown('#### Recipe statistics:')
            st.markdown(f'**EU/t**: {abs(int(recipe.raw_recipe.eu_per_tick))}')
            st.markdown(f'**Total EU**: {abs(int(recipe.raw_recipe.total_eu))}')
            st.markdown(f'**Processing time**: {recipe.raw_recipe.processing_time} s')
            options_string = recipe.raw_recipe.recipe_options.markdown_string()
            if options_string != '':
                st.markdown(options_string)

    st.session_state['selected_recipe'] = recipe


if crafting_chain is not None:
    recipe_configuration()
