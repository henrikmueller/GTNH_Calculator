import logging
from collections import defaultdict
from typing import Dict
from collections import deque

from ..recipes_db.material import Material
from ..recipes_db.recipes import Recipe

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


def calculate_gradings(
    recipes: list[Recipe], materials: list[Material], starting_materials: set[Material]
) -> tuple[Dict[Recipe, int], Dict[Material, int]]:
    node_to_edges = defaultdict(list)
    remaining = []
    for recipe_id, recipe in enumerate(recipes):
        inputs = [m for m, a in recipe.input_dict.items() if a != 0]
        for material in inputs:
            node_to_edges[material].append(recipe_id)
        remaining.append(len(inputs))

    material_grading = {m: -1 for m in materials}  # positive values = visited
    recipe_grading = [-1] * len(recipes)  # positive values = visited
    double_ended_queue = deque(starting_materials)
    for m in double_ended_queue:
        material_grading[m] = 0

    while double_ended_queue:
        material = double_ended_queue.popleft()
        if material_grading[material] < 0:  # TODO: Remove later
            raise AssertionError(f'Negative grading for material in queue: {material} | {double_ended_queue}')
        for recipe_id in node_to_edges[material]:
            remaining[recipe_id] -= 1

            if remaining[recipe_id] == 0 and recipe_grading[recipe_id] < 0:
                recipe_grading[recipe_id] = material_grading[material]
                for output in recipes[recipe_id].get_outputs():
                    if material_grading[output] < 0:
                        material_grading[output] = material_grading[material] + 1
                        double_ended_queue.append(output)

    recipe_grading = {r: g for r, g in zip(recipes, recipe_grading)}
    return recipe_grading, material_grading
