import math
from string import Template
from typing import Iterable
import streamlit as st
import logging
import sys
from io import BytesIO
from rapidfuzz import fuzz
from streamlit_extras.stylable_container import stylable_container
import streamlit.components.v1 as components
from tomlkit import key

from packages.crafting_chains.crafting_chain_database import CraftingChainDatabase
from packages.database_extraction.database_extractor import DatabaseExtractor
from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.configs.crafting_chain_config_db import CraftingChainConfig, load_config
from packages.recipes_db import material
from packages.recipes_db.material import Material
from packages.recipes_db.machine_options.machine_option_books import MachineOptionsBook
from packages.recipes_db.recipes import Recipe
from packages.utility.general_utility import get_base64_image, format_float
from packages.exceptions import DataLoadingException
from packages.recipes_db.voltage_tiers import VoltageTier

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


def load_database() -> GTNHDatabase:
    progress_text = 'Loading GTNH recipes...'
    if 'database' not in st.session_state:
        database_extractor = DatabaseExtractor(validity_check=False)
        progress_bar = st.progress(0, text=progress_text)
        gen = database_extractor.extract_database()

        try:
            while True:
                progress = next(gen)
                progress_bar.progress(progress, text=progress_text)

        except StopIteration as e:
            database: GTNHDatabase = e.value
            database.add_eu()
            # TODO: Add EU to inputs and outputs.
            progress_bar.progress(1.0, text=f"Successfully extracted all recipes.")
            st.session_state['database'] = database
    else:
        st.progress(1.0, text=f"Successfully extracted all recipes.")
        database = st.session_state['database']
    return database


def load_crafting_chain_database(uploaded_file: BytesIO | str, database: GTNHDatabase) -> CraftingChainDatabase:
    if 'crafting_chain_database' not in st.session_state:
        try:
            loaded_config = load_config(uploaded_file, database)
            if 'config' not in st.session_state:
                st.session_state['config'] = loaded_config
            config: CraftingChainConfig = st.session_state['config']
            crafting_chain_database = CraftingChainDatabase.create_crafting_chain_database(
                database=database, config=config, validity_check=True)
            st.session_state['crafting_chain_database'] = crafting_chain_database
        except DataLoadingException as e:
            st.error(e, icon="❗")
            raise Exception(f"Data loading failed: {e}")
    else:
        crafting_chain_database = st.session_state['crafting_chain_database']
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


def display_crafting_chain_recipe(recipe: Recipe, machine_options_book: MachineOptionsBook):
    valid_machines = sorted(recipe.valid_machines, key=lambda m: m.minimal_voltage_tier())
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
            options = {
                index: m.__str__() for index, m in enumerate(valid_machines)
            }
            selected_machine_index = st.selectbox(
                'Machine',
                options=options.keys(),
                index=valid_machines.index(recipe.machine),
                key=f"selectbox_valid_machines_{recipe.id}",
                width=500,
                format_func=lambda index: options[index]
            )
            selected_machine = valid_machines[selected_machine_index]
            st.markdown(f'#### {selected_machine.name}')

            @st.dialog("Select Machine")
            def change_machine():
                for i, machine in enumerate(valid_machines):
                    a, b = st.columns([0.5, 5], gap='small')
                    with a:
                        material_image(machine.item)
                    with b:
                        if st.button(machine.name, key=f"vote_{recipe.id}_machine_{i}"):
                            st.rerun()

            if st.button('Change Machine', key=f"change_machine_{recipe.id}"):
                change_machine()

            # Select voltage tier
            valid_voltage_tiers = [v for v in selected_machine.voltage_tiers if v >= recipe.minimum_voltage_tier]
            if recipe.voltage_tier in valid_voltage_tiers:
              initial_voltage_tier = recipe.voltage_tier
            else:
              initial_voltage_tier = min(valid_voltage_tiers)

            options = {
                index: VoltageTier.voltage_tier_name(v) for index, v in enumerate(valid_voltage_tiers)
            }
            voltage_tier_index = st.selectbox(
                'Voltage Tier',
                options=options.keys(),
                index=valid_voltage_tiers.index(initial_voltage_tier),
                key=f"voltage_tier_select_{recipe.id}",
                width=300,
                format_func=lambda index: options[index]
            )
            voltage_tier = valid_voltage_tiers[voltage_tier_index]

            # Select machine options
            st.markdown("#### Machine Options:")
            for machine_option_type in selected_machine.machine_options.valid_options:
                option_name = machine_option_type.name.replace('_', ' ').title()
                @st.dialog(f"Select {option_name}")
                def change_machine_option():
                    for i, machine_option in enumerate(
                        machine_options_book.get_machine_option_list(machine_option_type, rank=lambda o: o.tier)):
                        a, b = st.columns([0.5, 5], gap='small')
                        with a:
                            if machine_option.material is not None:
                                material_image(machine_option.material)
                        with b:
                            text = f'{machine_option.name} (Tier {machine_option.tier})' if machine_option.tier >= 0 else machine_option.name
                            if st.button(text, key=f"vote_{recipe.id}_{machine_option_type.name}_{i}"):
                                st.rerun()

                current_machine_option = selected_machine.machine_options.get_option(machine_option_type)
                c, d = st.columns([0.5, 5], gap='small')
                with c:
                    if st.button(option_name, key=f"change_{recipe.id}_{machine_option_type.name}"):
                        change_machine_option()
                with d:
                    if current_machine_option.material is not None:
                        material_image(current_machine_option.material)

            # Apply changes
            if not recipe.update(machine=selected_machine, voltage_tier=voltage_tier, log=True):
              raise ValueError(f'Invalid recipe update: {selected_machine}. '
                               f'VTs: {selected_machine.voltage_tiers}. Selected: {voltage_tier} '
                               f'Valid: {valid_voltage_tiers} '
                               f'Recipe min: {recipe.minimum_voltage_tier} ')
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
              font-size: 11px;
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
                img_base64 = get_base64_image(f'db/images/{recipe.machine.item.image_file_path}')
                machines_html = f"""<div class="tooltip">
                    <img src="data:image/png;base64,{img_base64}" width="36">
                    <span class="tooltiptext">{recipe.machine.__str__()}</span>
                </div>
                """
            except Exception as e:
                machines_html = ''
                _LOGGER.warning(e)

            inputs_html = ''
            for i, (input, amount) in enumerate(recipe.input_dict.items()):
                try:
                    img_base64 = get_base64_image(f'db/images/{input.image_file_path}')
                    inputs_html += f"""<div class="tooltip">
                        <img src="data:image/png;base64,{img_base64}" width="36">
                        <div class="tooltip-number">{abs(int(amount))}</div>
                        <span class="tooltiptext">{input.name}</span>
                    </div>
                    """
                except Exception as e:
                    _LOGGER.warning(e)

            outputs_html = ''
            for i, (output, amount, probability) in enumerate(recipe.raw_recipe.output_specifications.values()):
                try:
                    tooltip = f'{output.name}'
                    if probability < 1:
                        tooltip += f' ({100 * probability:.2g}%)'
                    img_base64 = get_base64_image(f'db/images/{output.image_file_path}')
                    outputs_html += f"""<div class="tooltip">
                        <img src="data:image/png;base64,{img_base64}" width="36">
                        <div class="tooltip-number">{abs(int(amount))}</div>
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
            info_string += f'**Processing Time**: {format_float(recipe.processing_time, decimal_places=6)}s  \n'
            info_string += f'**Voltage**: {format_float(abs(recipe.eu_per_tick), decimal_places=2, separate_thousands=True)} EU/t  \n'
            info_string += f'**Total EU**: {format_float(abs(recipe.total_eu), decimal_places=2, separate_thousands=True)} EU  \n'
            if recipe.raw_recipe.recipe_options:
                info_string += f'{recipe.raw_recipe.recipe_options}  \n'
            if recipe.used_parallels > 1:
                info_string += f'Used parallels: {recipe.used_parallels}  \n'
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
    html = Template("""
        <style>
        .tooltip {
            position: relative;
            display: inline-block;
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
            <img src="data:image/png;base64,{img_base64}" width="{width}">
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

    search = st.text_input("Search material")
    if search:
        search_terms = search.lower().split(' ')
        matching_materials = [m for m in filtered_materials if all(t in m.name.lower() for t in search_terms)]
        matching_materials.sort(key=lambda s: fuzz.ratio(search.lower(), s.name.lower()), reverse=True)
    else:
        matching_materials = []

    cols = st.columns(number_of_columns)
    for i, material in enumerate(matching_materials[:max_displayed_options]):
        with cols[i % number_of_columns]:
            material_card(material, button_key_prefix='display', key=key, multiselect=multiselect)
    
    return st.session_state[key]
