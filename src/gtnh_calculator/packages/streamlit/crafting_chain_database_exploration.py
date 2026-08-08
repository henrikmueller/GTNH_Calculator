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
from packages.recipes_db.instantiated_recipes import RecipeUpdateResult, InstantiatedRecipe
from packages.streamlit.streamlit_functions import (
    display_crafting_chain_recipe, adapt_crafting_chain_recipe
)
from packages.streamlit.session_state import SessionState

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class RecipeExplorationFilters:
    selected_recipe_id: str
    selected_machine_names: set[str]
    selected_inputs: set[Material]
    selected_outputs: set[Material]
    selected_voltage_tiers: set[int]


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


    def get_recipe_exploration_filters(
        self,
        database: GTNHDatabase,
        all_materials: dict[str, Material]
    ) -> RecipeExplorationFilters:
        a, b, c = st.columns(3)
        with a:
            selected_recipe_id = st.text_input("Filter by Recipe ID")
            selected_recipe_id = selected_recipe_id.split("==")[0]  # strip instance number of instantiated recipe
            selected_machine_names = set(st.multiselect(
                "Filter recipes by machines",
                options=[m.name for m in database.extracted_machines.values()],
                default=None,
            ))
        with b:
            options = {
                id: m.name for id, m in all_materials.items()
            }
            selected_input_ids = st.multiselect(
                'Filter by Input Materials',
                options=options.keys(),
                key=f"input_select",
                format_func=lambda index: options[index]
            )
            selected_inputs = {
                all_materials[id] for id in selected_input_ids
            }

            options = {
                id: m.name for id, m in all_materials.items()
            }
            selected_output_ids = st.multiselect(
                'Filter by Output Materials',
                options=options.keys(),
                key=f"output_select",
                format_func=lambda index: options[index]
            )
            selected_outputs = {
                all_materials[id] for id in selected_output_ids
            }
        with c:
            selected_voltage_tiers = set(VoltageTier.to_voltage_tier(v) for v in st.multiselect(
                "Filter recipes by voltage tiers",
                options=[VoltageTier.voltage_tier_name(v) for v in VoltageTier.valid_voltage_tiers()],
                default=[VoltageTier.voltage_tier_name(v) for v in VoltageTier.valid_voltage_tiers()],
            ))
        return RecipeExplorationFilters(
            selected_recipe_id=selected_recipe_id,
            selected_machine_names=selected_machine_names,
            selected_inputs=selected_inputs,
            selected_outputs=selected_outputs,
            selected_voltage_tiers=selected_voltage_tiers
        )


    def apply_recipe_exploration_filters(
        self,
        database: GTNHDatabase,
        crafting_chain_database: CraftingChainDatabase,
        recipe_exploration_filters: RecipeExplorationFilters
    ) -> pd.DataFrame:
        with st.spinner('Applying filters...', show_time=True):
            selected_machines = {m for m in database.extracted_machines.values() if m.name in recipe_exploration_filters.selected_machine_names}
            df_recipes = crafting_chain_database.df_recipes(database)
            df_filtered = filter_recipes(
                df_recipes=df_recipes,
                selected_id=recipe_exploration_filters.selected_recipe_id,
                inputs=recipe_exploration_filters.selected_inputs,
                outputs=recipe_exploration_filters.selected_outputs,
                voltage_tiers={v for v in VoltageTier.voltage_tiers_int()},
                machines=selected_machines
            )
        return df_filtered


    def recipe_exploration_display(
        self,
        database: GTNHDatabase,
        crafting_chain_database: CraftingChainDatabase,
        df_filtered: pd.DataFrame,
        max_displayed_recipes: int = 30
    ) -> None:
        _LOGGER.info(f'Starting recipe exploration display ...')
        # st.write(self.session_state.recipe_environments_state.changed_recipe_environments)

        total_recipe_count = crafting_chain_database.number_of_instantiated_recipes(df_filtered)
        show_all = st.toggle(f'Show all filtered recipes (Max {max_displayed_recipes})', value=False)
        display_amount = max_displayed_recipes if show_all else 10
        displayed_recipes: list[InstantiatedRecipe] = []
        for recipe_row in df_filtered.itertuples(index=False):
            recipe: Recipe = recipe_row.RECIPE  # type: ignore
            displayed_recipes += crafting_chain_database.instantiate(
                recipe=recipe, 
                changed_recipe_environments=self.session_state.recipe_environments_state.changed_recipe_environments
            )
            if len(displayed_recipes) >= display_amount:
                break

        displayed_recipes = displayed_recipes[:display_amount]

        st.success(f'Displaying {len(displayed_recipes)} / {total_recipe_count} recipes matching the selected filters.', icon="✅")

        if len(displayed_recipes) > 0:
            for instantiated_recipe in displayed_recipes:
                with st.container(border=True):
                    a, b = st.columns(2)
                    with a:
                        adapt_crafting_chain_recipe(
                            instantiated_recipe, database.machine_options_book, 
                            self.session_state.recipe_environments_state, key_suffix='ccdb'
                        )
                    with b:
                        display_crafting_chain_recipe(instantiated_recipe)


    def recipe_exploration(
        self,
        database: GTNHDatabase,
        crafting_chain_database: CraftingChainDatabase,
        all_materials: dict[str, Material],
        max_displayed_recipes: int = 30
    ) -> None:
        st.markdown('### Explore Recipes:')
        recipe_exploration_filters = self.get_recipe_exploration_filters(database, all_materials)
        df_filtered = self.apply_recipe_exploration_filters(
            database=database,
            crafting_chain_database=crafting_chain_database,
            recipe_exploration_filters=recipe_exploration_filters
        )
        self.recipe_exploration_display(
            database=database,
            crafting_chain_database=crafting_chain_database,
            df_filtered=df_filtered,
            max_displayed_recipes=max_displayed_recipes
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
