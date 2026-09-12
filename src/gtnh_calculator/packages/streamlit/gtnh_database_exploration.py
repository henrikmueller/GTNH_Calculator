import streamlit as st
import logging
import sys
import pandas as pd
from dataclasses import dataclass


from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.streamlit.filtering import get_recipe_filters, filter_recipes
from packages.recipes_db.material import Material
from packages.recipes_db.machines import Machine
from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.database_extraction.recipe_initialization import RecipeInitializer
from packages.recipes_db.recipes import Recipe
from packages.recipes_db.voltage_tiers import VoltageTier
from packages.recipes_db.instantiated_recipes import InstantiatedRecipe
from packages.streamlit.streamlit_recipes import (
    display_crafting_chain_recipe, display_recipe_environment
)
from packages.streamlit.filtering import RecipeFilters, get_recipe_filters
from packages.streamlit.session_state import GameStateSessionState
from packages.utility.gtnh_utility import get_recipe_id_from_str

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class GTNHDatabaseExplorer:
    database: GTNHDatabase
    session_state: GameStateSessionState
    recipe_initializer: RecipeInitializer

    def apply_recipe_exploration_filters(
        self,
        recipe_filters: RecipeFilters
    ) -> tuple[list[InstantiatedRecipe], int]:
        _LOGGER.info(f'Starting applying recipe exploration filters ...')
        with st.spinner('Applying filters...', show_time=True):
            if self.session_state.recipe_filtering_state.filtered_recipe_ids:
                df_filtered = self.database.df_recipes[self.database.df_recipes['ID'].isin(
                    self.session_state.recipe_filtering_state.filtered_recipe_ids)].copy(deep=False)
            else:
                selected_machines = {
                    m for m in self.database.extracted_machines.values() 
                    if m.name in recipe_filters.selected_machine_names
                }
                selected_id = get_recipe_id_from_str(recipe_filters.selected_recipe_id)
                df_filtered = filter_recipes(
                    df_recipes=self.database.df_recipes,
                    selected_id=selected_id,
                    inputs=recipe_filters.selected_inputs,
                    outputs=recipe_filters.selected_outputs,
                    voltage_tiers={v for v in VoltageTier.voltage_tiers_int()},
                    machines=selected_machines
                )

            if df_filtered.shape[0] > 0:
                df_filtered[["SELECTED_MACHINE", "SELECTED_VOLTAGE_TIER"]] = pd.DataFrame( # type: ignore
                    df_filtered["RECIPE"]
                        .apply(self.recipe_initializer.get_default_machine_and_voltage_tier)
                        .tolist(),
                    index=df_filtered.index,
                )

        with st.spinner('Instantiating recipes...', show_time=True):
            displayed_recipes: list[InstantiatedRecipe] = []
            filtered_recipe_amount = 0
            for recipe_row in df_filtered.itertuples(index=False):
                recipe: Recipe = recipe_row.RECIPE  # type: ignore
                machine: Machine = recipe_row.SELECTED_MACHINE  # type: ignore
                voltage_tier: int = recipe_row.SELECTED_VOLTAGE_TIER  # type: ignore
                input_combinations = recipe.filtered_input_combinations(
                    pick_any=False, selected_inputs=recipe_filters.selected_inputs, any_input=True,
                    selected_instantiated_id=recipe_filters.selected_recipe_id, 
                    enabled_ids=None
                )
                if not input_combinations:
                    continue
                if filtered_recipe_amount >= recipe_filters.max_displayed_recipes:
                    filtered_recipe_amount += len(input_combinations)
                    continue  # this may break after max_displayed_recipes, as there can be multiple instances
                filtered_recipe_amount += len(input_combinations)
    
                instantiated_recipes = self.recipe_initializer.instantiate_recipe_from_raw(
                    recipe, machine, voltage_tier, pick_any=False,
                    changed_recipe_environments=self.session_state.recipe_environments_state.changed_recipe_environments
                )
                displayed_recipes += instantiated_recipes
    
            displayed_recipes = displayed_recipes[:recipe_filters.max_displayed_recipes]
            return displayed_recipes, filtered_recipe_amount

    def recipe_exploration_display(
        self,
        displayed_recipes: list[InstantiatedRecipe],
        filtered_recipe_amount: int
    ) -> None:
        st.success(f'Displaying {len(displayed_recipes)} / {filtered_recipe_amount} recipes matching the selected filters.', icon="✅")

        if len(displayed_recipes) > 0:
            for instantiated_recipe in displayed_recipes:
                with st.container(border=True):
                    a, b = st.columns(2)
                    with a:
                        display_recipe_environment(
                            instantiated_recipe, self.session_state.recipe_environments_state
                        )
                        st.button(
                            label='Select', key=f'select_{instantiated_recipe.id}', type='primary',
                            on_click=self.session_state.select_recipe, args=(instantiated_recipe,)
                        )
                    with b:
                        display_crafting_chain_recipe(instantiated_recipe)

    def recipe_exploration(
        self,
        all_materials: dict[str, Material],
    ) -> None:
        _LOGGER.info(f'Starting recipe exploration ...')
        st.markdown('## Explore Recipes:')
        recipe_filters = get_recipe_filters(
            st_key='game_state_filters', 
            used_machines=self.database.extracted_machines.values(), 
            used_materials=all_materials.values(),
            only_enabled_checkbox=False
        )
        if not self.session_state.recipe_filtering_state.has_selected_filters(recipe_filters):
            self.session_state.recipe_filtering_state.selected_filters = recipe_filters
            self.session_state.recipe_filtering_state.wipe_filtered_recipes()

        displayed_recipes, filtered_recipe_amount = self.apply_recipe_exploration_filters(
            recipe_filters=recipe_filters
        )
        self.session_state.recipe_filtering_state.filtered_recipe_ids = {r.base_id for r in displayed_recipes}
        self.session_state.recipe_filtering_state.number_of_filtered_instantiated_recipes = filtered_recipe_amount

        self.recipe_exploration_display(
            displayed_recipes=displayed_recipes,
            filtered_recipe_amount=self.session_state.recipe_filtering_state.number_of_filtered_instantiated_recipes
        )
