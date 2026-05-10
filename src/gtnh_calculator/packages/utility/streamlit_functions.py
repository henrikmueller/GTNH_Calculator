import math
from string import Template
import streamlit as st
import logging
import sys
from io import BytesIO
from streamlit_extras.stylable_container import stylable_container

from packages.crafting_chains.crafting_chain_database import CraftingChainDatabase
from packages.database_extraction.database_extractor import GTNHDatabase, DatabaseExtractor
from packages.configs.crafting_chain_config_db import CraftingChainConfig, load_config
from packages.recipes_db.machines import Machine
from packages.recipes_db.recipes import Recipe
from packages.utility.general_utility import get_base64_image
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
            crafting_chain_database.initialize_machine_options()
        except DataLoadingException as e:
            st.error(e, icon="❗")
            raise Exception(f"Data loading failed: {e}")
    else:
        crafting_chain_database = st.session_state['crafting_chain_database']
    return crafting_chain_database


def display_recipe(recipe_row, valid_machines: list[Machine]):
    with stylable_container(
            key=f"recipe_container_{recipe_row.Index}",
            css_styles="""
        {
            background-color: #2b2b2b;
            padding: 15px;
            border-radius: 10px;
        }
        """
    ):
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
          bottom: 0;
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

        machines_html = ''
        for machine in valid_machines:
            try:
                img_base64 = get_base64_image(f'db/images/{machine.item.image_file_path}')
                machines_html += f"""<div class="tooltip">
                    <img src="data:image/png;base64,{img_base64}" width="36">
                    <span class="tooltiptext">{machine.__str__()}</span>
                </div>
                """
            except Exception as e:
                _LOGGER.warning(e)

        inputs_html = ''
        for i, (input_group, amount) in enumerate(recipe_row.TOTAL_INPUTS.items()):
            material = list(input_group.materials)[0]
            try:
                img_base64 = get_base64_image(f'db/images/{material.image_file_path}')
                inputs_html += f"""<div class="tooltip">
                    <img src="data:image/png;base64,{img_base64}" width="36">
                    <div class="tooltip-number">{abs(int(amount))}</div>
                    <span class="tooltiptext">{material.name}</span>
                </div>
                """
            except Exception as e:
                _LOGGER.warning(e)

        outputs_html = ''
        for i, (output, amount, probability) in enumerate(recipe_row.OUTPUTS.values()):
            try:
                tooltip = f'{output.name}'
                if probability < 1:
                    tooltip += f' ({100*probability:.2g}%)'
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
        if not math.isnan(recipe_row.DURATION):
            info_string += f'**Processing Time**: {recipe_row.DURATION:.6g}s  \n'
        if not math.isnan(recipe_row.VOLTAGE):
            info_string += f'**Voltage**: {int(recipe_row.VOLTAGE):.6g} EU/t  \n'
        if not math.isnan(recipe_row.AMPERAGE):
            info_string += f'**Amperage**: {int(recipe_row.AMPERAGE):.6g}A  \n'
        if not (math.isnan(recipe_row.DURATION) or math.isnan(recipe_row.VOLTAGE) or math.isnan(recipe_row.AMPERAGE)):
            total_eu = recipe_row.VOLTAGE * recipe_row.AMPERAGE * recipe_row.DURATION * 20
            info_string += f'**Total EU**: {total_eu:.6g} EU  \n'
        if recipe_row.ADDITIONAL_INFO:
            info_string += f'{recipe_row.ADDITIONAL_INFO}  \n'
        if info_string:
            st.markdown(info_string)


def display_crafting_chain_recipe(recipe: Recipe):
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
                key=f"valid_machines_{recipe.id}",
                width=500,
                format_func=lambda index: options[index]
            )
            selected_machine = valid_machines[selected_machine_index]
            st.write(f'Selected machine: {selected_machine.__str__()}')
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
            if not recipe.update(machine=selected_machine, voltage_tier=voltage_tier, log=False):
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
              bottom: 0;
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
            info_string += f'**Processing Time**: {recipe.processing_time:.6g}s  \n'
            info_string += f'**Voltage**: {abs(recipe.eu_per_tick):.6g} EU/t  \n'
            info_string += f'**Total EU**: {abs(recipe.total_eu):.6g} EU  \n'
            if recipe.raw_recipe.recipe_options:
                info_string += f'{recipe.raw_recipe.recipe_options}  \n'
            if recipe.used_parallels > 1:
                info_string += f'Used parallels: {recipe.used_parallels}  \n'
            if info_string:
                st.markdown(info_string)
