import streamlit as st
import logging
import sys
import numpy as np
from collections import defaultdict
from rapidfuzz import fuzz
from streamlit_searchbox import st_searchbox
import plotly.express as px
from io import BytesIO

from packages.configs.crafting_chain_config_db import CraftingChainConfig, load_config
from packages.crafting_chains.crafting_chain_database import CraftingChainDatabase
from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.utility.streamlit_functions import (
    load_database, load_crafting_chain_database, display_crafting_chain_recipe, material_image,
    scatter_plot, display_pareto_front
)
from packages.recipes_db.material import Material
from packages.recipes_db.voltage_tiers import VoltageTier
from packages.crafting_chains.crafting_chain_finder_highs import (
    CraftingChainFinder, OptimalSolution, CostConstraints, CostVectorCollection)
from packages.crafting_chains.crafting_chain_db import CraftingChain
from packages.utility.general_utility import time_to_seconds, is_contained_in, Timer

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


WEIGHT_EXP_MIN = -5.0
WEIGHT_EXP_MAX = 10.0
MAX_DISPLAYED_MATERIALS = 100
NUMBER_OF_COLUMNS = 3
MAX_DISPLAYED_RECIPES = 30

machine_type_book = None
crafting_chain_database: CraftingChainDatabase | None
crafting_chain: CraftingChain | None
config: CraftingChainConfig | None

_LOGGER.warning('\n\nSTARTING NEW PAGE')

st.set_page_config(
    page_title="GTNH: Crafting Chain Calculator",
    page_icon="🏭",
    layout="wide"
)
st.markdown('# GTNH Calculator')
st.markdown('## CraftingChainConfig File')
database: GTNHDatabase = load_database()
uploaded_file = st.file_uploader("Choose a config file to specify the recipe chain", type='yaml')

with st.expander('Example files'):
    a, b = st.columns(2)

    with a:
        st.markdown('### Example 1: High Octane Gasoline')

        st.markdown(f'''Uses _Oil Combs_ from Forestry and _Spruce Logs_ to produce _High Octane Gasoline_. 
    The config file specifies that the crafting chain should be optimized for maximal Gasoline output, while 
    adhering to the specified material constraints.
    ''')
        example_hog = st.button('Calculate Crafting Chain', type='primary', key='example_hog')
        # material_image(database.extracted_materials['f~gregtech~highoctanegasoline'])

        st.markdown('**Download config file for High Octane Gasoline example**:')
        with open("config/fixed_examples/config_hog_example.yaml", "rb") as file:
            st.download_button(
                label="Download yaml file",
                data=file,
                file_name="config_hog_example.yaml"
            )

    with b:
        st.markdown('### Example 2: Platinum Line')
        
        st.markdown(f'''Extracts several elements from _Platinum Metallic Powder Dust_ via Sieving, Electrolysis, 
    Leaching, Pyrometallurgy, Solvent extraction and other processes: _Platinum_, _Rhodium_, _Ruthenium_, _Palladium_, 
    _Iridium_ and _Osmium_. The config file specifies that the crafting chain should be optimized for the unweighted 
    sum of all outputs, while adhering to the specified material constraints.
    ''')
        example_plat = st.button('Calculate Crafting Chain', type='primary', key='example_plat')
        # material_image(database.extracted_materials['i~bartworks~gt.bwMetaGenerateddust~47'])

        st.markdown('**Download config file for Platinum Line example**:')
        with open("config/fixed_examples/config_plat_line_example.yaml", "rb") as file:
            st.download_button(
                label="Download yaml file",
                data=file,
                file_name="config_plat_line_example.yaml"
            )


if uploaded_file is None:
    if example_hog:
        with open("config/fixed_examples/config_hog_example.yaml", "rb") as f:
            uploaded_file = BytesIO(f.read())
    elif example_plat:
        with open("config/fixed_examples/config_plat_line_example.yaml", "rb") as f:
            uploaded_file = BytesIO(f.read())


if uploaded_file is not None:
    with st.spinner('Reducing database...', show_time=True):
        if 'file_hash' not in st.session_state or st.session_state['file_hash'] != hash(uploaded_file):
            for key in st.session_state:
                if key == 'database':
                    continue
                del st.session_state[key]
        st.session_state['file_hash'] = hash(uploaded_file)
        crafting_chain_database = load_crafting_chain_database(uploaded_file, database)
else:
    crafting_chain_database = None if 'crafting_chain_database' not in st.session_state \
        else st.session_state['crafting_chain_database']

config = crafting_chain_database.config if crafting_chain_database is not None else None
update = 'update' in st.session_state and st.session_state['update']
if 'selected_material' not in st.session_state:
    st.session_state.selected_material = None


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
    b.metric("Materials", len(list(crafting_chain_database.materials)), border=True)

    with st.expander('Explore Crafting Chain Database'):
        tab1, tab2, tab3 = st.tabs(["Search Materials", "Search Recipes", "Explore Grading"], default="Search Recipes")

        # Material Exploration
        with tab1:
            st.markdown('### Explore Materials:')

            def material_card(crafting_chain_database: CraftingChainDatabase, material: Material):
                with st.container(border=True, width=600):
                    col1, col2 = st.columns([4, 1])

                    with col1:
                        print(material)
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

            search = st.text_input("Search material")
            if search:
                search_terms = search.lower().split(' ')
                matching_materials = [
                    m for m in crafting_chain_database.materials
                    if all(t in m.name.lower() for t in search_terms)
                ]
                matching_materials.sort(key=lambda s: fuzz.ratio(search.lower(), s.name.lower()), reverse=True)
            else:
                matching_materials = []

            cols = st.columns(NUMBER_OF_COLUMNS)
            for i, material in enumerate(matching_materials[:MAX_DISPLAYED_MATERIALS]):
                with cols[i % NUMBER_OF_COLUMNS]:
                    material_card(crafting_chain_database, material)

            # grade = (
            #     crafting_chain_database.material_grading[material]
            #     if material in crafting_chain_database.material_grading.keys() else -1
            # )
            # if grade >= 1:
            #     current_grade_materials = {material}
            #     for g in range(grade - 1, -1, -1):
            #         st.markdown(f'**Grading Level {g}**')
            #         current_grade_recipes = [
            #             r for r in crafting_chain_database.recipes.values()
            #             if crafting_chain_database.recipe_grading[r] == g and
            #             any(o in current_grade_materials for o in r.get_outputs())
            #         ]
            #         current_grade_materials = {
            #             m for r in current_grade_recipes for m, a in r.input_dict.items() if a < 0
            #         }
            #         st.write(current_grade_materials)

        # Recipe Exploration
        with tab2:
            st.markdown('### Explore Recipes:')

            a, b, c = st.columns(3)
            with a:
                selected_recipe_id = st.text_input("Filter by Recipe ID")
                selected_machine_names = set(st.multiselect(
                    "Filter recipes by machines",
                    options=[m.name for m in database.extracted_machines.values()],
                    default=None,
                ))
            with b:
                options = {
                    m.id: m.name for m in crafting_chain_database.materials
                }
                selected_input_ids = st.multiselect(
                    'Filter by Input Materials',
                    options=options.keys(),
                    key=f"input_select",
                    format_func=lambda index: options[index]
                )
                selected_inputs = {
                    crafting_chain_database.database.extracted_materials[id] for id in selected_input_ids
                }

                options = {
                    m.id: m.name for m in crafting_chain_database.materials
                }
                selected_output_ids = st.multiselect(
                    'Filter by Output Materials',
                    options=options.keys(),
                    key=f"output_select",
                    format_func=lambda index: options[index]
                )
                selected_outputs = {
                    crafting_chain_database.database.extracted_materials[id] for id in selected_output_ids
                }
            with c:
                selected_voltage_tiers = set(VoltageTier.to_voltage_tier(v) for v in st.multiselect(
                    "Filter recipes by voltage tiers",
                    options=[VoltageTier.voltage_tier_name(v) for v in VoltageTier.valid_voltage_tiers()],
                    default=[VoltageTier.voltage_tier_name(v) for v in VoltageTier.valid_voltage_tiers()],
                ))

            with st.spinner('Applying filters...', show_time=True):
                selected_machines = {m for m in database.extracted_machines.values() if m.name in selected_machine_names}
                
                filtered_recipes = list(crafting_chain_database.recipes.values())
                if selected_machines:
                    filtered_recipes = [
                        r for r in crafting_chain_database.recipes.values() if bool(selected_machines & r.valid_machines)
                    ]
                filtered_recipes = [
                    r for r in filtered_recipes if bool(selected_voltage_tiers & set(r.valid_voltage_tiers))
                ]
                if selected_recipe_id:
                    filtered_recipes = [
                        r for r in filtered_recipes if selected_recipe_id in r.id
                    ]
                if selected_inputs:
                    filtered_recipes = [
                        r for r in filtered_recipes if r.has_input(selected_inputs)
                    ]
                if selected_outputs:
                    filtered_recipes = [
                        r for r in filtered_recipes if r.has_output(selected_outputs)
                    ]

                show_all = st.toggle(f'Show all filtered recipes (Max {MAX_DISPLAYED_RECIPES})', value=False)
                total_recipe_count = len(filtered_recipes)
                filtered_recipes = filtered_recipes[:(MAX_DISPLAYED_RECIPES if show_all else 10)]

            st.success(f'Displaying {len(filtered_recipes)} / {total_recipe_count} recipes matching the selected filters.', icon="✅")

            if len(filtered_recipes) > 0:
                for recipe in filtered_recipes:
                    display_crafting_chain_recipe(recipe, database.machine_options_book)

        # Grading
        with tab3:
            st.markdown('### Recipe and Material Grades:')

            a, b = st.columns(2)
            with a:
                grading_counts = crafting_chain_database.get_recipe_grading_counts()
                non_reachable_recipe_amount = grading_counts[-1]
                st.metric("Recipes not reachable from inputs + infinite materials", non_reachable_recipe_amount, border=True)
            with b:
                grading_counts = crafting_chain_database.get_material_grading_counts()
                non_reachable_materials_amount = grading_counts[-1]
                st.metric("Materials not reachable from inputs + infinite materials", non_reachable_materials_amount,
                        border=True)

    
    # Check if all outputs can still be produced by at least one recipe
    outputs_missing = False
    for output in config.outputs:
        if not any(output in recipe.get_outputs() for recipe in crafting_chain_database.recipes.values()):
            outputs_missing = True
            st.error(f'''Output {output} cannot be produced by any recipe with the given config.
            Please check if the config is too restrictive (e.g. because of unlocked_voltage_tier).''', icon="❗")


    # Crafting Chain Optimization
    if not outputs_missing:
        st.markdown('## Crafting Chain Optimization')
        with st.spinner('Calculating optimal crafting chain...', show_time=True):

            crafting_chain_finder = CraftingChainFinder(
                crafting_chain_database, config=config, machine_limit=config.machine_limit, use_individual_limits=False
            )
            cost_vectors = crafting_chain_finder.get_default_cost_vectors()

            weighted_cost_vectors = [(cost_vectors[0], 1.0), (cost_vectors[1], 0.0), (cost_vectors[2], 0.0)]
            if 'crafting_chain' not in st.session_state or update:
                st.session_state['crafting_chain'] = crafting_chain_finder._optimal_crafting_chain(
                    weighted_cost_vectors=weighted_cost_vectors, use_individual_limits=False,
                    eu_per_tick_constraint=None, machine_amount_constraint=None
                )
            crafting_chain = st.session_state['crafting_chain']

        if crafting_chain is None:
            st.error('Crafting Chain could not be determined!', icon="❗")
        else:
            st.success('Successfully determined the crafting chain!', icon="✅")

        # if st.button('Display Pareto Front'):
        #     display_pareto_front(crafting_chain_finder, cost_vectors)
    else:
        crafting_chain = None

    # Crafting Chain Display
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
        unspecified_machines = set().union(*[r.valid_machines for r in crafting_chain.recipe_amounts.keys() if r.machine.unspecified])
        if len(unspecified_machines) > 0:
            st.warning(f"""The behaviours of the following machines are not specified. This probably leads to incorrect 
recipe data for these machines. Behaviours need to be implemented via the config files and the machine 
behaviour classes.\n            
{'\n'.join([f'- {m.__str__()}\n' for m in unspecified_machines])}
    """, icon="❗")

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


    # @st.fragment()
    # def recipe_configuration(crafting_chain: CraftingChain):
    #     _LOGGER.info('Displaying recipe configuration')

    #     st.markdown('## Recipe Configuration')
    #     crafting_chain_recipes = crafting_chain.recipe_list
    #     for recipe in crafting_chain_recipes:
    #         display_crafting_chain_recipe(recipe, database.machine_options_book)


    # if crafting_chain is not None:
    #     recipe_configuration(crafting_chain)
