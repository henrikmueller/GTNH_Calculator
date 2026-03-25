import math
from string import Template
import streamlit as st
import logging
import sys
from streamlit_extras.stylable_container import stylable_container
from collections import defaultdict

from packages.utility.general_utility import get_base64_image

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


def display_recipe(recipe_row):
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

        # <div style="display:flex; justify-content:center;">
        #           <div class="recipe-row">
        #             $inputs_html <div class="arrow"></div> $outputs_html
        #           </div>
        #         </div>

        machines_html = ''
        groups = defaultdict(set)
        for machine in recipe_row.MACHINES:
            groups[(frozenset(machine.machine_types), machine.multiblock)].add(machine)
        valid_machines = [min(group, key=lambda m: m.minimal_voltage_tier()) for group in groups.values()]
        valid_machines.sort(key=lambda m: m.multiblock)
        for machine in valid_machines:
            try:
                img_base64 = get_base64_image(f'db/images/{machine.item.image_file_path}')
                machines_html += f"""<div class="tooltip">
                    <img src="data:image/png;base64,{img_base64}" width="36">
                    <span class="tooltiptext">{machine.__repr__()}</span>
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
            info_string += f'**Total EU**: {total_eu:.6g} EU'
        if info_string:
            st.markdown(info_string)
