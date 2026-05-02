import streamlit as st
import logging
import sys
import numpy as np
from collections import defaultdict
from rapidfuzz import fuzz
from streamlit_searchbox import st_searchbox
import plotly.express as px
import plotly.graph_objects as go

from packages.configs.crafting_chain_config_db import CraftingChainConfig, load_config
from packages.crafting_chains.crafting_chain_database import CraftingChainDatabase
from packages.database_extraction.database_extractor import GTNHDatabase
from packages.utility.streamlit_functions import (
    load_database, load_crafting_chain_database, display_crafting_chain_recipe
)
from packages.recipes_db.material import Material
from packages.crafting_chains.crafting_chain_finder_highs import (
    CraftingChainFinder, OptimalSolution, CostConstraints, CostVectorCollection)
from packages.crafting_chains.crafting_chain_db import CraftingChain
from packages.utility.general_utility import time_to_seconds, is_contained_in, Timer

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


WEIGHT_EXP_MIN = -5.0
WEIGHT_EXP_MAX = 10.0
MAX_DISPLAYED_OPTIONS = 300
NUMBER_OF_COLUMNS = 3

_LOGGER.warning('\n\nSTARTING NEW PAGE')

st.set_page_config(
    page_title="GTNH: Crafting Chain Calculator",
    page_icon="🏭",
    layout="wide"
)
st.markdown('# GTNH Calculator')
st.markdown('## CraftingChainConfig File')
crafting_chain = None
machine_type_book = None
crafting_chain_database: CraftingChainDatabase | None = None
config: CraftingChainConfig | None = None
database: GTNHDatabase = load_database()

uploaded_file = st.file_uploader("Choose a config file to specify the recipe chain", type='yaml')
if uploaded_file is not None:
    if 'file_hash' not in st.session_state or st.session_state['file_hash'] != hash(uploaded_file):
        for key in st.session_state:
            if key == 'database':
                continue
            del st.session_state[key]
    st.session_state['file_hash'] = hash(uploaded_file)
    crafting_chain_database = load_crafting_chain_database(uploaded_file, database)
    config = crafting_chain_database.config

update = 'update' in st.session_state and st.session_state['update']
if 'selected_material' not in st.session_state:
    st.session_state.selected_material = None


def scatter_plot(
    data: list[tuple[OptimalSolution, CostConstraints]],
    cost_vectors: CostVectorCollection,
    crafting_chain_finder: CraftingChainFinder,
    title: str,
    x: str,
    y: str,
    label_x: str,
    label_y: str
):
    def get_value(cost_vector_name: str, solution: OptimalSolution) -> float:
        match cost_vector_name:
            case 'recipe_cost_vector':
                return np.dot(solution.recipe_vector, cost_vectors.recipe_cost_vector.vector).item()
            case 'eu_cost_vector':
                return crafting_chain_finder.get_eu_per_tick(solution)
            case 'machine_amount_cost_vector':
                return crafting_chain_finder.get_machine_amount(solution)

    data_x = [get_value(x, s) for s, _ in data]
    data_y = [get_value(y, s) for s, _ in data]
    labels = [f'Solution {i}' for i in range(len(data))]
    description = [f'{c}' for _, c in data]
    colors = ['cyan' for x in data]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data_x,
        y=data_y,
        mode='markers',
        marker=dict(
            size=12,
            color=colors
        ),
        text=labels,
        customdata=description,
        hovertemplate=
        "<b>%{text}</b><br>" "x: %{x}<br>" + "y: %{y}<br>" +
        "%{customdata}<extra></extra>"
    ))
    fig.update_layout(
        title=title,
        xaxis_title=label_x,
        yaxis_title=label_y
    )
    st.plotly_chart(fig)


def display_pareto_front(crafting_chain_finder: CraftingChainFinder, cost_vectors: CostVectorCollection):
    pareto_results = crafting_chain_finder.pareto_front(cost_vectors)
    a, b, c = st.columns(3)
    with a:
        scatter_plot(
            data=pareto_results,
            cost_vectors=cost_vectors,
            crafting_chain_finder=crafting_chain_finder,
            title='Material Cost vs. EU/t',
            x='recipe_cost_vector',
            y='eu_cost_vector',
            label_x='Material Cost',
            label_y='EU/t'
        )
    with b:
        scatter_plot(
            data=pareto_results,
            cost_vectors=cost_vectors,
            crafting_chain_finder=crafting_chain_finder,
            title='Material Cost vs. Machine Amount',
            x='recipe_cost_vector',
            y='machine_amount_cost_vector',
            label_x='Material Cost',
            label_y='Machine Cost'
        )
    with c:
        scatter_plot(
            data=pareto_results,
            cost_vectors=cost_vectors,
            crafting_chain_finder=crafting_chain_finder,
            title='EU/t vs. Machine Amount',
            x='eu_cost_vector',
            y='machine_amount_cost_vector',
            label_x='Recipe Cost',
            label_y='Machine Cost'
        )


if crafting_chain_database is not None and config is not None:
    if 'weight_materials' not in st.session_state:
        st.session_state['weight_materials'] = [m for m, a in config.weights.items() if a > 0]
    st.session_state['weight_materials'].sort(key=lambda m: m.id)
    if 'ipw_materials' not in st.session_state:
        st.session_state['ipw_materials'] = [m for m, a in config.infinite_production_weights.items() if a > 0]
    st.session_state['ipw_materials'].sort(key=lambda m: m.id)

    st.write(config)
    a, b = st.columns(2)

    a.metric("Recipes", crafting_chain_database.df_recipes.shape[0], border=True)
    b.metric("Materials", len(crafting_chain_database.extracted_materials), border=True)

    # Crafting Chain Database Exploration
    st.markdown('## Crafting Chain Database Exploration')

    st.markdown('### Recipe and Material Grades:')

    a, b = st.columns(2)
    with a:
        grading_counts = crafting_chain_database.get_recipe_grading_counts()
        non_reachable_recipe_amount = grading_counts[-1]
        del grading_counts[-1]
        data = {
            'Grading': list(grading_counts.keys()),
            'Amount': list(grading_counts.values())
        }
        fig = px.bar(data, x='Grading', y='Amount', title='Recipe Grading Distribution')
        st.plotly_chart(fig, width=500)
        st.metric("Recipes not reachable from inputs + infinite materials", non_reachable_recipe_amount, border=True)
    with b:
        grading_counts = crafting_chain_database.get_material_grading_counts()
        non_reachable_materials_amount = grading_counts[-1]
        del grading_counts[-1]
        data = {
            'Grading': list(grading_counts.keys()),
            'Amount': list(grading_counts.values())
        }
        fig = px.bar(data, x='Grading', y='Amount', title='Material Grading Distribution')
        st.plotly_chart(fig, width=500)
        st.metric("Materials not reachable from inputs + infinite materials", non_reachable_materials_amount,
                  border=True)

    def material_card(material: Material):
        with st.container(border=True, width=600):
            col1, col2 = st.columns([4, 1])

            with col1:
                if st.button(material.name, key=f"button_{material.id}", width='stretch'):
                    if st.session_state.selected_material is None:
                        st.session_state.selected_material = material
                        st.rerun()
                st.write(f'Mod: {material.mod}')
                st.write(f'Grading: {crafting_chain_database.material_grading[material] 
                         if material in crafting_chain_database.material_grading.keys() else '?'}')
            with col2:
                try:
                    st.image(f'db/images/{material.image_file_path}')
                except Exception as e:
                    pass

    mods_materials = crafting_chain_database.database.mod_set_materials()

    if st.session_state.selected_material is None:
        search = st.text_input("Search material")
        if search:
            search_terms = search.lower().split(' ')
            matching_materials = [
                m for m in crafting_chain_database.extracted_materials.values()
                if all(t in m.name.lower() for t in search_terms)
            ]
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

        with (material_info_tab):
            grade = (
                crafting_chain_database.material_grading[material]
                if material in crafting_chain_database.material_grading.keys() else -1
            )
            if grade >= 1:
                current_grade_materials = {material}
                for g in range(grade - 1, -1, -1):
                    st.markdown(f'**Grading Level {g}**')
                    current_grade_recipes = [
                        r for r in crafting_chain_database.recipes.values()
                        if crafting_chain_database.recipe_grading[r] == g and
                        any(o in current_grade_materials for o in r.get_outputs())
                    ]
                    current_grade_materials = {
                        m for r in current_grade_recipes for m, a in r.input_dict.items() if a < 0
                    }
                    st.write(current_grade_materials)
        with usage_tab:
            st.write('TODO')
        with recipes_tab:
            st.write('TODO')

    # Crafting Chain Optimization
    st.markdown('## Crafting Chain Optimization')

    crafting_chain_finder = CraftingChainFinder(
        crafting_chain_database, config=config, machine_limit=config.machine_limit, use_individual_limits=False
    )
    cost_vectors = crafting_chain_finder.get_default_cost_vectors()

    weighted_cost_vectors = [(cost_vectors[0], 1), (cost_vectors[1], 0), (cost_vectors[2], 0)]
    if 'crafting_chain' not in st.session_state or update:
        st.session_state['crafting_chain'] = crafting_chain_finder._optimal_crafting_chain(
            weighted_cost_vectors=weighted_cost_vectors, use_individual_limits=False,
            eu_per_tick_constraint=None, machine_amount_constraint=None
        )
    crafting_chain: CraftingChain = st.session_state['crafting_chain']

    if crafting_chain is None:
        st.error('Crafting Chain could not be determined!', icon="❗")
    else:
        st.success('Successfully determined the crafting chain!', icon="✅")

    if st.button('Display Pareto Front'):
        display_pareto_front(crafting_chain_finder, cost_vectors)

if crafting_chain is not None:
    time, _ = time_to_seconds(config.time)
    display_interval, display_interval_unit = time_to_seconds(config.display_interval)
    if display_interval != 1:
        display_interval_unit = display_interval_unit + 's'
    display_interval_string = f'{display_interval} {display_interval_unit}'

    st.markdown('### Crafting Chain Statistics')
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(crafting_chain.markdown_inputs(display_interval_string))
    with col2:
        st.markdown(crafting_chain.markdown_outputs(display_interval_string))
    st.markdown(crafting_chain.markdown_eu())
    st.write(f'Total number of machines: {crafting_chain.number_of_machines}')
    st.markdown('---')

    df = crafting_chain.to_dataframe(
        time_factor=display_interval / time,
        display_interval_string=display_interval_string
    )
    st.dataframe(df, hide_index=True)

    with st.expander('Material Grading'):
        grading = [(m, g) for m, g in crafting_chain.material_grading.items()]
        grading_level = defaultdict(list)
        for material, g in grading:
            grading_level[g].append(material)
        grading_levels = list(set(grading_level.keys()))
        grading_levels.sort()
        for g in grading_levels:
            if g < 0:
                continue
            st.markdown(f'#### Grading Level {g}')
            st.write(grading_level[g])

        looping_materials = (
            set(m for m, a in crafting_chain.total_material_needs.items() if a == 0) &
            set().union(*[set(r.get_outputs()) for r, a in crafting_chain.recipe_amounts.items() if a > 0])
        )

    with st.expander('Looping Materials'):
        st.markdown(f'#### Reachable')
        st.write(looping_materials & set(m for m, g in crafting_chain.material_grading.items() if g >= 0))
        st.markdown(f'#### Unreachable')
        st.write(looping_materials & set(m for m, g in crafting_chain.material_grading.items() if g < 0))


@st.fragment()
def recipe_configuration(crafting_chain: CraftingChain):
    _LOGGER.info('Displaying recipe configuration')

    st.markdown('## Recipe Configuration')
    crafting_chain_recipes = crafting_chain.recipe_list
    for recipe in crafting_chain_recipes:
        display_crafting_chain_recipe(recipe)


if crafting_chain is not None:
    recipe_configuration(crafting_chain)
