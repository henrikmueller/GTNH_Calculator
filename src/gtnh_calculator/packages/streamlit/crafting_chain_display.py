from frozendict import frozendict
import streamlit as st
import logging
import sys
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Mapping
import plotly.graph_objects as go

from packages.configs.crafting_chain_config_db import CraftingChainConfig
from packages.crafting_chains.crafting_chain_database import CraftingChainDatabase
from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.recipes_db.instantiated_recipes import InstantiatedRecipe
from packages.streamlit.streamlit_functions import ( 
    display_crafting_chain_recipe, adapt_crafting_chain_recipe
)
from packages.streamlit.session_state import SessionState
from packages.streamlit.crafting_chain_database_exploration import CCDBExplorer
from packages.streamlit.filtering import get_recipe_filters
from packages.recipes_db.material import Material
from packages.crafting_chains.crafting_chain_problem import CostVectorType, GTNHConstraints
from packages.optimization.optimization_problem import CostVector, CostConstraint
from packages.crafting_chains.crafting_chain_optimizer import (
    CraftingChainFinder, DeterminedSolution)
from packages.crafting_chains.crafting_chain_db import CraftingChain
from packages.utility.general_utility import time_to_seconds, Timer, format_float

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)

MAX_DISPLAYED_MATERIALS = 100
NUMBER_OF_COLUMNS = 3


@dataclass(frozen=True)
class ConstraintValidity:
    message: str
    valid: bool


@dataclass(frozen=True)
class ParetoConstraints:
    solution_name: str
    cost_vector_type: CostVectorType
    cost_constraints: GTNHConstraints

    @property
    def validity(self) -> ConstraintValidity:
        if (
            CostVectorType.RECIPE_COST_VECTOR in self.cost_constraints.keys() and
            self.cost_constraints[CostVectorType.RECIPE_COST_VECTOR].lower_le(0)
        ):
            return ConstraintValidity(
                message=f"Please insert a positive lower bound for the Material Value. "
                        f"Otherwise the trivial solution is valid for the optimization.",
                valid=False
            )
        return ConstraintValidity(message="", valid=True)

        
@dataclass
class CraftingChainCalculationDisplay:
    database: GTNHDatabase
    crafting_chain_database: CraftingChainDatabase
    config: CraftingChainConfig
    all_materials: dict[str, Material]
    session_state: SessionState
    instantiated_recipes: dict[str, InstantiatedRecipe] = field(default_factory=dict)

    def display_page(self) -> None:
        self.set_material_weights()
        st.write(self.config)
        df_recipes = self.crafting_chain_database.df_recipes(self.database)

        a, b = st.columns(2, gap='small')
        with a:
            if st.button('Apply changed recipe environments', type='primary'):
                self.session_state.update_optimization = True
        with b:
            if st.button('Reset Enabled Recipes', type='primary'):
                self.session_state.reset_enabled_recipes = True
                self.session_state.update_optimization = True

        if not self.prepare_optimization(df_recipes):
            _LOGGER.error('Optimization preparation failed. Skipping crafting chain optimization.')
            return
        if not self.instantiated_recipes:
            _LOGGER.error('Recipes not instantiated. Cannot perform optimization.')
            return
        
        with st.spinner('Building optimization problems ...', show_time=True):
            crafting_chain_finder = CraftingChainFinder(
                instantiated_recipes=list(self.instantiated_recipes.values()),
                materials=list(self.all_materials.values()),
                config=self.config, 
                machine_limit=self.config.machine_limit, 
                use_individual_limits=False
            )
        self.update_default_solutions(crafting_chain_finder)
        self.display_crafting_chain_database(df_recipes)

        st.divider()
        st.markdown('## Crafting Chain Optimization')

        default_bounds = crafting_chain_finder.get_default_bounds(self.session_state.default_solutions)
        selected_pareto_constraints = self.get_pareto_constraints(
            cost_vectors=crafting_chain_finder.continuous_problem.cost_vectors,
            default_bounds=default_bounds
        )
        with st.spinner('Calculating additional solution ...', show_time=True):
            self.apply_pareto_constraints(crafting_chain_finder, selected_pareto_constraints)

        self.display_optimization_results(crafting_chain_finder)

    def set_material_weights(self) -> None:
        if 'weight_materials' not in st.session_state:
            st.session_state['weight_materials'] = [m for m, a in self.config.weights.items() if a > 0]
        st.session_state['weight_materials'].sort(key=lambda m: m.id)
        if 'ipw_materials' not in st.session_state:
            st.session_state['ipw_materials'] = [m for m, a in self.config.infinite_production_weights.items() if a > 0]
        st.session_state['ipw_materials'].sort(key=lambda m: m.id)
    
    @st.fragment()
    def display_crafting_chain_database(self, df_recipes: pd.DataFrame) -> None:
        st.divider()
        st.markdown('## Loaded Database')
        ccdb_explorer = CCDBExplorer(self.session_state)

        a, b, c, d, e = st.columns(5)
        number_of_instantiated_recipes = self.crafting_chain_database.number_of_instantiated_recipes(
            df_recipes["RECIPE"] if not df_recipes.empty else []
        )
        a.metric("Recipes", len(self.crafting_chain_database.recipe_ids), border=True)
        b.metric("Instantiated Recipes", number_of_instantiated_recipes, border=True)
        c.metric("Enabled Instantiated Recipes", len(self.session_state.enabled_recipe_ids), border=True)
        d.metric("Materials", len(self.crafting_chain_database.material_ids), border=True)
        e.metric("Machines", len(self.crafting_chain_database.machine_ids), border=True)

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
                    database=self.database,
                    crafting_chain_database=self.crafting_chain_database,
                    all_materials=self.all_materials
                )

            with tab3:
                st.markdown('### Recipe and Material Grades:')
                st.markdown('Under construction.')
                # TODO

        st.markdown('#### Changes to Recipe Environments')
        st.markdown(self.session_state.recipe_environments_state.get_change_markdown())

    def prepare_optimization(self, df_recipes: pd.DataFrame) -> bool:
        with st.spinner('Fitting recipes to machines...', show_time=True):
            self.instantiated_recipes = self.crafting_chain_database.instantiate_all(
                df_recipes,
                changed_recipe_environments=self.session_state.recipe_environments_state.changed_recipe_environments
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

    # -----------------------------------------------------------------------------------------------------------------
    # Default support and crafting chain calculation
    # -----------------------------------------------------------------------------------------------------------------

    def update_default_solutions(self, crafting_chain_finder: CraftingChainFinder) -> None:
        if not self.session_state.update_optimization:
            return

        self._update_recipe_environments()
        with st.spinner('Calculating default support ...', show_time=True):
            if self.session_state.reset_enabled_recipes:
                _LOGGER.info('Updating default enabled recipes...')
                default_enabled_recipes = self._default_enabled_recipes(crafting_chain_finder)
                self.session_state.enable(default_enabled_recipes)
                self.session_state.reset_enabled_recipes = False
        with st.spinner('Calculating default crafting chain ...', show_time=True):
            determined_solutions = self._calculate_default_solutions(crafting_chain_finder)
            if determined_solutions:
                self.session_state.add_solutions(determined_solutions)

        self.session_state.update_optimization = False

    def _update_recipe_environments(self) -> None:
        _LOGGER.info('Updating current recipe environments and wiping previous solutions...')
        self.session_state.recipe_environments_state.update_current_environments(self.instantiated_recipes)
        self.session_state.wipe_solutions()  # wipe previous solutions since environments have changed

    def _default_enabled_recipes(self, crafting_chain_finder: CraftingChainFinder) -> set[str]:
        optimization_response = crafting_chain_finder.get_linear_default_solution()
        if not optimization_response.success:
            st.error(optimization_response.response)
            return set()
        support = optimization_response.pick_solution().solution_vector.support
        recipe_ids = {crafting_chain_finder.recipes[i].id for i in support if i < crafting_chain_finder.q}
        return recipe_ids
    
    def _calculate_default_solutions(self, crafting_chain_finder: CraftingChainFinder) -> list[DeterminedSolution]:
        optimization_response = crafting_chain_finder.get_default_restricted_mixed_integer_solutions(
            self.session_state.enabled_recipe_ids
        )
        if not optimization_response.success:
            st.error(optimization_response.response, icon="❗")
            return []
        return optimization_response.determined_solutions

    # -----------------------------------------------------------------------------------------------------------------
    # Additional Pareto-optimal solutions
    # -----------------------------------------------------------------------------------------------------------------

    @st.fragment()
    def get_pareto_constraints(
        self, cost_vectors: Mapping[CostVectorType, CostVector], 
        default_bounds: Mapping[CostVectorType, float]
    ) -> ParetoConstraints:
        st.markdown('### Add solutions with constraints')
        st.markdown(f'''It is recommended to optimize for the _total material value_ while bounding _EU/t_ and _machine amount_.
        ''')
        cost_vector_type_display = {
            CostVectorType.RECIPE_COST_VECTOR: 'Total Material Value',
            CostVectorType.EU_COST_VECTOR: 'EU/t',
            CostVectorType.MACHINE_AMOUNT_COST_VECTOR: 'Machine Amount',
        }
        a, b = st.columns(2, gap="small")
        with a:
            solution_name = st.text_input(label="Solution Name", value="Additional Solution", width=500)
            selected_cost_vector_type = st.selectbox(
                'Optimize for',
                options=list(cost_vectors.keys()),
                index=0,
                format_func=lambda rct: cost_vector_type_display[rct],
                key='pareto_cost_vector',
                width=300,
            )
        with b:
            constraints: Dict[CostVectorType, CostConstraint] = {}
            for cost_vector_type, cost_vector in cost_vectors.items():
                if cost_vector_type == selected_cost_vector_type:
                    continue
                constraint_bound = st.number_input(
                    label=f'{cost_vector_type_display[cost_vector_type]} {"<=" if cost_vector.minimize else ">="}',
                    min_value=None,
                    max_value=None,
                    value=default_bounds[cost_vector_type],
                    key=f"pareto_constraint_{cost_vector_type.name}",
                    width=300,
                )
                if cost_vector.minimize:
                    constraint = CostConstraint(upper=constraint_bound)
                else:
                    constraint = CostConstraint(lower=constraint_bound)
                constraints[cost_vector_type] = constraint
        pareto_constraints = ParetoConstraints(
            solution_name=solution_name,
            cost_vector_type=selected_cost_vector_type,
            cost_constraints=frozendict(constraints)
        )
        constraint_validity = pareto_constraints.validity
        if not constraint_validity.valid:
            st.warning(constraint_validity.message)
        return pareto_constraints

    def apply_pareto_constraints(
        self, crafting_chain_finder: CraftingChainFinder, pareto_constraints: ParetoConstraints
    ) -> None:
        if st.button('Determine additional solution', type='primary'):
            optimization_response = crafting_chain_finder.get_restricted_mixed_integer_solutions(
                enabled_recipe_ids=self.session_state.enabled_recipe_ids,
                optimized_cost_vector_type=pareto_constraints.cost_vector_type,
                cost_constraints=pareto_constraints.cost_constraints,
                solution_name=self.session_state.next_solution_name(pareto_constraints.solution_name)
            )
            if not optimization_response.success:
                st.error(optimization_response.response, icon="❗")
                return

            solutions = optimization_response.determined_solutions
            self.session_state.add_solutions(solutions)
            st.success(optimization_response.response)

    @st.fragment()
    def display_optimization_results(
        self, crafting_chain_finder: CraftingChainFinder
    ) -> None:
        st.divider()
        st.markdown('## Optimization Results')

        determined_solutions = self.session_state.determined_solutions
        st.markdown(f'Stored: {len(determined_solutions)} Pareto-optimal solutions.')
        
        with st.expander('Solution Space Visualization'):
            self._plot_determined_solutions()

        selected_solution = self._select_determined_solution(determined_solutions)
        if selected_solution is None:
            st.warning('No solution selected.')
            return
        st.write(selected_solution.markdown_string)

        with Timer('display_crafting_chain', active=True):
            crafting_chain = crafting_chain_finder.create_crafting_chain(selected_solution)
            self.display_crafting_chain(crafting_chain)
            self.detailed_recipe_information(crafting_chain)

        # self.display_grading()
        # self.display_looping_materials()

    def _select_determined_solution(
        self, determined_solutions: list[DeterminedSolution]
    ) -> DeterminedSolution | None:
        if len(determined_solutions) == 0:
            return None

        width = 400
        options = {
            i: s.name for i, s in enumerate(determined_solutions)
        }
        selected_index = st.selectbox(
            'Select solution to display',
            options=options.keys(),
            key=f"display_determined_solutions",
            width=width,
            format_func=lambda index: options[index]
        )
        selected_solution = determined_solutions[selected_index]
        return selected_solution

    def _plot_determined_solutions(self) -> None:
        @dataclass(frozen=True)
        class DisplayedObjective:
            name: str
            key: str
            cost_vector: CostVector
            color: str

        st.markdown('### Visualization of Pareto-optimal Solutions')

        cost_vectors = frozendict({
            "material_weights": CostVector(np.array([1, 0, 0]), minimize=False, normalization_scalar=1.0),
            "eu_per_tick": CostVector(np.array([8, 32, 120]), minimize=True, normalization_scalar=1.0),
            "machine_amounts": CostVector(np.array([1, 1, 1]), minimize=True, normalization_scalar=1.0),
        })

        displayed_objectives = (
            DisplayedObjective(
                name="Material Weights",
                key="material_weights",
                cost_vector=cost_vectors["material_weights"],
                color="blue"
            ),
            DisplayedObjective(
                name="EU/t",
                key="eu_per_tick",
                cost_vector=cost_vectors["eu_per_tick"],
                color="red"
            ),
            DisplayedObjective(
                name="Number of machines",
                key="machine_amounts",
                cost_vector=cost_vectors["machine_amounts"],
                color="green"
            ),
        )

        objective_points = [
            frozendict({
                "material_weights": 2.5,
                "eu_per_tick": 3.0,
                "machine_amounts": 4.0,
            }),
            frozendict({
                "material_weights": 1.7,
                "eu_per_tick": 2.0,
                "machine_amounts": 2.6,
            }),
            frozendict({
                "material_weights": 1.0,
                "eu_per_tick": 1.5,
                "machine_amounts": 2.2,
            }),
        ]

        x, y, z = zip(*[
            tuple(p[key] for key in [d.key for d in displayed_objectives])
            for p in objective_points
        ])

        options = {
            i: displayed_objectives[i].name for i in range(len(displayed_objectives))
        }
        selected_objective_index = st.selectbox(
            label="Select the objective for coloring", format_func=lambda d: options[d],
            options=options.keys(),
            width=400
        )
        selected_objective = displayed_objectives[selected_objective_index]

        fig = go.Figure(
            go.Scatter3d(
                x=x,
                y=y,
                z=z,
                mode="markers",
                marker=dict(
                    size=7,
                    color=[p[selected_objective.key] for p in objective_points],
                    colorscale="RdBu_r",
                    cmin=min(p[selected_objective.key] for p in objective_points),
                    cmax=max(p[selected_objective.key] for p in objective_points),
                    colorbar=dict(
                        title=selected_objective.name
                    ),
                ),
                hovertemplate=(
                    f"{displayed_objectives[0].name}: %{{x}}<br>"
                    f"{displayed_objectives[1].name}: %{{y}}<br>"
                    f"{displayed_objectives[2].name}: %{{z}}"
                    "<extra></extra>"
                ),
            )
        )

        fig.update_layout(
            scene=dict(
                xaxis_title=displayed_objectives[0].name,
                yaxis_title=displayed_objectives[1].name,
                zaxis_title=displayed_objectives[2].name,
                aspectmode="cube",
            ),
            height=700
        )
        st.plotly_chart(fig, width='stretch')

    # -----------------------------------------------------------------------------------------------------------------
    # Crafting Chain Details
    # -----------------------------------------------------------------------------------------------------------------

    def display_crafting_chain(self, crafting_chain: CraftingChain) -> None:
        st.markdown('### Selected Crafting Chain')
        
        unspecified_machines = set(
            p.machine for p in crafting_chain.partial_recipes.values() 
            if p.machine.unspecified and p.capacity_utilization > 0
        )
        if len(unspecified_machines) > 0:
            st.warning(f"""The behaviours of the following machines are not specified. This probably leads to incorrect 
recipe data for these machines. Behaviours need to be implemented via the config files and the machine 
behaviour classes.\n            
{'\n'.join([f'- {m.__str__()}\n' for m in unspecified_machines])}
    """, icon="❗")

        time, _ = time_to_seconds(self.config.time)
        display_interval, display_interval_unit = time_to_seconds(self.config.display_interval)
        if display_interval != 1:
            display_interval_unit = display_interval_unit + 's'
        display_interval_string = f'{display_interval} {display_interval_unit}'

        # TODO: Improve input/output display formatting. Include gradings
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(crafting_chain.markdown_inputs(display_interval_string))
        with col2:
            st.markdown(crafting_chain.markdown_outputs(display_interval_string))
        st.markdown(crafting_chain.markdown_eu())
        st.write(f'Number of machines: {crafting_chain.number_of_machines}')
        st.write(f'Number of distinct recipes: {crafting_chain.number_of_distinct_machines}')
        st.markdown('---')

        df = crafting_chain.to_dataframe(
            time_factor=display_interval / time,
            display_interval_string=display_interval_string
        )
        with st.expander('Tabular Overview'):
            st.dataframe(df, hide_index=True)

    @st.fragment()
    def detailed_recipe_information(self, crafting_chain: CraftingChain) -> None:
        st.markdown('### Detailed Recipe Information')
        partial_recipes = [(p, crafting_chain.get_machine_amount(id)) for id, p in crafting_chain.partial_recipes.items()]
        recipe_filters = get_recipe_filters(
            st_key="cc_rf", 
            used_machines=crafting_chain.used_machines, 
            used_materials=crafting_chain.used_materials,
            default_max_displayed_recipes=100,
            only_enabled_checkbox=False
        )
        partial_recipes = [
            (p, machine_amount) for p, machine_amount in partial_recipes
            if (recipe_filters.selected_recipe_id == '' or p.id == recipe_filters.selected_recipe_id)
            and (not recipe_filters.selected_machine_names or p.machine.name in recipe_filters.selected_machine_names)
            and (not recipe_filters.selected_inputs or any(m in p.input_dict.keys() for m in recipe_filters.selected_inputs))
            and (not recipe_filters.selected_outputs or any(m in p.output_dict.keys() for m in recipe_filters.selected_outputs))
            and (not recipe_filters.selected_voltage_tiers or p.voltage_tier in recipe_filters.selected_voltage_tiers)
            and (not recipe_filters.only_enabled or self.session_state.is_enabled(p.id))
        ]
        partial_recipes.sort(key=lambda p: -p[1])
        partial_recipes = partial_recipes[:recipe_filters.max_displayed_recipes]

        # TODO: Sorting strategies: By eu/t, by total eu, by machine name, by grading
        if len(partial_recipes) <= 0:
            _LOGGER.warning('No recipes in crafting chain. Skipping detailed recipe information.')
            return
        
        for partial_recipe, machine_amount in partial_recipes:
            amount = partial_recipe.capacity_utilization

            if self.session_state.recipe_environments_state.has_recipe_environment(partial_recipe.id):
                new_recipe_environment = self.session_state.recipe_environments_state.changed_recipe_environments[partial_recipe.id][1].to_environment()
                changed_instantiated_recipe = partial_recipe.instantiated_recipe.copy(new_recipe_environment)
                processing_time_ratio = changed_instantiated_recipe.processing_time / partial_recipe.processing_time
                new_amount = amount * partial_recipe.instantiated_recipe.get_throughput_ratio(changed_instantiated_recipe) * processing_time_ratio
                self.session_state.crafting_chain_display_state.changed_recipes[partial_recipe.id] = (changed_instantiated_recipe, new_amount)

            with st.container(border=True):
                a, b = st.columns(2)
                with a:
                    adapt_crafting_chain_recipe(
                        partial_recipe.instantiated_recipe, self.database.machine_options_book, 
                        self.session_state, amount=machine_amount, key_suffix='opt'
                    )
                with b:
                    if self.session_state.crafting_chain_display_state.has_recipe(partial_recipe.id):
                        changed_instantiated_recipe, new_amount = self.session_state.crafting_chain_display_state.get_recipe(partial_recipe.id)
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
            
    # def display_grading(self) -> None:
    #     """
    #     Display the grading of materials in the crafting chain.
    #     """
    #     if self.crafting_chain is None:
    #         return
    #     with st.expander('Material Grading'):
    #         grading = [(m, g) for m, g in self.crafting_chain.material_grading.items()]
    #         grading_level = defaultdict(list)
    #         for material, g in grading:
    #             grading_level[g].append(material)
    #         grading_levels = list(set(grading_level.keys()))
    #         grading_levels.sort()
    #         for g in grading_levels:
    #             if g < 0:
    #                 continue
    #             st.markdown(f'#### Grading Level {g}')
    #             st.write(grading_level[g])

    # def display_looping_materials(self) -> None:
    #     """
    #     Display the materials that are both produced and consumed in the crafting chain, indicating potential loops.
    #     """
    #     if self.crafting_chain is None:
    #         return
    #     looping_materials = (
    #         set(m for m, a in self.crafting_chain.total_material_needs.items() if a == 0) &
    #         set().union(*[set(p.positive_outputs) for p in self.crafting_chain.partial_recipes.values() if p.capacity_utilization > 0])
    #     )
    #     with st.expander('Looping Materials'):
    #         st.markdown(f'#### Reachable')
    #         st.write(looping_materials & set(m for m, g in self.crafting_chain.material_grading.items() if g >= 0))
    #         st.markdown(f'#### Unreachable')
    #         st.write(looping_materials & set(m for m, g in self.crafting_chain.material_grading.items() if g < 0))