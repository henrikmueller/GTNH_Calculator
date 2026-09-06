import streamlit as st
from rapidfuzz import fuzz
from dataclasses import dataclass
import pandas as pd
import logging

from packages.recipes_db.material import Material
from packages.crafting_chains.crafting_chain_database import CraftingChainDatabase, filter_recipes
from packages.database_extraction.gtnh_database import GTNHDatabase
from packages.recipes_db.material import Material
from packages.recipes_db.recipes import Recipe
from packages.recipes_db.voltage_tiers import VoltageTier
from packages.recipes_db.instantiated_recipes import InstantiatedRecipe
from packages.streamlit.streamlit_functions import (
    display_crafting_chain_recipe, adapt_crafting_chain_recipe
)
from packages.streamlit.filtering import RecipeFilters, get_recipe_filters
from packages.streamlit.session_state import SessionState
from packages.utility.gtnh_utility import get_recipe_id_from_str

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class CCDBExplorer:
    session_state: SessionState

    def material_exploration(
        self,
        all_materials: dict[str, Material],
        number_of_columns: int = 3,
        max_displayed_materials: int = 100
    ) -> None:
        st.markdown('### Explore Materials:')

        search = st.text_input("Search material")
        if search:
            search_terms = search.lower().split(' ')
            matching_materials = [
                m for m in all_materials.values()
                if all(t in m.name.lower() for t in search_terms)
            ]
            matching_materials.sort(key=lambda s: fuzz.ratio(search.lower(), s.name.lower()), reverse=True)
        else:
            matching_materials = []

        cols = st.columns(number_of_columns)
        for i, material in enumerate(matching_materials[:max_displayed_materials]):
            with cols[i % number_of_columns]:
                self.material_card_crafting_chain_database(material)

        # grade = (
        #     self.crafting_chain_database.material_grading[material]
        #     if material in self.crafting_chain_database.material_grading.keys() else -1
        # )
        # if grade >= 1:
        #     current_grade_materials = {material}
        #     for g in range(grade - 1, -1, -1):
        #         st.markdown(f'**Grading Level {g}**')
        #         current_grade_recipes = [
        #             r for r in self.crafting_chain_database.instantiated_recipes.values()
        #             if self.crafting_chain_database.recipe_grading[r] == g and
        #             any(o in current_grade_materials for o in r.get_outputs())
        #         ]
        #         current_grade_materials = {
        #             m for r in current_grade_recipes for m, a in r.input_dict.items() if a < 0
        #         }
        #         st.write(current_grade_materials)

    def apply_recipe_exploration_filters(
        self,
        database: GTNHDatabase,
        crafting_chain_database: CraftingChainDatabase,
        recipe_filters: RecipeFilters
    ) -> tuple[list[InstantiatedRecipe], int]:
        with st.spinner('Applying filters...', show_time=True):
            selected_machines = {m for m in database.extracted_machines.values() if m.name in recipe_filters.selected_machine_names}
            df_recipes = crafting_chain_database.df_recipes(database)
            selected_id = get_recipe_id_from_str(recipe_filters.selected_recipe_id)
            df_filtered = filter_recipes(
                df_recipes=df_recipes,
                selected_id=selected_id,
                inputs=recipe_filters.selected_inputs,
                outputs=recipe_filters.selected_outputs,
                voltage_tiers={v for v in VoltageTier.voltage_tiers_int()},
                machines=selected_machines
            )

            displayed_recipes: list[InstantiatedRecipe] = []
            filtered_recipe_amount = 0
            for recipe_row in df_filtered.itertuples(index=False):
                recipe: Recipe = recipe_row.RECIPE  # type: ignore
                input_combinations = recipe.filtered_input_combinations(
                    pick_any=False, selected_inputs=recipe_filters.selected_inputs, any_input=True,
                    selected_instantiated_id=recipe_filters.selected_recipe_id, 
                    enabled_ids=self.session_state.enabled_recipe_ids if recipe_filters.only_enabled else None
                )
                if not input_combinations:
                    continue
                if filtered_recipe_amount >= recipe_filters.max_displayed_recipes:
                    filtered_recipe_amount += len(input_combinations)
                    continue  # this may break after max_displayed_recipes, as there can be multiple instances
                filtered_recipe_amount += len(input_combinations)
    
                instantiated_recipes = crafting_chain_database.instantiate(
                    recipe=recipe, pick_any=False,
                    input_combinations=input_combinations,
                    changed_recipe_environments=self.session_state.recipe_environments_state.changed_recipe_environments
                )
                displayed_recipes += instantiated_recipes
    
            displayed_recipes = displayed_recipes[:recipe_filters.max_displayed_recipes]
            return displayed_recipes, filtered_recipe_amount


    def recipe_exploration_display(
        self,
        database: GTNHDatabase,
        displayed_recipes: list[InstantiatedRecipe],
        filtered_recipe_amount: int
    ) -> None:
        _LOGGER.info(f'Starting recipe exploration display ...')
        st.success(f'Displaying {len(displayed_recipes)} / {filtered_recipe_amount} recipes matching the selected filters.', icon="✅")

        if len(displayed_recipes) > 0:
            for instantiated_recipe in displayed_recipes:
                with st.container(border=True):
                    a, b = st.columns(2)
                    with a:
                        adapt_crafting_chain_recipe(
                            instantiated_recipe, database.machine_options_book, 
                            self.session_state, key_suffix='ccdb'
                        )
                    with b:
                        display_crafting_chain_recipe(instantiated_recipe)


    def recipe_exploration(
        self,
        database: GTNHDatabase,
        crafting_chain_database: CraftingChainDatabase,
        all_materials: dict[str, Material],
    ) -> None:
        st.markdown('### Explore Recipes:')
        recipe_filters = get_recipe_filters(
            st_key="ccdb_rf", 
            used_machines=database.extracted_machines.values(), 
            used_materials=all_materials.values()
        )
        displayed_recipes, filtered_recipe_amount = self.apply_recipe_exploration_filters(
            database=database,
            crafting_chain_database=crafting_chain_database,
            recipe_filters=recipe_filters
        )
        self.recipe_exploration_display(
            database=database,
            displayed_recipes=displayed_recipes,
            filtered_recipe_amount=filtered_recipe_amount
        )


    def material_card_crafting_chain_database(self, material: Material):
        with st.container(border=True, width=600):
            col1, col2 = st.columns([4, 1])

            with col1:
                print(material)
                if st.button(material.name, key=f"button_{material.id}", width='stretch'):
                    if st.session_state.selected_material is None:
                        st.session_state.selected_material = material
                        st.rerun()
                st.write(f'Mod: {material.mod}')
            with col2:
                try:
                    st.image(f'db/images/{material.image_file_path}')
                except Exception as e:
                    pass
