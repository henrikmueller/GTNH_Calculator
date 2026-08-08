from string import Template
from textwrap import dedent
from typing import Iterable
from frozendict import frozendict
import streamlit as st
import logging
from typing import Protocol
from rapidfuzz import fuzz
from streamlit_extras.stylable_container import stylable_container
import streamlit.components.v1 as components
from tomlkit import key
import numpy as np
import plotly.graph_objects as go
from pympler import asizeof
import os
import psutil

from packages.crafting_chains.crafting_chain_database import CraftingChainDatabase
from packages.database_extraction.database_extractor import DatabaseExtractor
from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.configs.crafting_chain_config_db import load_config
from packages.recipes_db.material import Material
from packages.recipes_db.recipe_options import RecipeOptions
from packages.recipes_db.machine_options.machine_option_books import MachineOptionsBook
from packages.recipes_db.machine_options.machine_option_types import MachineOptionType
from packages.recipes_db.machines import Machine
from packages.recipes_db.machine_options.machine_options import MachineOptions, MachineOption
from packages.recipes_db.instantiated_recipes import InstantiatedRecipe
from packages.utility.general_utility import get_base64_image, format_float
from packages.recipes_db.voltage_tiers import VoltageTier
from packages.exceptions import GTNHCalculatorException
from packages.crafting_chains.crafting_chain_finder_highs import (
    CraftingChainFinder, OptimalSolution, CostConstraints, CostVectorCollection)
from packages.streamlit.session_state import SessionState, RecipeEnvironmentsState, StoredRecipeEnvironment
from packages.streamlit.streamlit_logic import ConfigFile

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class DisplayableRecipe(Protocol):
    @property
    def processing_time(self) -> float:
        ...

    @property
    def input_dict(self) -> frozendict[Material, float]:
        ...

    @property
    def output_dict(self) -> frozendict[Material, float]:
        ...

    @property
    def output_specifications(self) -> frozendict[int, tuple[Material, float, float]]:
        ...

    @property
    def machine(self) -> Machine:
        ...

    @property
    def recipe_options(self) -> RecipeOptions:
        ...

    @property
    def parallelized(self) -> bool:
        ...

    def average_eu_per_tick_str(self, factor: float = 1.0) -> str:
        ...

    def average_total_eu_str(self, factor: float = 1.0) -> str:
        ...

    def used_parallels_str(self) -> str:
        ...

    @property
    def is_valid(self) -> bool:
        ...


def _flatten_html(html_string: str) -> str:
    """Strip indentation and blank lines so Streamlit's markdown parser
    doesn't mistake indented/blank-separated lines for a code block."""
    return '\n'.join(line.strip() for line in html_string.splitlines() if line.strip())


@st.cache_resource(show_spinner=False)
def load_database() -> GTNHDatabase:
    database_extractor = DatabaseExtractor(validity_check=False)

    with st.spinner('Decompressing database...', show_time=True):
        database_extractor.decompress_database()

    progress_text = 'Loading GTNH recipes...'
    progress_bar = st.progress(0, text=progress_text)
    gen = database_extractor.extract_database()

    try:
        while True:
            progress = next(gen)
            progress_bar.progress(progress, text=progress_text)

    except StopIteration as e:
        database: GTNHDatabase = e.value
        database.add_eu()
        progress_bar.progress(1.0, text=f"Successfully extracted all recipes from the database.")
    return database


def load_crafting_chain_database(
    uploaded_file: ConfigFile, database: GTNHDatabase, session_state: SessionState
) -> CraftingChainDatabase | None:
    crafting_chain_database: CraftingChainDatabase | None = None
    try:
        config = load_config(uploaded_file, database)
        crafting_chain_database = CraftingChainDatabase.create_crafting_chain_database(
            database=database, config=config)
    except GTNHCalculatorException as e:
        st.error(e, icon="❗")
    return crafting_chain_database


# def load_and_cache_crafting_chain_database(
#     uploaded_file: ConfigFile, database: GTNHDatabase, session_state: SessionState
# ) -> CraftingChainDatabase | None:
#     if session_state.crafting_chain_database is None:
#         try:
#             config = load_config(uploaded_file, database)
#             crafting_chain_database = CraftingChainDatabase.create_crafting_chain_database(
#                 database=database, config=config)
#             session_state.crafting_chain_database = crafting_chain_database
#         except GTNHCalculatorException as e:
#             st.error(e, icon="❗")
#             return None
#     else:
#         crafting_chain_database = session_state.crafting_chain_database
#     return crafting_chain_database


def adapt_crafting_chain_recipe(
    instantiated_recipe: InstantiatedRecipe, machine_options_book: MachineOptionsBook,
    recipe_environments_state: RecipeEnvironmentsState, amount: float = 1, key_suffix: str = ''
) -> None:
    """
    Allows the user to adapt the machine, voltage tier and machine options of an instantiated recipe.
    :param instantiated_recipe: The instantiated recipe to adapt.
    :param machine_options_book: The machine options book to use for selecting machine options.
    :return: None. The recipe_environments_state is adapted in place.
    """
    id = instantiated_recipe.id
    selected_recipe_environment = recipe_environments_state.get_recipe_environment(id, instantiated_recipe.recipe_environment)
    recipe_amount_str = format_float(amount, decimal_places=3, separate_thousands=True)

    aa, bb = st.columns(2)
    with aa:
        c, d = st.columns([0.5, 5], gap='small', vertical_alignment='center')
        with c:
            material_image(selected_recipe_environment.machine.item)
        with d:
            st.markdown(f'#### {f"{recipe_amount_str} " if amount != 1 else ""}{selected_recipe_environment.machine.machine_name_specified}')

        st.markdown(f'Recipe ID: {id}')
        valid_machines = sorted(instantiated_recipe.valid_machines, key=lambda m: m.minimal_voltage_tier())
        select_machine(
            instantiated_recipe=instantiated_recipe,
            selected_recipe_environment=selected_recipe_environment,
            valid_machines=valid_machines,
            recipe_environments_state=recipe_environments_state,
            key_suffix=key_suffix
        )
        select_voltage_tier(
            instantiated_recipe=instantiated_recipe,
            selected_recipe_environment=selected_recipe_environment,
            valid_machines=valid_machines,
            recipe_environments_state=recipe_environments_state,
            key_suffix=key_suffix
        )

    with bb: 
        select_machine_options(
            instantiated_recipe=instantiated_recipe, 
            machine_options=instantiated_recipe.machine_options,
            selected_recipe_environment=selected_recipe_environment, 
            recipe_environments_state=recipe_environments_state,
            machine_options_book=machine_options_book,
            key_suffix=key_suffix
        )


def select_machine(
    instantiated_recipe: InstantiatedRecipe, selected_recipe_environment: StoredRecipeEnvironment, valid_machines: list[Machine], 
    recipe_environments_state: RecipeEnvironmentsState, key_suffix: str = ''
):
    if len(valid_machines) <= 1:
        return
    
    id = instantiated_recipe.id

    def machine_changed(machine: Machine):
        if (not recipe_environments_state.has_recipe_environment(id) and machine == instantiated_recipe.machine):
            return
        _LOGGER.info(f'Updating stored machine for recipe {id}: {selected_recipe_environment.machine} -> {machine}')
        selected_recipe_environment.set_machine(machine)
        recipe_environments_state.set_recipe_environment(id, selected_recipe_environment, instantiated_recipe.recipe_environment)
    
    with st.expander('Change machine', width=400):
        for i, machine in enumerate(valid_machines):
            a, b = st.columns([0.5, 5], gap='small')
            with a:
                material_image(machine.item)
            with b:
                if st.button(machine.name, key=f"vote_{id}_machine_{i}_{key_suffix}", on_click=machine_changed, args=(machine,)):
                    pass


def select_voltage_tier(
    instantiated_recipe: InstantiatedRecipe, selected_recipe_environment: StoredRecipeEnvironment, valid_machines: list[Machine], 
    recipe_environments_state: RecipeEnvironmentsState, key_suffix: str = ''
):
    id = instantiated_recipe.id
    valid_voltage_tiers = [v for v in selected_recipe_environment.machine.voltage_tiers if v >= instantiated_recipe.minimum_voltage_tier]
    options = {
        index: VoltageTier.voltage_tier_name(v) for index, v in enumerate(valid_voltage_tiers)
    }
    def voltage_changed():
        index = st.session_state[f"voltage_tier_select_{id}_{key_suffix}"]
        selected_voltage_tier = valid_voltage_tiers[index]
        
        if (not recipe_environments_state.has_recipe_environment(id) 
            and selected_voltage_tier == instantiated_recipe.voltage_tier):
            return
        _LOGGER.info(f'Updating stored voltage tier for recipe {id}: {instantiated_recipe.voltage_tier} -> {selected_voltage_tier}')
        selected_recipe_environment.voltage_tier = selected_voltage_tier
        recipe_environments_state.set_recipe_environment(id, selected_recipe_environment, instantiated_recipe.recipe_environment)

    st.selectbox(
        'Voltage Tier',
        options=options.keys(),
        key=f"voltage_tier_select_{id}_{key_suffix}",
        width=100,
        index=valid_voltage_tiers.index(instantiated_recipe.voltage_tier),
        format_func=lambda index: options[index],
        on_change=voltage_changed
    )


def select_machine_options(
    instantiated_recipe: InstantiatedRecipe, machine_options: MachineOptions,
    selected_recipe_environment: StoredRecipeEnvironment, recipe_environments_state: RecipeEnvironmentsState,
    machine_options_book: MachineOptionsBook, key_suffix: str = ''
):
    if machine_options.valid_option_amount == 0:
        return
    id = instantiated_recipe.id
    st.markdown(f'#### Machine Options')

    def machine_option_changed(machine_option_type: MachineOptionType, machine_option: MachineOption):
        if (not recipe_environments_state.has_recipe_environment(id) and 
            machine_option == instantiated_recipe.machine_options.get_option(machine_option_type)):
            return
        _LOGGER.info(f'Updating stored machine option for recipe {id}: {machine_option_type.name} -> {machine_option}')
        selected_recipe_environment.machine_options.set_option(machine_option_type, machine_option)
        recipe_environments_state.set_recipe_environment(id, selected_recipe_environment, instantiated_recipe.recipe_environment)

    for machine_option_type in machine_options.valid_options:
        option_name = machine_option_type.name.replace('_', ' ').title()
        selected_option = selected_recipe_environment.machine_options.get_option(machine_option_type)

        c, d = st.columns([0.5, 5], gap='small', vertical_alignment='center')
        with c:
            if selected_option.material is not None:
                material_image(selected_option.material)
        with d:
            st.markdown(selected_option.name)

        with st.expander(f'Change {option_name}', width=400):
            for i, machine_option in enumerate(
                machine_options_book.get_machine_option_list(machine_option_type, rank=lambda o: o.tier)):
                a, b = st.columns([0.5, 5], gap='small')
                with a:
                    if machine_option.material is not None:
                        material_image(machine_option.material)
                with b:
                    text = f'{machine_option.name} (Tier {machine_option.tier})' if machine_option.tier >= 0 else machine_option.name
                    if st.button(
                        text, key=f"vote_{id}_{machine_option_type.name}_{i}_{key_suffix}", 
                        on_click=machine_option_changed, args=(machine_option_type, machine_option)
                    ):
                        pass


def display_crafting_chain_recipe(
    displayable_recipe: DisplayableRecipe, factor: float = 1.0, recipe_headline: str = ''
) -> None:
    html = Template(dedent("""
    <style>
    .recipe-row {
        display: grid;
        grid-template-columns: 1fr auto 1fr;
        align-items: center;
        width: 100%;
        gap: 8px;
        margin-bottom: 1.8rem;
    }

    .inputs {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: flex-end;
    }

    .outputs {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: flex-start;
    }

    .arrow-container {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 0 10px;
    }

    .tooltip {
        position: relative;
        display: inline-block;
    }

    .tooltip-number {
        position: absolute;
        bottom: -1;
        right: 0;
        color: white;
        font-size: 10px;
    }

    .tooltip .tooltiptext {
        visibility: hidden;
        display: block;
        background-color: rgba(0,0,0,0.9);
        color: white;
        padding: 5px 8px;
        border-radius: 5px;
        position: absolute;
        bottom: 110%;
        left: 50%;
        transform: translateX(-50%);
        min-width: 40px;
        max-width: min(2500px, 20vw);
        width: max-content;
        white-space: normal;
        word-wrap: break-word;
    }

    .tooltip:hover .tooltiptext {
        visibility: visible;
    }

    .arrow {
        position: relative;
        width: 40px;
        height: 2px;
        background: white;
    }

    .arrow::after {
        content: "";
        position: absolute;
        right: -3px;
        top: -4px;

        border-top: 5px solid transparent;
        border-bottom: 5px solid transparent;
        border-left: 10px solid white;
    }
    </style>

    $machines_html
    <div class="recipe-row">
        <div class="inputs">
            $inputs_html
        </div>

        <div class="arrow-container">
            <div class="arrow"></div>
        </div>

        <div class="outputs">
            $outputs_html
        </div>
    </div>
    """))

    try:
        img_base64 = get_base64_image(f'db/images/{displayable_recipe.machine.item.image_file_path}')
        machines_html = f"""<div class="tooltip">
            <img src="data:image/png;base64,{img_base64}" width="36">
            <span style="margin-left:6px;">{recipe_headline}</span>
            <span class="tooltiptext">{displayable_recipe.machine.__str__()}</span>
        </div>
        """
    except Exception as e:
        machines_html = ''
        _LOGGER.warning(e)

    inputs_html = ''
    for i, (input, amount) in enumerate(displayable_recipe.input_dict.items()):
        try:
            tooltip = f'{format_float(abs(factor * amount), decimal_places=1, separate_thousands=True)} {input.name}'
            img_base64 = get_base64_image(f'db/images/{input.image_file_path}')
            inputs_html += f"""<div class="tooltip">
                <img src="data:image/png;base64,{img_base64}" width="36">
                <div class="tooltip-number">{abs(int(factor * amount))}</div>
                <span class="tooltiptext">{tooltip}</span>
            </div>
            """
        except Exception as e:
            _LOGGER.warning(e)

    outputs_html = ''
    for i, (output, amount, probability) in enumerate(displayable_recipe.output_specifications.values()):
        try:
            tooltip = f'{f"{format_float(factor * amount, decimal_places=1, separate_thousands=True)} {output.name}"}'
            if probability < 1:
                tooltip += f' ({100 * probability:.2g}%)'
            img_base64 = get_base64_image(f'db/images/{output.image_file_path}')
            outputs_html += f"""<div class="tooltip">
                <img src="data:image/png;base64,{img_base64}" width="36">
                <div class="tooltip-number">{int(factor * amount)}</div>
                <span class="tooltiptext">{tooltip}</span>
            </div>
            """
        except Exception as e:
            _LOGGER.warning(e)

    st.markdown(
        _flatten_html(html.substitute(inputs_html=inputs_html, outputs_html=outputs_html, machines_html=machines_html)),
        unsafe_allow_html=True
    )
    if not displayable_recipe.is_valid:
        st.markdown('**INVALID RECIPE:** Please change machine and machine options.')
    info_string = ''
    if displayable_recipe.processing_time > 0:
        t = format_float(displayable_recipe.processing_time, decimal_places=2, separate_thousands=True)
        info_string += f'**Processing Time**: {t}s  \n'
    info_string += f'**Voltage**: {displayable_recipe.average_eu_per_tick_str(factor=factor)}  \n'
    info_string += f'**Total EU**: {displayable_recipe.average_total_eu_str(factor=factor)}  \n'
    if displayable_recipe.recipe_options:
        info_string += f'{displayable_recipe.recipe_options.markdown_string()}  \n'
    if displayable_recipe.parallelized:
        info_string += f'Used parallels: {displayable_recipe.used_parallels_str()}  \n'
    if info_string:
        st.markdown(info_string)


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


def material_image(material: Material, width: int = 36):
    html = Template(dedent("""
        <style>
        .tooltip {
            position: relative;
            display: block;
            margin-bottom: 1.18rem;
        }

        .tooltip .tooltiptext {
            visibility: hidden;
            display: block;
            background-color: rgba(0,0,0,0.9);
            color: white;
            padding: 5px 8px;
            border-radius: 5px;
            position: absolute;
            bottom: 110%;
            left: 50%;
            transform: translateX(-50%);
            min-width: 40px;
            max-width: min(2500px, 20vw);
            width: max-content;
            white-space: normal;
            word-wrap: break-word;
        }

        .tooltip:hover .tooltiptext {
            visibility: visible;
        }
        </style>

        <div class="inputs">
            $inputs_html
        </div>
        """))

    try:
        img_base64 = get_base64_image(f'db/images/{material.image_file_path}')
        inputs_html = f"""<div class="tooltip">
            <img
                src="data:image/png;base64,{img_base64}"
                width="{width}"
            >
            <span class="tooltiptext">{material.name}</span>
        </div>
        """
        st.markdown(
            _flatten_html(html.substitute(inputs_html=inputs_html)),
            unsafe_allow_html=True
        )
    except Exception as e:
        pass


def material_card(material: Material, button_key_prefix: str, key: str | None = None, multiselect: bool = True):
    with st.container(border=True, width=600):
        col1, col2 = st.columns([4, 1])

        with col1:
            if st.button(material.name, key=f"{button_key_prefix}_{material.id}", width='stretch'):
                if key is not None:
                    if multiselect:
                        if material in st.session_state[key]:
                            st.session_state[key].remove(material)
                        else:
                            st.session_state[key].add(material)
                    else:
                        st.session_state[key] = {material} if st.session_state[key] != {material} else set()
                    st.rerun()
            # st.markdown(f'<span style="font-size:12px;">{material.id.replace('~', '\~')}</span>', unsafe_allow_html=True)
            st.write(f'Mod: {material.mod}')
        with col2:
            copy_button(text='Copy ID', key=material.id)
            material_image(material)


def search_and_select_materials(
    database: GTNHDatabase,
    key: str,
    multiselect: bool = True,
    number_of_columns: int = 3,
    max_displayed_options: int = 300
) -> set[Material]:
    if key not in st.session_state or not isinstance(st.session_state[key], set):
        st.session_state[key] = set()

    st.write('Selected materials:' if multiselect else 'Selected material:')
    for material in st.session_state[key]:
        material_card(material, button_key_prefix='selected', key=key, multiselect=multiselect)

    selected_mods = st.multiselect(
        "Filter by mods",
        options=database.mod_set_materials(),
        default=None,
    )
    selected_type = st.multiselect(
        "Filter by material type",
        options=['item', 'fluid'],
        default=None,
    )
    filtered_materials = [
        m for m in database.extracted_materials.values() if
        (not selected_mods or m.mod in selected_mods) and (not selected_type or m.material_type in selected_type)
    ]
    st.write(f'Found {len(filtered_materials)} materials matching the selected filters.')

    matching_materials = search_material_name(materials=filtered_materials, label='Search Material')
    cols = st.columns(number_of_columns)
    for i, material in enumerate(matching_materials[:max_displayed_options]):
        with cols[i % number_of_columns]:
            material_card(material, button_key_prefix='display', key=key, multiselect=multiselect)
    
    return st.session_state[key]


def search_material_name(materials: Iterable[Material], label: str) -> list[Material]:
    search = st.text_input(label)
    if search:
        search_terms = search.lower().split(' ')
        matching_materials = [m for m in materials if all(t in m.name.lower() for t in search_terms)]
        matching_materials.sort(key=lambda s: fuzz.ratio(search.lower(), s.name.lower()), reverse=True)
        return matching_materials
    return []


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
    def get_value(cost_vector_name: str, solution: OptimalSolution) -> float | None:
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


def show_memory_usage(database: GTNHDatabase) -> None:
    process = psutil.Process(os.getpid())
    ram_mb = process.memory_info().rss / 1024**2
    session_mb = asizeof.asizeof(st.session_state) / 1024**2
    database_mb = asizeof.asizeof(database) / 1024**2

    st.sidebar.header("Memory")
    st.sidebar.metric("Process RAM", f"{ram_mb:.1f} MB")
    st.sidebar.metric("Database", f"{database_mb:.1f} MB")
    st.sidebar.metric("Session State", f"{session_mb:.1f} MB")
