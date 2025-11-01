import streamlit as st
from io import StringIO
import logging
import sys

from packages.configs.config import Config
from packages.crafting_chains.crafting_chain import CraftingChain
from packages.recipes.recipe_book import RecipeBook
from packages.crafting_chains.crafting_chain_finder import CraftingChainFinder
from packages.configs.config import load_config
from packages.utility.general_utility import time_to_seconds
from packages.recipes.machine_options.machine_option_books import load_possible_machine_options

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


# Run via: streamlit run ./src/gtnh_calculator/streamlit-app.py

# Deploy: Install poetry plugin: poetry self add poetry-plugin-export
# Then create requirements.txt: poetry export -f requirements.txt -o requirements.txt


machine_options_path = 'config/fixed_settings/machine_options.yaml'
machine_options_book = load_possible_machine_options(machine_options_path)

st.set_page_config(layout="wide")
st.markdown('# GTNH Calculator')


# def display_input_row(index):
#     left, middle = st.columns(2)
#     left.text_input('Material name', key=f'first_{index}')
#     middle.text_input('Restriction', key=f'middle_{index}')
#
#
# def increase_rows():
#     st.session_state['rows'] += 1
#
#
# def decrease_rows():
#     st.session_state['rows'] = max(st.session_state['rows'] - 1, 1)
#
#
# if 'rows' not in st.session_state:
#     st.session_state['rows'] = 1

st.markdown('## Recipe Lists')
st.markdown('Recipes are stored in the following Google Spreadsheet: https://docs.google.com/spreadsheets/d/1OSog0iIKua5T7ms0Iv9OZxCR1Qw45QSPtZd7EDP-FK4/edit?usp=sharing')
st.markdown('Please **DO NOT** change any recipes in existing tabs, but create a separate tab!')

st.markdown('## Config File')
crafting_chain = None
recipe_book = None
config = None

uploaded_file = st.file_uploader("Choose a config file to specify the recipe chain", type='yaml')
if uploaded_file is not None:
    # To convert to a string based IO:
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    string_data = stringio.read()

    config, recipe_book = load_config(uploaded_file, machine_options_book)
    st.write(config)

    crafting_chain_finder = CraftingChainFinder(recipe_book)
    crafting_chain = crafting_chain_finder.draw_optimal_crafting_chain(config, recipe_weight_factor=0.0000001)

st.markdown('---')

# st.button('Add material', on_click=increase_rows)
# st.button('Remove material', on_click=decrease_rows)
# for i in range(st.session_state['rows']):
#     display_input_row(i)

# with st.form(key='recipe_chain_config'):
#     st.markdown('### Input materials')
#
#
#
#     st.markdown('### Output materials')
#
#     submit_button = st.form_submit_button(label='Calculate Recipe Chain')


# Show the results
# st.markdown('## Summary')
# st.markdown('### Input materials')
# if all(is_empty(st.session_state[f'first_{i}']) for i in range(st.session_state['rows'])):
#     st.write('None')
# else:
#     for i in range(st.session_state['rows']):
#         st.write(
#             st.session_state[f'first_{i}'],
#             st.session_state[f'middle_{i}']
#         )

if isinstance(crafting_chain, CraftingChain) and isinstance(recipe_book, RecipeBook) and isinstance(config, Config):
    time, _ = time_to_seconds(config.time)
    display_interval, display_interval_name = time_to_seconds(config.display_interval)
    if display_interval != 1:
        display_interval_name = display_interval_name + 's'

    df = crafting_chain.to_dataframe(
        time_factor=display_interval / time,
        time_interval=f'{display_interval} {display_interval_name}'
    )
    statistics = crafting_chain.print(
        time_factor=display_interval / time,
        time_interval=f'{display_interval} {display_interval_name}'
    )
    df['Checkbox'] = False
    df['Machine Group'] = ''
    st.markdown('## Crafting Chain Statistics')
    st.write(statistics.markdown_string())
    st.markdown('---')

    st.markdown('## Complete Crafting Chain')
    column_config = {
        'EU/t': st.column_config.NumberColumn(),
        'Checkbox': st.column_config.CheckboxColumn('Checkbox', width='small')
    }
    if st.toggle("Enable editing"):
        edited_data = st.data_editor(df, column_config=column_config, width='stretch', height='stretch')
    else:
        st.dataframe(df, column_config=column_config, width='stretch', height='stretch')
