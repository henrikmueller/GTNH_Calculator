import streamlit as st
import logging
import sys
import math
from streamlit_searchbox import st_searchbox

from packages.recipes.voltage_tiers import VoltageTier
from packages.configs.config import Config
from packages.crafting_chains.crafting_chain import CraftingChain
from packages.recipes.recipe_book import RecipeBook
from packages.crafting_chains.crafting_chain_finder import CraftingChainFinder
from packages.data_loader import load_data
from packages.utility.general_utility import time_to_seconds
from packages.recipes.machine_options.machine_option_books import load_possible_machine_options
from packages.exceptions import DataLoadingException

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


WEIGHT_EXP_MIN = -5.0
WEIGHT_EXP_MAX = 10.0



# Run via: streamlit run ./src/gtnh_calculator/streamlit-app.py
# Colors: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Values/named-color

# Deploy: Install poetry plugin: poetry self add poetry-plugin-export
# Then create requirements.txt: poetry export -f requirements.txt -o requirements.txt

_LOGGER.warning('\n\nSTARTING NEW PAGE')
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
    if 'file_hash' not in st.session_state or st.session_state['file_hash'] != hash(uploaded_file):
        for key in st.session_state:
            del st.session_state[key]
    st.session_state['file_hash'] = hash(uploaded_file)

    try:
        loaded_config, recipe_book, machine_type_book = load_data(uploaded_file, machine_options_book)
        if 'config' not in st.session_state:
            st.session_state['config'] = loaded_config
        config: Config = st.session_state['config']
    except DataLoadingException as e:
        st.error(e, icon="❗")


if 'recipe_book' in st.session_state:
    _LOGGER.debug('Keep recipe book')
    recipe_book: RecipeBook = st.session_state['recipe_book']


@st.fragment()
def select_weights():
    container = st.container(border=True, width=1900)
    with container:
        def valid_materials(text: str) -> list:
            return [m.name for m in recipe_book.material_list.materials_by_name.values()
                    if text.lower() in m.name.lower()]

        def valid_infinite_materials(text: str) -> list:
            return [m.name for m in config.infinite_materials if text.lower() in m.name.lower()]

        def add_weight(text: str) -> None:
            if text in recipe_book.material_list.materials_by_name.keys():
                material = recipe_book.material_list.materials_by_name[text]
                if material not in st.session_state['weight_materials']:
                    # Set material weight to 1. Add it to the weights section
                    config.weights[material] = 1  # default value: 1
                    st.session_state['weight_materials'].append(material)
                    st.session_state['weight_materials'].sort(key=lambda m: m.id)

        def add_ipw(text: str) -> None:
            if text in recipe_book.material_list.materials_by_name.keys():
                material = recipe_book.material_list.materials_by_name[text]
                if material not in st.session_state['ipw_materials']:
                    # Set material weight to 1. Add it to the weights section
                    config.infinite_production_weights[material] = 1  # default value: 1
                    st.session_state['ipw_materials'].append(material)
                    st.session_state['ipw_materials'].sort(key=lambda m: m.id)

        col_left, col_right = st.columns([1, 1])
        with col_left:
            st_searchbox(
                valid_materials,
                placeholder="Select additional material for weights",
                key="select_material_weight",
                rerun_scope='fragment',
                label='Add Weight',
                default_options=[m.name for m in recipe_book.material_list.materials_by_id.values()],
                clear_on_submit=True,
                submit_function=add_weight
            )

            for material in st.session_state['weight_materials']:
                def button_clicked(m):
                    if m in config.weights.keys():
                        del config.weights[m]
                    st.session_state['weight_materials'].remove(m)

                col_l1, col_l2, col_l3, col_l4 = st.columns([1, 0.7, 3, 1])

                with col_l1:
                    st.markdown(f'**{material.name}:**')
                with col_l2:
                    weight_placeholder = st.empty()
                with col_l3:
                    weight_exponent = max(min(math.log10(config.weights[material]), WEIGHT_EXP_MAX),
                                          WEIGHT_EXP_MIN + 0.1)
                    weight_exponent = st.slider(
                        label=f'{material.name}',
                        value=weight_exponent,
                        format=None,
                        min_value=WEIGHT_EXP_MIN,
                        max_value=WEIGHT_EXP_MAX,
                        step=0.01,
                        label_visibility='collapsed',
                        width=500
                    )
                    weight = 10 ** weight_exponent
                with col_l4:
                    st.button(
                        label='(Remove)',
                        key=f'remove_{material.name}',
                        type='tertiary',
                        on_click=button_clicked,
                        args=(material,)
                    )

                weight_placeholder.markdown(
                    f'{"{:.5f}".format(weight) if weight < 1 else "{:.2f}".format(weight)}'
                )
                config.weights[material] = weight
        with col_right:
            st_searchbox(
                valid_infinite_materials,
                placeholder="Select additional material for ♾️-production weights",
                key="select_material_ipw",
                rerun_scope='fragment',
                label='Add ♾️-Production Weight',
                default_options=[m.name for m in config.infinite_materials],
                clear_on_submit=True,
                submit_function=add_ipw
            )

            for material in st.session_state['ipw_materials']:
                def button_clicked_ipw(m):
                    if m in config.infinite_production_weights.keys():
                        del config.infinite_production_weights[m]
                    st.session_state['ipw_materials'].remove(m)

                col_r1, col_r2, col_r3, col_r4 = st.columns([1, 0.7, 3, 1])
                with col_r1:
                    st.markdown(f'**{material.name}:**')
                with col_r2:
                    if material in config.infinite_materials:
                        ipw_placeholder = st.empty()
                with col_r3:
                    if material in config.infinite_materials:
                        ipw_exponent = max(
                            min(math.log10(config.infinite_production_weights[material]), WEIGHT_EXP_MAX),
                            WEIGHT_EXP_MIN)
                        ipw_exponent = st.slider(
                            label=f'{material.name}',
                            value=ipw_exponent,
                            format=None,
                            min_value=WEIGHT_EXP_MIN,
                            max_value=WEIGHT_EXP_MAX,
                            step=0.01,
                            label_visibility='collapsed',
                            width=500
                        )
                        ipw = 10 ** ipw_exponent
                with col_r4:
                    st.button(
                        label='(Remove)',
                        key=f'remove_ipw_{material.name}',
                        type='tertiary',
                        on_click=button_clicked_ipw,
                        args=(material,)
                    )
                if material in config.infinite_materials:
                    ipw_placeholder.markdown(
                        f'{"{:.5f}".format(ipw) if ipw < 1 else "{:.2f}".format(ipw)}'
                    )
                    config.infinite_production_weights[material] = ipw

        if st.button(label='Update weights', key=f'update_weights', type='primary'):
            st.session_state['update_machine_types'] = True
            st.session_state['update'] = True
            st.rerun(scope='app')


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


def print_crafting_chain(
    crafting_chain_finder: CraftingChainFinder,
    crafting_chain: CraftingChain | None,
    recipe_book: RecipeBook | None,
    config: Config | None
):
    if crafting_chain is None:
        _LOGGER.warning(f'crafting_chain of wrong type: {type(crafting_chain)}')
        return None
    if recipe_book is None:
        _LOGGER.warning(f'recipe_book of wrong type: {type(recipe_book)}')
        return None
    if config is None:
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

    if any(amount >= config.machine_limit for recipe_id, amount in crafting_chain.recipe_amounts.items()):
        st.markdown(f'#### The following recipes reached the specified machine limit of {config.machine_limit}:')
    for recipe_id, recipe in crafting_chain.recipes.items():
        time, _ = time_to_seconds(config.time)
        cap = crafting_chain_finder.machine_amount_cap(recipe, time, config.use_individual_limits)
        if cap is not None and crafting_chain.recipe_amounts[recipe_id] >= cap:
            st.markdown(f'{crafting_chain.recipes[recipe_id]}')
    st.markdown('---')


if config is not None and recipe_book is not None:
    if 'weight_materials' not in st.session_state:
        st.session_state['weight_materials'] = [m for m, a in config.weights.items() if a > 0]
    st.session_state['weight_materials'].sort(key=lambda m: m.id)
    if 'ipw_materials' not in st.session_state:
        st.session_state['ipw_materials'] = [m for m, a in config.infinite_production_weights.items() if a > 0]
    st.session_state['ipw_materials'].sort(key=lambda m: m.id)

    select_weights()
    config.weights = {m: a for m, a in config.weights.items() if a != 0}
    config.infinite_production_weights = {m: a for m, a in config.infinite_production_weights.items() if a != 0}
    st.write(config)

    crafting_chain_finder = CraftingChainFinder(
        recipe_book, machine_limit=config.machine_limit, use_individual_limits=config.use_individual_limits
    )
    if 'recipe_book' not in st.session_state:
        st.session_state['update_machine_types'] = True
    crafting_chain = crafting_chain_finder.optimal_crafting_chain(
        machine_type_book, machine_options_book, config, recipe_weight_factor=0.000000001,
        update_machine_types=st.session_state['update_machine_types']
    )
    if crafting_chain is None:
        st.error('Crafting Chain could not be determined', icon="❗")

    st.session_state['recipe_book'] = recipe_book
    st.markdown('---')
    print_crafting_chain(crafting_chain_finder, crafting_chain, recipe_book, config)


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

        new_voltage_tier = VoltageTier.to_voltage_tier(selected_voltage_tier)
        recipe.machine.voltage_tier = new_voltage_tier
        recipe.fit_to_machine()

        new_machine_type = machine_type_book.get_machine_type(selected_machine)
        _LOGGER.debug(f'New machine: {new_machine_type}')
        if new_machine_type is not None:
            new_machine_options = machine_options_book.get_default_options(
                recipe.raw_recipe, new_machine_type, config.default_machine_options
            )
            recipe.update(
                config, machine_options_book, machine_type=new_machine_type, machine_options=new_machine_options
            )
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
