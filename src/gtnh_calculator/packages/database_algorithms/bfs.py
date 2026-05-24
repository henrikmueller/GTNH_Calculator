import pandas as pd
from typing import Dict
from collections import defaultdict
from collections import deque
import logging

from ..utility.general_utility import Timer
from ..recipes_db.material import Material, MaterialGroup
from ..recipes_db.machines import Machine
from ..recipes_db.voltage_tiers import VoltageTier

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)


def get_reachable_recipes(
    df_recipes: pd.DataFrame, extracted_materials: Dict[str, Material],
    starting_materials: set[Material], sort=False
) -> tuple[Dict[Material, int], pd.DataFrame]:
    outputs = df_recipes['AVG_OUTPUTS']
    node_to_edges = defaultdict(list)
    remaining = []
    for edge_id, inputs_groups in enumerate(df_recipes['TOTAL_INPUTS']):
        tmp = [True] * len(inputs_groups)
        for i, (input_group, amount) in enumerate(inputs_groups.items()):
            if amount == 0:
                tmp[i] = False
                continue
            for material in input_group.materials:
                node_to_edges[material].append((edge_id, i))
        remaining.append(tmp)

    material_grading = {m: -1 for m in extracted_materials.values()}  # positive values = visited
    recipe_grading = [-1] * df_recipes.shape[0]  # positive values = visited
    double_ended_queue = deque(starting_materials)
    for m in double_ended_queue:
        material_grading[m] = 0

    while double_ended_queue:
        material = double_ended_queue.popleft()
        if material_grading[material] < 0:  # TODO: Remove later
            raise AssertionError(f'Negative grading for material in queue: {material} | {double_ended_queue}')
        for edge_id, index in node_to_edges[material]:
            remaining[edge_id][index] = False

            if sum(remaining[edge_id]) == 0 and recipe_grading[edge_id] < 0:
                recipe_grading[edge_id] = material_grading[material]
                for output in outputs.iloc[edge_id].keys():
                    if material_grading[output] < 0:
                        material_grading[output] = material_grading[material] + 1
                        double_ended_queue.append(output)

    df_reachable_recipes = df_recipes.assign(GRADING=recipe_grading)[[r >= 0 for r in recipe_grading]]
    if sort:
        df_reachable_recipes = df_reachable_recipes.sort_values(by='GRADING')
    return material_grading, df_reachable_recipes

def get_ingredient_recipes(
    df_recipes: pd.DataFrame, extracted_materials: Dict[str, Material],
    target_materials: list[Material], sort=False
) -> tuple[list[tuple[Material, int]], pd.DataFrame]:
    """
    Calculates recipes and materials which can be used to craft the target materials
    :param df_recipes:
    :param target_materials:
    :param sort:
    :return:
    """
    input_groups = df_recipes['TOTAL_INPUTS']
    node_to_edges = defaultdict(list)
    for edge_id, avg_outputs in enumerate(df_recipes['AVG_OUTPUTS']):
        for i, (output, amount) in enumerate(avg_outputs.items()):
            if amount <= 0:
                continue
            node_to_edges[output].append(edge_id)

    material_grading = {m: -1 for m in extracted_materials.values()}  # positive values = visited
    recipe_grading = [-1] * df_recipes.shape[0]  # positive values = visited
    double_ended_queue = deque(target_materials)
    for m in target_materials:
        material_grading[m] = 0

    while double_ended_queue:
        material = double_ended_queue.popleft()
        for edge_id in node_to_edges[material]:
            if recipe_grading[edge_id] < 0:
                recipe_grading[edge_id] = material_grading[material]
                for input_group in input_groups.iloc[edge_id].keys():
                    for input in input_group.materials:
                        if material_grading[input] < 0:
                            material_grading[input] = material_grading[material] + 1
                            double_ended_queue.append(input)

    reachable_materials_graded = [(m, r) for m, r in material_grading.items() if r >= 0]
    reachable_materials_graded.sort(key=lambda x: x[1])
    df_reachable_recipes = df_recipes.assign(OUTPUT_GRADING=recipe_grading)[[r >= 0 for r in recipe_grading]]
    if sort:
        df_reachable_recipes = df_reachable_recipes.sort_values(by='OUTPUT_GRADING')
    return reachable_materials_graded, df_reachable_recipes


def calculate_unlock_tiers(
    df_recipes: pd.DataFrame, extracted_materials: Dict[str, Material]
):
    with Timer('calculate_unlock_tiers'):
        df_recipes = df_recipes.reset_index()
        ids = df_recipes['ID']
        total_inputs = df_recipes['TOTAL_INPUTS']
        outputs = df_recipes['AVG_OUTPUTS']
        voltage_tiers: list[int] = list(df_recipes['VOLTAGE_TIER'])
        node_to_edges = defaultdict(list)
        unlock_tiers_groups = []
        for edge_id, row in enumerate(df_recipes.itertuples(index=False)):
            input_groups: Dict[MaterialGroup, float] = row.TOTAL_INPUTS
            n = len(input_groups)
            tmp: list[int | None] = [None] * (n + 1)
            for i, (input_group, amount) in enumerate(input_groups.items()):
                if amount == 0:
                    tmp[i] = VoltageTier.NO_REQUIREMENT
                    continue
                for material in input_group.materials:
                    node_to_edges[material].append((edge_id, i))
            machines: set[Machine] = row.MACHINES
            for machine in machines:
                node_to_edges[machine.item].append((edge_id, n))
            unlock_tiers_groups.append(tmp)

        unlock_tiers: Dict[Material, int | None] = {m: None for m in extracted_materials.values()}
        gates: Dict[Material, set[MaterialGroup | Material | Machine | str]] = {
            m: set() for m in extracted_materials.values()}
        recipe_unlock_tiers: list[int | None] = [None] * df_recipes.shape[0]
        for material in extracted_materials.values():
            if material.is_starting():
                unlock_tiers[material] = VoltageTier.NO_REQUIREMENT

        double_ended_queue = deque([m for m, t in unlock_tiers.items() if t is not None])

        while double_ended_queue:
            material = double_ended_queue.popleft()
            if unlock_tiers[material] is None:  # TODO: Remove later
                raise AssertionError(f'Invalid unlock tier: {material} | {double_ended_queue}')
            for edge_id, index in node_to_edges[material]:
                unlock_tiers_groups_recipe = unlock_tiers_groups[edge_id]
                unlock_tiers_groups_recipe[index] = unlock_tiers[material]
                if unlock_tiers_groups_recipe.count(None) > 0:
                    continue
                
                new_tier = max(max(unlock_tiers_groups_recipe), voltage_tiers[edge_id])
                recipe_unlock_tiers[edge_id] = new_tier

                new_gates = set()
                for index, input_group in enumerate(total_inputs.iloc[edge_id].keys()):
                    if unlock_tiers_groups_recipe[index] == new_tier:
                        new_gates.add(input_group)
                if unlock_tiers_groups_recipe[-1] == new_tier:
                    new_gates |= df_recipes['MACHINES'].iloc[edge_id]
                if voltage_tiers[edge_id] == new_tier:
                    new_gates.add(ids.iloc[edge_id])

                for output in outputs.iloc[edge_id].keys():
                    if unlock_tiers[output] is not None and new_tier >= unlock_tiers[output]:
                        if new_tier == unlock_tiers[output]:
                            gates[output] |= new_gates
                        continue
                    gates[output] = new_gates.copy()
                    unlock_tiers[output] = new_tier
                    double_ended_queue.append(output)

        # df_reachable_recipes = df_recipes.assign(GRADING=recipe_grading)[[r >= 0 for r in recipe_grading]]
        # test = [(m, t) for m, t in unlock_tiers.items() if t is not None and t >= 1]
        # for m, t in test[:10]:
        #     print(f'{m}: {t}.   Gates: {gates[m]}')

        print('SPECIFIC')
        specific_ids = [
            'f~GalacticraftMars~hydrogen', 'f~GalacticraftMars~oxygen', 'i~gregtech~gt.blockmachines~421',
            'i~minecraft~brick_block~0', 'i~etfuturum~blast_furnace~0', 'i~gregtech~gt.blockmachines~106',
            'i~gregtech~gt.metaitem.01~2805', 'i~minecraft~paper~0', 'i~gregtech~gt.blockmachines~118',
            'i~CarpentersBlocks~blockCarpentersBlock~0', 'i~gregtech~gt.metaitem.01~11308',
            'i~minecraft~redstone~0'
        ]
        for id in specific_ids:
            m = extracted_materials[id]
            print(f'{m}: {unlock_tiers[m]}.   Gates: {gates[m]}')

    return unlock_tiers
