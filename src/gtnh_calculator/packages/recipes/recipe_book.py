from __future__ import annotations
from typing import Dict

from .recipe import Recipe
from .material import Material, MaterialList


class RecipeBook:
    recipes: Dict[int, Recipe]
    material_list: MaterialList

    def __init__(
        self,
        recipes: Dict[int, Recipe],
        material_list: MaterialList
    ):
        self.recipes = recipes
        self.material_list = material_list

    def restrict_to(self, materials: list[Material]) -> RecipeBook:
        restricted_materials_by_id = {
            id: material for id, material in self.material_list.materials_by_id.items() if material in materials
        }
        restricted_materials_by_name = {
            name: material for name, material in self.material_list.materials_by_name.items() if material in materials
        }
        restricted_material_list = MaterialList(restricted_materials_by_name, restricted_materials_by_id)
        materials_set = set(materials)
        restricted_recipes = {
            id: recipe for id, recipe in self.recipes.items()
            if set(recipe.get_inputs() + recipe.get_outputs()).issubset(materials_set)
        }
        return RecipeBook(restricted_recipes, restricted_material_list)

    def material_by_id(self, id: int) -> Material:
        return self.material_list.materials_by_id[id]

    def material_by_name(self, name: str) -> Material:
        return self.material_list.materials_by_name[name]

    def recipe_by_id(self, id: int) -> Recipe:
        return self.recipes[id]
