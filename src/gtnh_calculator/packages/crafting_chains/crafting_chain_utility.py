import logging
from collections import defaultdict
from typing import Dict
from collections import deque

from ..recipes_db.material import Material
from ..recipes_db.instantiated_recipes import InstantiatedRecipe

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


def calculate_gradings(
    instantiated_recipe_list: list[InstantiatedRecipe], materials: Dict[str, Material], starting_materials: set[Material],
    ignore_unreachable: bool = False
) -> tuple[Dict[str, int], Dict[Material, int]]:
    _LOGGER.info("Starting calculation of gradings...")
    node_to_edges: Dict[Material, list[int]] = defaultdict(list)
    remaining = []
    for recipe_id, recipe in enumerate(instantiated_recipe_list):
        inputs = [m for m, a in recipe.input_dict.items() if a != 0]
        for material in inputs:
            node_to_edges[material].append(recipe_id)
        remaining.append(len(inputs))

    unreachable = set()
    material_grading: Dict[Material, int] = {m: -1 for m in materials.values()}  # positive values = visited
    recipe_grading: list[int] = [-1] * len(instantiated_recipe_list)  # positive values = visited
    double_ended_queue = deque(starting_materials)
    for m in double_ended_queue:
        material_grading[m] = 0

    def fill_gradings():
        frozen_unreachable = set()
        max_iterations = 50
        iterations = 0
        while double_ended_queue and iterations < max_iterations:
            iterations += 1
            material = double_ended_queue.popleft()
            for recipe_id in node_to_edges[material]:
                if material not in unreachable:
                    remaining[recipe_id] -= 1

                recipe_inputs = [m for m, a in instantiated_recipe_list[recipe_id].input_dict.items() if a != 0]
                rank = max(material_grading[m] for m in recipe_inputs) + 1
                updatable_outputs = [output for output in instantiated_recipe_list[recipe_id].get_outputs() if material_grading[output] < rank and output not in frozen_unreachable]
                if not updatable_outputs:
                    continue

                if remaining[recipe_id] == 0 and recipe_grading[recipe_id] < rank:
                    for input_material in recipe_inputs:
                        if input_material in unreachable:
                            _LOGGER.info(f"Freezing material {input_material} as unreachable.")
                            frozen_unreachable.add(input_material)
                    input_info = {m: material_grading[m] for m in recipe_inputs}
                    recipe_grading[recipe_id] = rank
                    for output in updatable_outputs:
                        material_grading[output] = rank
                        double_ended_queue.append(output)
                    _LOGGER.info(
                        f"Recipe {recipe_id} is now reachable with grading {recipe_grading[recipe_id]}: {input_info}. "
                        f"Outputs: {[f'{m}: {material_grading[m]}' for m in instantiated_recipe_list[recipe_id].output_dict.keys()]}"
                    )
        if iterations == max_iterations:
            _LOGGER.warning("Maximum iterations reached while filling gradings. Some materials may remain ungraded.")

    fill_gradings()

    if ignore_unreachable:
        unreachable = frozenset(m for m, g in material_grading.items() if g < 0)
        remaining = []
        for recipe_id, recipe in enumerate(instantiated_recipe_list):
            inputs = {m for m, a in recipe.input_dict.items() if a != 0}
            remaining.append(len(inputs - unreachable))

        material_grading = {m: -1 for m in materials.values()}  # positive values = visited
        recipe_grading = [-1] * len(instantiated_recipe_list)  # positive values = visited
        double_ended_queue = deque(starting_materials)
        for m in double_ended_queue:
            material_grading[m] = 0
        fill_gradings()

    recipe_grading = {r.id: g for r, g in zip(instantiated_recipe_list, recipe_grading)}
    return recipe_grading, material_grading
