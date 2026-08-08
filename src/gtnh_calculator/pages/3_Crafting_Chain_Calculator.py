import streamlit as st
import logging
import sys
import numpy as np
from collections import defaultdict
from streamlit_searchbox import st_searchbox
import plotly.express as px
from dataclasses import dataclass

from packages.configs.crafting_chain_config_db import CraftingChainConfig
from packages.crafting_chains.crafting_chain_database import CraftingChainDatabase
from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.recipes_db.instantiated_recipes import InstantiatedRecipe
from packages.streamlit.streamlit_functions import (
    load_database, load_crafting_chain_database, display_pareto_front, show_memory_usage, 
    display_crafting_chain_recipe, adapt_crafting_chain_recipe
)
from packages.streamlit.streamlit_logic import (
    display_example_files, file_selection, ConfigFile
)
from packages.streamlit.session_state import SessionState, CraftingChainDisplayState
from packages.streamlit.crafting_chain_database_exploration import CCDBExplorer
from packages.recipes_db.material import Material
from packages.crafting_chains.crafting_chain_finder_highs import (
    CraftingChainFinder, OptimalSolution, CostConstraints, CostVectorCollection)
from packages.crafting_chains.crafting_chain_db import CraftingChain
from packages.utility.general_utility import time_to_seconds, is_contained_in, Timer, format_float
from packages.utility.constants import EXAMPLE_FILES

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


SESSION_STATE_KEY = 'crafting_chain_calculator'
WEIGHT_EXP_MIN = -5.0
WEIGHT_EXP_MAX = 10.0
MAX_DISPLAYED_MATERIALS = 100
NUMBER_OF_COLUMNS = 3
MAX_DISPLAYED_RECIPES = 30

_LOGGER.warning('\n\nSTARTING NEW PAGE')

st.set_page_config(
    page_title="GTNH: Crafting Chain Calculator",
    page_icon="🏭",
    layout="wide"
)
st.markdown('# GTNH Calculator')
st.markdown('## CraftingChainConfig File')

database: GTNHDatabase = load_database()
session_state = SessionState.get(SESSION_STATE_KEY)
show_memory_usage(database)

display_example_files(EXAMPLE_FILES, session_state)
uploaded_file: ConfigFile | None = file_selection(EXAMPLE_FILES, session_state)

if uploaded_file is not None:
    with st.spinner('Reducing database...', show_time=True):
        _LOGGER.info(f'Uploaded file hash: {uploaded_file.file_hash()}')
        _LOGGER.info(f'Stored file hash: {session_state.file_hash}')

        if not session_state.has_active_file() or session_state.file_hash != uploaded_file.file_hash():
            session_state.wipe()
        session_state.file_hash = uploaded_file.file_hash()
        crafting_chain_database = load_crafting_chain_database(uploaded_file, database, session_state)
else:
    crafting_chain_database = None

        
@dataclass
class CraftingChainCalculationDisplay:
    crafting_chain_database: CraftingChainDatabase
    config: CraftingChainConfig
    all_materials: dict[str, Material]
    instantiated_recipes: dict[str, InstantiatedRecipe] | None = None
    crafting_chain: CraftingChain | None = None

    def display_page(self) -> None:
        self.set_material_weights()
        st.write(self.config)
        with Timer('display_crafting_chain_database', active=True):
            self.display_crafting_chain_database()

        if st.button('Update Optimization', type='primary'):
            session_state.update_optimization = True

        if not self.prepare_optimization():
            _LOGGER.error('Optimization preparation failed. Skipping crafting chain optimization.')
            return
        
        with Timer('calculate_crafting_chain', active=True):
            self.calculate_crafting_chain()

        with Timer('display_optimization_results', active=True):
            self.display_optimization_results()

        self.detailed_recipe_information()

        self.display_grading()
        self.display_looping_materials()

    def set_material_weights(self) -> None:
        if 'weight_materials' not in st.session_state:
            st.session_state['weight_materials'] = [m for m, a in self.config.weights.items() if a > 0]
        st.session_state['weight_materials'].sort(key=lambda m: m.id)
        if 'ipw_materials' not in st.session_state:
            st.session_state['ipw_materials'] = [m for m, a in self.config.infinite_production_weights.items() if a > 0]
        st.session_state['ipw_materials'].sort(key=lambda m: m.id)
    
    @st.fragment()
    def display_crafting_chain_database(self) -> None:
        ccdb_explorer = CCDBExplorer(session_state)

        a, b = st.columns(2)
        a.metric("Recipes", len(self.crafting_chain_database.recipe_ids), border=True)
        b.metric("Materials", len(self.crafting_chain_database.material_ids), border=True)

        with st.expander('Explore Crafting Chain Database'):
            tab1, tab2, tab3 = st.tabs(["Search Materials", "Search Recipes", "Explore Grading"], default="Search Recipes")

            with tab1:
                ccdb_explorer.material_exploration(
                    self.all_materials, 
                    number_of_columns=NUMBER_OF_COLUMNS, 
                    max_displayed_materials=MAX_DISPLAYED_MATERIALS
                )
                st.markdown('Under construction.')

            with tab2:
                ccdb_explorer.recipe_exploration(
                    database=database,
                    crafting_chain_database=self.crafting_chain_database,
                    all_materials=self.all_materials,
                    max_displayed_recipes=MAX_DISPLAYED_RECIPES
                )

            with tab3:
                st.markdown('### Recipe and Material Grades:')
                st.markdown('Under construction.')
                # TODO

        st.markdown('#### Changes to Recipe Environments')
        st.markdown(session_state.recipe_environments_state.get_change_markdown())

    def prepare_optimization(self) -> bool:
        with st.spinner('Fitting recipes to machines...', show_time=True):
            df_recipes = self.crafting_chain_database.df_recipes(database)
            st.write(session_state.recipe_environments_state.changed_recipe_environments)
            self.instantiated_recipes = self.crafting_chain_database.instantiate_all(
                df_recipes,
                changed_recipe_environments=session_state.recipe_environments_state.changed_recipe_environments
            )
        
        # Check if all outputs can still be produced by at least one recipe
        outputs_missing = False
        for output in self.config.outputs:
            if not any(output in recipe.get_outputs() for recipe in self.instantiated_recipes.values()):
                outputs_missing = True
                st.error(f'''Output {output} cannot be produced by any recipe with the given config.
                Please check if the config is too restrictive (e.g. because of unlocked_voltage_tier).''', icon="❗")

        invalid_recipes = [r for r in self.instantiated_recipes.values() if not r.is_valid]
        has_invalid_recipes = False
        if len(invalid_recipes) > 0:
            st.error('Some recipes are invalid.', icon="❗")
            for instantiated_recipe in invalid_recipes:
                st.write(f'Invalid recipe: {instantiated_recipe.base_recipe.raw_recipe} with environment {instantiated_recipe.recipe_environment}.')
            has_invalid_recipes = True
        
        successful_preparation = not outputs_missing and not has_invalid_recipes
        return successful_preparation
    
    def calculate_crafting_chain(self) -> None:
        if self.instantiated_recipes is None:
            _LOGGER.error('Recipes not instantiated. Cannot perform optimization.')
            return
        
        st.markdown('## Crafting Chain Optimization')
        with st.spinner('Calculating optimal crafting chain...', show_time=True):
            crafting_chain_finder = CraftingChainFinder(
                instantiated_recipes=list(self.instantiated_recipes.values()),
                materials=list(self.all_materials.values()),
                config=self.config, 
                machine_limit=self.config.machine_limit, 
                use_individual_limits=False
            )
            cost_vectors = crafting_chain_finder.get_default_cost_vectors()

            weighted_cost_vectors = [(cost_vectors[0], 1.0), (cost_vectors[1], 0.0), (cost_vectors[2], 0.0)]
            if session_state.crafting_chain is None or session_state.update_optimization:
                session_state.recipe_environments_state.update_current_environments(self.instantiated_recipes)
                _LOGGER.info('Calculating optimal crafting chain ...')
                session_state.crafting_chain = crafting_chain_finder._optimal_crafting_chain(
                    weighted_cost_vectors=weighted_cost_vectors, use_individual_limits=False,
                    eu_per_tick_constraint=None, machine_amount_constraint=None
                )
                session_state.update_optimization = False
            self.crafting_chain = session_state.crafting_chain

        if self.crafting_chain is None:
            st.error('Crafting Chain could not be determined!', icon="❗")
        else:
            st.success('Successfully determined the crafting chain!', icon="✅")

        # if st.button('Display Pareto Front'):
        #     display_pareto_front(crafting_chain_finder, cost_vectors)

    def display_optimization_results(self) -> None:
        if self.crafting_chain is None:
            return
        
        time, _ = time_to_seconds(self.config.time)
        display_interval, display_interval_unit = time_to_seconds(self.config.display_interval)
        if display_interval != 1:
            display_interval_unit = display_interval_unit + 's'
        display_interval_string = f'{display_interval} {display_interval_unit}'

        st.markdown('### Crafting Chain Statistics')
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(self.crafting_chain.markdown_inputs(display_interval_string))
        with col2:
            st.markdown(self.crafting_chain.markdown_outputs(display_interval_string))
        st.markdown(self.crafting_chain.markdown_eu())
        st.write(f'Total number of machines: {self.crafting_chain.number_of_machines}')
        st.markdown('---')

        df = self.crafting_chain.to_dataframe(
            time_factor=display_interval / time,
            display_interval_string=display_interval_string
        )
        st.dataframe(df, hide_index=True)
        unspecified_machines = set(
            p.machine for p in self.crafting_chain.partial_recipes.values() 
            if p.machine.unspecified and p.capacity_utilization > 0
        )
        if len(unspecified_machines) > 0:
            st.warning(f"""The behaviours of the following machines are not specified. This probably leads to incorrect 
recipe data for these machines. Behaviours need to be implemented via the config files and the machine 
behaviour classes.\n            
{'\n'.join([f'- {m.__str__()}\n' for m in unspecified_machines])}
    """, icon="❗")

    @st.fragment()
    def detailed_recipe_information(self) -> None:
        if self.crafting_chain is None:
            return
        
        st.markdown('### Detailed Recipe Information')
        partial_recipes = [(p, self.crafting_chain.get_machine_amount(id)) for id, p in self.crafting_chain.partial_recipes.items()]
        partial_recipes.sort(key=lambda p: -p[1])
        # TODO: Sorting strategies: By eu/t, by total eu, by machine name, by grading
        if len(partial_recipes) <= 0:
            _LOGGER.warning('No recipes in crafting chain. Skipping detailed recipe information.')
            return
        
        for partial_recipe, machine_amount in partial_recipes:
            amount = partial_recipe.capacity_utilization

            if session_state.recipe_environments_state.has_recipe_environment(partial_recipe.id):
                new_recipe_environment = session_state.recipe_environments_state.changed_recipe_environments[partial_recipe.id][1].to_environment()
                changed_instantiated_recipe = partial_recipe.instantiated_recipe.copy(new_recipe_environment)
                processing_time_ratio = changed_instantiated_recipe.processing_time / partial_recipe.processing_time
                new_amount = amount * partial_recipe.instantiated_recipe.get_throughput_ratio(changed_instantiated_recipe) * processing_time_ratio
                session_state.crafting_chain_display_state.changed_recipes[partial_recipe.id] = (changed_instantiated_recipe, new_amount)

            with st.container(border=True):
                a, b = st.columns(2)
                with a:
                    adapt_crafting_chain_recipe(
                        partial_recipe.instantiated_recipe, database.machine_options_book, 
                        session_state.recipe_environments_state, amount=machine_amount, key_suffix='opt'
                    )
                with b:
                    if session_state.crafting_chain_display_state.has_recipe(partial_recipe.id):
                        changed_instantiated_recipe, new_amount = session_state.crafting_chain_display_state.get_recipe(partial_recipe.id)
                    else:
                        changed_instantiated_recipe, new_amount = None, amount
                    new_machine_amount = machine_amount * (new_amount / amount)

                    if changed_instantiated_recipe is not None and changed_instantiated_recipe != partial_recipe.instantiated_recipe:
                        old_headline = (
                            f'Before: {format_float(machine_amount, decimal_places=3, separate_thousands=True)} '
                            f'{partial_recipe.machine.machine_name_specified}'
                        )
                        partial_changed_recipe = changed_instantiated_recipe.fit_to_capacity_utilization(amount)
                        new_headline = (
                            f'After: {format_float(new_machine_amount, decimal_places=3, separate_thousands=True)} '
                            f'{partial_changed_recipe.machine.machine_name_specified}  '
                            f'(Update Optimization to apply changes)'
                        )
                        display_crafting_chain_recipe(
                            partial_recipe, factor=machine_amount / amount,
                            recipe_headline=old_headline
                        )
                        display_crafting_chain_recipe(
                            partial_changed_recipe, factor=new_machine_amount / new_amount,
                            recipe_headline=new_headline
                        )
                    else:
                        headline = (
                            f'{format_float(machine_amount, decimal_places=3, separate_thousands=True)} '
                            f'{partial_recipe.machine.machine_name_specified}'
                        )
                        display_crafting_chain_recipe(
                            partial_recipe, factor=machine_amount / amount,
                            recipe_headline=headline
                        )
            
    def display_grading(self) -> None:
        """
        Display the grading of materials in the crafting chain.
        """
        if self.crafting_chain is None:
            return
        with st.expander('Material Grading'):
            grading = [(m, g) for m, g in self.crafting_chain.material_grading.items()]
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

    def display_looping_materials(self) -> None:
        """
        Display the materials that are both produced and consumed in the crafting chain, indicating potential loops.
        """
        if self.crafting_chain is None:
            return
        looping_materials = (
            set(m for m, a in self.crafting_chain.total_material_needs.items() if a == 0) &
            set().union(*[set(p.positive_outputs) for p in self.crafting_chain.partial_recipes.values() if p.capacity_utilization > 0])
        )
        with st.expander('Looping Materials'):
            st.markdown(f'#### Reachable')
            st.write(looping_materials & set(m for m, g in self.crafting_chain.material_grading.items() if g >= 0))
            st.markdown(f'#### Unreachable')
            st.write(looping_materials & set(m for m, g in self.crafting_chain.material_grading.items() if g < 0))


config = crafting_chain_database.config if crafting_chain_database is not None else None
if crafting_chain_database is not None and config is not None:
    all_materials = crafting_chain_database.materials(database)
    crafting_chain_calculation_display = CraftingChainCalculationDisplay(
        crafting_chain_database=crafting_chain_database,
        config=config,
        all_materials=all_materials
    )
    crafting_chain_calculation_display.display_page()
