from __future__ import annotations
import streamlit as st
from dataclasses import dataclass
from typing import Dict
import logging

from packages.recipes_db.recipe_environments import RecipeEnvironment
from packages.recipes_db.machines import Machine
from packages.recipes_db.machine_options.machine_options import MachineOptions
from packages.crafting_chains.crafting_chain_db import CraftingChain
from packages.recipes_db.instantiated_recipes import InstantiatedRecipe

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class StoredRecipeEnvironment:
    """
    Mutable version of RecipeEnvironment.
    """
    machine: Machine
    voltage_tier: int
    machine_options: MachineOptions

    @classmethod
    def from_environment(cls, recipe_environment: RecipeEnvironment) -> StoredRecipeEnvironment:
        return StoredRecipeEnvironment(
            machine=recipe_environment.machine,
            voltage_tier=recipe_environment.voltage_tier,
            machine_options=recipe_environment.machine_options.copy(),
        )

    def set_machine(self, machine: Machine) -> None:
        self.machine = machine
        if self.voltage_tier not in machine.voltage_tiers:
            self.voltage_tier = max(machine.voltage_tiers, key=lambda vt: abs(vt - self.voltage_tier))

    def to_environment(self) -> RecipeEnvironment:
        return RecipeEnvironment(
            machine=self.machine,
            voltage_tier=self.voltage_tier,
            machine_options=self.machine_options
        )

    def get_change_markdown(self, current_recipe_environment: RecipeEnvironment) -> str:
        changes = []
        if self.machine != current_recipe_environment.machine:
            changes.append(f"Machine: {current_recipe_environment.machine} -> {self.machine}")
        if self.voltage_tier != current_recipe_environment.voltage_tier:
            changes.append(f"Voltage tier: {current_recipe_environment.voltage_tier} -> {self.voltage_tier}")
        if self.machine_options != current_recipe_environment.machine_options:
            changes.append(f"Machine options: {current_recipe_environment.machine_options} -> {self.machine_options}")
        return "\n".join(f"- {change}" for change in changes) if changes else "No changes"


@dataclass
class RecipeEnvironmentsState:
    changed_recipe_environments: Dict[str, tuple[RecipeEnvironment, StoredRecipeEnvironment]]  # (current, new)

    def get_recipe_environment(self, instantiated_recipe_id: str, current_recipe_environment: RecipeEnvironment) -> StoredRecipeEnvironment:
        if instantiated_recipe_id in self.changed_recipe_environments.keys():
            return self.changed_recipe_environments[instantiated_recipe_id][1]
        return StoredRecipeEnvironment.from_environment(current_recipe_environment)

    def has_recipe_environment(self, instantiated_recipe_id: str) -> bool:
        return instantiated_recipe_id in self.changed_recipe_environments.keys()

    def clear_recipe_environment(self, instantiated_recipe_id: str) -> None:
        if instantiated_recipe_id in self.changed_recipe_environments.keys():
            self.changed_recipe_environments.pop(instantiated_recipe_id)
            _LOGGER.info(f'Cleared stored recipe environment for recipe {instantiated_recipe_id}')

    def set_recipe_environment(self, 
        instantiated_recipe_id: str, 
        new_recipe_environment: StoredRecipeEnvironment,
        current_recipe_environment: RecipeEnvironment
    ) -> None:
        if instantiated_recipe_id in self.changed_recipe_environments.keys():
            self.changed_recipe_environments[instantiated_recipe_id] = (
                self.changed_recipe_environments[instantiated_recipe_id][0],
                new_recipe_environment
            )
        else:
            self.changed_recipe_environments[instantiated_recipe_id] = (current_recipe_environment, new_recipe_environment)

    def update_current_environments(self, instantiated_recipes: Dict[str, InstantiatedRecipe]) -> None:
        for id, (_, new) in self.changed_recipe_environments.items():
            if id in instantiated_recipes.keys():
                self.changed_recipe_environments[id] = (new.to_environment(), new)
            else:
                _LOGGER.warning(f"Instantiated recipe with id {id} not found in provided instantiated_recipes. Skipping update for this recipe.")

    def get_change_markdown(self) -> str:
        markdown_string = ''
        for id, (current, new) in self.changed_recipe_environments.items():
            changes = new.get_change_markdown(current)
            if changes:
                markdown_string += f"Recipe {id}:\n{changes}\n\n"
        if markdown_string == '':
            return 'No changes to recipe environments.'
        markdown_string += "Update Optimization to apply changes to the crafting chain."
        return markdown_string
    
    @classmethod
    def initialize_empty_recipe_environments_state(cls) -> RecipeEnvironmentsState:
        return cls(changed_recipe_environments={})


@dataclass
class CraftingChainDisplayState:
    changed_recipes: Dict[str, tuple[InstantiatedRecipe, float]]  # recipe and amount

    def has_recipe(self, instantiated_recipe_id: str) -> bool:
        return instantiated_recipe_id in self.changed_recipes.keys()

    def get_recipe(self, instantiated_recipe_id: str) -> tuple[InstantiatedRecipe, float]:
        return self.changed_recipes[instantiated_recipe_id]
    
    @classmethod
    def initialize_empty_crafting_chain_display_state(cls) -> CraftingChainDisplayState:
        return cls(changed_recipes={})


@dataclass
class SessionState:
    key: str
    recipe_environments_state: RecipeEnvironmentsState
    crafting_chain_display_state: CraftingChainDisplayState
    file_hash: str | None = None
    example_file_key: str | None = None
    update_optimization: bool = True
    crafting_chain: CraftingChain | None = None

    def has_active_file(self) -> bool:
        return self.file_hash is not None or self.example_file_key is not None

    def wipe(self) -> None:
        self.recipe_environments_state = RecipeEnvironmentsState.initialize_empty_recipe_environments_state()
        self.crafting_chain_display_state = CraftingChainDisplayState.initialize_empty_crafting_chain_display_state()
        self.file_hash = None
        self.update_optimization = True
        self.crafting_chain = None
        _LOGGER.info(f'Wiped session state with key "{self.key}"')

    @classmethod
    def get(cls, key: str) -> SessionState:
        if key not in st.session_state:
            st.session_state[key] = SessionState(
                key=key,
                recipe_environments_state=RecipeEnvironmentsState.initialize_empty_recipe_environments_state(),
                crafting_chain_display_state=CraftingChainDisplayState.initialize_empty_crafting_chain_display_state()
            )
        return st.session_state[key]
    