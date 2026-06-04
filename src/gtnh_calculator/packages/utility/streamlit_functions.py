from string import Template
from typing import Iterable
import streamlit as st
import logging
from typing import Dict
from io import BytesIO
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
from packages.configs.crafting_chain_config_db import CraftingChainConfig, load_config
from packages.recipes_db.material import Material
from packages.recipes_db.machine_options.machine_option_books import MachineOptionsBook
from packages.recipes_db.machine_options.machine_option_types import MachineOptionType
from packages.recipes_db.machine_options.machine_options import MachineOption
from packages.recipes_db.instantiated_recipes import InstantiatedRecipe
from packages.utility.general_utility import get_base64_image, format_float
from packages.recipes_db.voltage_tiers import VoltageTier
from packages.exceptions import GTNHCalculatorException
from packages.crafting_chains.crafting_chain_finder_highs import (
    CraftingChainFinder, OptimalSolution, CostConstraints, CostVectorCollection)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


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


# def load_database_old() -> GTNHDatabase:
#     database_extractor = DatabaseExtractor(validity_check=False)

#     with st.spinner('Decompressing database...', show_time=True):
#         database_extractor.decompress_database()

#     progress_text = 'Loading GTNH recipes...'
#     if 'database' not in st.session_state:
#         progress_bar = st.progress(0, text=progress_text)
#         gen = database_extractor.extract_database()

#         try:
#             while True:
#                 progress = next(gen)
#                 progress_bar.progress(progress, text=progress_text)

#         except StopIteration as e:
#             database: GTNHDatabase = e.value
#             database.add_eu()
#             # TODO: Add EU to inputs and outputs.
#             progress_bar.progress(1.0, text=f"Successfully extracted all recipes from the database.")
#             st.session_state['database'] = database
#     else:
#         st.progress(1.0, text=f"Successfully extracted all recipes from the database.")
#         database = st.session_state['database']
#     return database


def load_crafting_chain_database(uploaded_file: BytesIO | str, database: GTNHDatabase) -> CraftingChainDatabase | None:
    try:
        config = load_config(uploaded_file, database)
        crafting_chain_database = CraftingChainDatabase.create_crafting_chain_database(
            database=database, config=config, validity_check=True)
    except GTNHCalculatorException as e:
        st.error(e, icon="❗")
        return None
    return crafting_chain_database


# def display_recipe(recipe_row, valid_machines: Iterable[Machine]):
#     with stylable_container(
#             key=f"recipe_container_{recipe_row.ID}",
#             css_styles="""
#         {
#             background-color: #2b2b2b;
#             padding: 15px;
#             border-radius: 10px;
#         }
#         """
#     ):
#         html = Template("""
#         <style>
#         .recipe-row {
#           display: grid;
#           grid-template-columns: 1fr auto 1fr;
#           align-items: center;
#           width: 100%;
#           gap: 8px;
#           margin-bottom: 1.8rem;
#         }

#         .inputs {
#           display: flex;
#           flex-wrap: wrap;
#           gap: 8px;
#           justify-content: flex-end;
#         }

#         .outputs {
#           display: flex;
#           flex-wrap: wrap;
#           gap: 8px;
#           justify-content: flex-start;
#         }

#         .arrow-container {
#           display: flex;
#           justify-content: center;
#           align-items: center;
#           padding: 0 10px;
#         }

#         .tooltip {
#           position: relative;
#           display: inline-block;
#         }

#         .tooltip-number {
#           position: absolute;
#           bottom: 0;
#           right: 0;
#           color: white;
#           font-size: 10px;
#         }

#         .tooltip .tooltiptext {
#           visibility: hidden;
#           display: block;
#           background-color: rgba(0,0,0,0.9);
#           color: white;
#           padding: 5px 8px;
#           border-radius: 5px;
#           position: absolute;
#           bottom: 110%;
#           left: 50%;
#           transform: translateX(-50%);
#           min-width: 40px;
#           max-width: min(2500px, 20vw);
#           width: max-content;
#           white-space: normal;
#           word-wrap: break-word;
#         }

#         .tooltip:hover .tooltiptext {
#           visibility: visible;
#         }

#         .arrow {
#           position: relative;
#           width: 40px;
#           height: 2px;
#           background: white;
#         }

#         .arrow::after {
#           content: "";
#           position: absolute;
#           right: -3px;
#           top: -4px;

#           border-top: 5px solid transparent;
#           border-bottom: 5px solid transparent;
#           border-left: 10px solid white;
#         }
#         </style>

#         $machines_html
#         <div class="recipe-row">
#           <div class="inputs">
#             $inputs_html
#           </div>

#           <div class="arrow-container">
#             <div class="arrow"></div>
#           </div>

#           <div class="outputs">
#             $outputs_html
#           </div>
#         </div>
#         """)

#         machines_html = ''
#         for machine in valid_machines:
#             try:
#                 img_base64 = get_base64_image(f'db/images/{machine.item.image_file_path}')
#                 machines_html += f"""<div class="tooltip">
#                     <img src="data:image/png;base64,{img_base64}" width="36">
#                     <span class="tooltiptext">{machine.__str__()}</span>
#                 </div>
#                 """
#             except Exception as e:
#                 _LOGGER.warning(e)

#         inputs_html = ''
#         for i, (input_group, amount) in enumerate(recipe_row.TOTAL_INPUTS.items()):
#             material = list(input_group.materials)[0]
#             try:
#                 img_base64 = get_base64_image(f'db/images/{material.image_file_path}')
#                 inputs_html += f"""<div class="tooltip">
#                     <img src="data:image/png;base64,{img_base64}" width="36">
#                     <div class="tooltip-number">{abs(int(amount))}</div>
#                     <span class="tooltiptext">{material.name}</span>
#                 </div>
#                 """
#             except Exception as e:
#                 _LOGGER.warning(e)

#         outputs_html = ''
#         for i, (output, amount, probability) in enumerate(recipe_row.OUTPUTS.values()):
#             try:
#                 tooltip = f'{output.name}'
#                 if probability < 1:
#                     tooltip += f' ({100*probability:.2g}%)'
#                 img_base64 = get_base64_image(f'db/images/{output.image_file_path}')
#                 outputs_html += f"""<div class="tooltip">
#                     <img src="data:image/png;base64,{img_base64}" width="36">
#                     <div class="tooltip-number">{abs(int(amount))}</div>
#                     <span class="tooltiptext">{tooltip}</span>
#                 </div>
#                 """
#             except Exception as e:
#                 _LOGGER.warning(e)
#         st.markdown(
#             html.substitute(inputs_html=inputs_html, outputs_html=outputs_html, machines_html=machines_html),
#             unsafe_allow_html=True
#         )
#         info_string = ''
#         if not math.isnan(recipe_row.DURATION):
#             info_string += f'**Processing Time**: {recipe_row.DURATION:.6g}s  \n'
#         if not math.isnan(recipe_row.VOLTAGE):
#             info_string += f'**Voltage**: {int(recipe_row.VOLTAGE):.6g} EU/t  \n'
#         if not math.isnan(recipe_row.AMPERAGE):
#             info_string += f'**Amperage**: {int(recipe_row.AMPERAGE):.6g}A  \n'
#         if not (math.isnan(recipe_row.DURATION) or math.isnan(recipe_row.VOLTAGE) or math.isnan(recipe_row.AMPERAGE)):
#             total_eu = recipe_row.VOLTAGE * recipe_row.AMPERAGE * recipe_row.DURATION * 20
#             info_string += f'**Total EU**: {total_eu:.6g} EU  \n'
#         if recipe_row.ADDITIONAL_INFO:
#             info_string += f'{recipe_row.ADDITIONAL_INFO}  \n'
#         if info_string:
#             st.markdown(info_string)


@st.fragment()
def display_crafting_chain_recipe(instantiated_recipe: InstantiatedRecipe, machine_options_book: MachineOptionsBook):
    valid_machines = sorted(instantiated_recipe.valid_machines, key=lambda m: m.minimal_voltage_tier())
    with st.container(border=True):
        # with stylable_container(
        #         key=f"recipe_container_{recipe.id}",
        #         css_styles=""",
        #     {
        #         background-color: #2b2b2b;
        #         padding: 15px;
        #         border-radius: 10px;
        #     }
        #     """
        # ):
        a, b = st.columns(2)
        with a:
            aa, bb = st.columns(2)

            with aa:  # Select machine
                if f"selected_machine_{instantiated_recipe.id}" in st.session_state:
                    selected_machine = st.session_state[f"selected_machine_{instantiated_recipe.id}"]
                else:
                    selected_machine = instantiated_recipe.machine
                st.markdown(f'#### {selected_machine.name}')
                st.markdown(f'Recipe ID: {instantiated_recipe.id}')

                @st.dialog("Select Machine")
                def change_machine():
                    for i, machine in enumerate(valid_machines):
                        a, b = st.columns([0.5, 5], gap='small')
                        with a:
                            material_image(machine.item)
                        with b:
                            if st.button(machine.name, key=f"vote_{instantiated_recipe.id}_machine_{i}"):
                                st.session_state[f"selected_machine_{instantiated_recipe.id}"] = machine
                                st.rerun()

                c, d = st.columns([0.5, 5], gap='small', vertical_alignment='center')
                with c:
                    material_image(selected_machine.item)
                with d:
                    if st.button('Change Machine', key=f"change_machine_{instantiated_recipe.id}", type='tertiary'):
                        change_machine()

                # Select machine options
                machine_option_dict: Dict[MachineOptionType, MachineOption] = {}
                for machine_option_type in instantiated_recipe.machine_options.valid_options:
                    option_name = machine_option_type.name.replace('_', ' ').title()
                    if f"selected_option_{instantiated_recipe.id}_{machine_option_type}" in st.session_state:
                        selected_option = st.session_state[f"selected_option_{instantiated_recipe.id}_{machine_option_type}"]
                    else:
                        selected_option = instantiated_recipe.machine_options.get_option(machine_option_type)
                    machine_option_dict[machine_option_type] = selected_option

                    @st.dialog(f"Select {option_name}")
                    def change_machine_option(machine_option_type: MachineOptionType):
                        for i, machine_option in enumerate(
                            machine_options_book.get_machine_option_list(machine_option_type, rank=lambda o: o.tier)):
                            a, b = st.columns([0.5, 5], gap='small')
                            with a:
                                if machine_option.material is not None:
                                    material_image(machine_option.material)
                            with b:
                                text = f'{machine_option.name} (Tier {machine_option.tier})' if machine_option.tier >= 0 else machine_option.name
                                if st.button(text, key=f"vote_{instantiated_recipe.id}_{machine_option_type.name}_{i}"):
                                    st.session_state[f"selected_option_{instantiated_recipe.id}_{machine_option_type}"] = machine_option
                                    st.rerun()

                    with c:
                        if selected_option.material is not None:
                            material_image(selected_option.material)
                    with d:
                        if st.button(f'Change {option_name}', key=f"change_{instantiated_recipe.id}_{machine_option_type.name}", 
                                    type='tertiary'):
                            change_machine_option(machine_option_type)
                
            with bb:  # Select voltage tier
                valid_voltage_tiers = [v for v in selected_machine.voltage_tiers if v >= instantiated_recipe.minimum_voltage_tier]
                if instantiated_recipe.voltage_tier in valid_voltage_tiers:
                    initial_voltage_tier = instantiated_recipe.voltage_tier
                else:
                    initial_voltage_tier = min(valid_voltage_tiers)

                # Reset selectbox on faulty voltage tier
                if f"reset_vt_{instantiated_recipe.id}" not in st.session_state:
                    st.session_state[f"reset_vt_{instantiated_recipe.id}"] = True
                if st.session_state[f"reset_vt_{instantiated_recipe.id}"]:
                    st.session_state[f"voltage_tier_select_{instantiated_recipe.id}"] = valid_voltage_tiers.index(initial_voltage_tier)
                    st.session_state[f"reset_vt_{instantiated_recipe.id}"] = False

                options = {
                    index: VoltageTier.voltage_tier_name(v) for index, v in enumerate(valid_voltage_tiers)
                }
                voltage_tier_index = st.selectbox(
                    'Voltage Tier',
                    options=options.keys(),
                    key=f"voltage_tier_select_{instantiated_recipe.id}",
                    width=100,
                    format_func=lambda index: options[index]
                )
                voltage_tier = valid_voltage_tiers[voltage_tier_index]

            # Apply changes
            if not instantiated_recipe.update(
                machine=selected_machine, voltage_tier=voltage_tier, machine_option_dict=machine_option_dict, log=False
            ):
                _LOGGER.warning(f'Invalid recipe update: {selected_machine}. '
                              f'VTs: {selected_machine.voltage_tiers}. Selected: {voltage_tier}. '
                              f'Initial: {initial_voltage_tier}. Valid: {valid_voltage_tiers}. '
                              f'Recipe min: {instantiated_recipe.minimum_voltage_tier} ')
                st.toast(f'Invalid recipe configuration (Recipe ID: {instantiated_recipe.id})', icon='❗', duration='long')
                st.session_state[f"selected_machine_{instantiated_recipe.id}"] = instantiated_recipe.machine
                st.session_state[f"reset_vt_{instantiated_recipe.id}"] = True
                for machine_option_type in instantiated_recipe.machine_options.valid_options:
                    st.session_state[f"selected_option_{instantiated_recipe.id}_{machine_option_type}"] = \
                        instantiated_recipe.machine_options.get_option(machine_option_type)
                st.rerun()
        with b:
            html = Template("""
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
            """)

            try:
                img_base64 = get_base64_image(f'db/images/{instantiated_recipe.machine.item.image_file_path}')
                machines_html = f"""<div class="tooltip">
                    <img src="data:image/png;base64,{img_base64}" width="36">
                    <span class="tooltiptext">{instantiated_recipe.machine.__str__()}</span>
                </div>
                """
            except Exception as e:
                machines_html = ''
                _LOGGER.warning(e)

            inputs_html = ''
            for i, (input, amount) in enumerate(instantiated_recipe.input_dict.items()):
                try:
                    tooltip = f'{format_float(abs(amount), decimal_places=1, separate_thousands=True)} {input.name}'
                    img_base64 = get_base64_image(f'db/images/{input.image_file_path}')
                    inputs_html += f"""<div class="tooltip">
                        <img src="data:image/png;base64,{img_base64}" width="36">
                        <div class="tooltip-number">{abs(int(amount))}</div>
                        <span class="tooltiptext">{tooltip}</span>
                    </div>
                    """
                except Exception as e:
                    _LOGGER.warning(e)

            outputs_html = ''
            for i, (output, amount, probability) in enumerate(instantiated_recipe.adapted_recipe.output_specifications.values()):
                try:
                    tooltip = f'{f"{format_float(amount, decimal_places=1, separate_thousands=True)} {output.name}"}'
                    if probability < 1:
                        tooltip += f' ({100 * probability:.2g}%)'
                    img_base64 = get_base64_image(f'db/images/{output.image_file_path}')
                    outputs_html += f"""<div class="tooltip">
                        <img src="data:image/png;base64,{img_base64}" width="36">
                        <div class="tooltip-number">{int(amount)}</div>
                        <span class="tooltiptext">{tooltip}</span>
                    </div>
                    """
                except Exception as e:
                    _LOGGER.warning(e)

            st.markdown(
                html.substitute(inputs_html=inputs_html, outputs_html=outputs_html, machines_html=machines_html),
                unsafe_allow_html=True
            )
            info_string = ''
            if instantiated_recipe.processing_time > 0:
                t = format_float(instantiated_recipe.processing_time, decimal_places=2, separate_thousands=True)
                info_string += f'**Processing Time**: {t}s  \n'
            if instantiated_recipe.eu_per_tick != 0:
                v = format_float(abs(instantiated_recipe.eu_per_tick), decimal_places=2, separate_thousands=True)
                t = format_float(abs(instantiated_recipe.total_eu), decimal_places=2, separate_thousands=True)
                info_string += f'**Voltage**: {v} EU/t ({int(instantiated_recipe.adapted_recipe.amperage)}A)  \n'
                info_string += f'**Total EU**: {t} EU  \n'
            if instantiated_recipe.recipe_options:
                info_string += f'{instantiated_recipe.recipe_options}  \n'
            if instantiated_recipe.used_parallels != 1:
                info_string += f'Used parallels: {instantiated_recipe.used_parallels}  \n'
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


# def material_image(material: Material, width: int = 36):
#     try:
#         img_base64 = get_base64_image(f'db/images/{material.image_file_path}')

#         st.html(f"""
#             <div style="
#                 display:flex;
#                 align-items:center;
#                 height:100%;
#             ">
#                 <img
#                     src="data:image/png;base64,{img_base64}"
#                     width="{width}"
#                     title="{material.name}"
#                 />
#             </div>
#         """)
#     except Exception as e:
#         pass


def material_image(material: Material, width: int = 36):
    html = Template("""
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
        """)

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
            html.substitute(inputs_html=inputs_html),
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
