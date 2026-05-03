import sqlite3
from dataclasses import dataclass
import re
import yaml
import pandas as pd
import logging
from typing import Dict
from collections import defaultdict
import json
from itertools import chain
from collections import deque

from ..recipes_db.material import ExtractedItem, ExtractedFluid, Material, MaterialGroup
from ..recipes_db.voltage_tiers import VoltageTier
from ..recipes_db.machine_stats import MachineStats
from ..recipes_db.machines import Machine, MachineType
from ..recipes_db.behaviours.machine_behaviours import MachineBehaviour
from ..recipes_db.machine_options.machine_option_books import load_possible_machine_options, MachineOptionsBook
from ..recipes_db.machine_options.machine_option_types import MachineOptionType
from .database_building_options import steam_machines
from ..utility.general_utility import str_to_float, Timer, print_df
from ..utility.constants import GT_EU_KEY, INCLUDE_DEPRECATED_MACHINES

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


@dataclass
class GTNHDatabase:
    df_recipes: pd.DataFrame
    extracted_materials: Dict[str, Material]
    extracted_machines: Dict[str, Machine]
    machine_options_book: MachineOptionsBook
    includes_deprecated_machines: bool = INCLUDE_DEPRECATED_MACHINES

    def mod_set_materials(self) -> set[str]:
        return set(m.mod for m in self.extracted_materials.values())

    def mod_set_recipes(self) -> set[str]:
        return set(self.df_recipes['CATEGORY'].unique())

    def add_eu(self) -> None:
        if GT_EU_KEY in self.extracted_materials.keys():
            raise AssertionError(f'{GT_EU_KEY} must not a key of material.')
        self.extracted_materials[GT_EU_KEY] = Material(
            id=GT_EU_KEY,
            image_file_path='',
            name='EU',
            mod='gregtech',
            nbt='',
            tooltip='The Electric Unit, the standard unit of energy in GTNH.'
        )

    def filter_recipes(
        self,
        df_recipes: pd.DataFrame,
        inputs: set[Material] | None = None,
        outputs: set[Material] | None = None,
        voltage_tiers: set[int] | None = None,
        categories: set[str] | None = None,
        machines: set[Machine] | None = None
    ) -> pd.DataFrame:
        df_result = df_recipes.copy(deep=False)
        if inputs is not None:
            df_result = df_result[df_result['TOTAL_INPUTS'].map(lambda input_groups: all(
                any(input in input_group.materials for input_group in input_groups) for input in inputs
            ))]
        if outputs is not None:
            df_result = df_result[df_result['AVG_OUTPUTS'].map(lambda avg_outputs: all(
                output in avg_outputs.keys() for output in outputs
            ))]
        if voltage_tiers is not None:
            if max(voltage_tiers) - min(voltage_tiers) + 1 == len(voltage_tiers):
                df_result = df_result[(df_result['VOLTAGE_TIER'] >= min(voltage_tiers)) &
                                       (df_result['VOLTAGE_TIER'] <= max(voltage_tiers))]
            else:
                df_result = df_result[df_result['VOLTAGE_TIER'].isin(voltage_tiers)]
        if categories is not None:
            df_result = df_result[df_result['CATEGORY'].isin(categories)]
        if machines is not None:
            df_result['MACHINES'] = df_result['MACHINES'].map(lambda s: s & machines)
            df_result = df_result[df_result['MACHINES'].map(len) > 0]
        return df_result

    def get_reachable_recipes(
            self, df_recipes: pd.DataFrame,
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

        material_grading = {m: -1 for m in self.extracted_materials.values()}  # positive values = visited
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
        self, df_recipes: pd.DataFrame,
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

        material_grading = {m: -1 for m in self.extracted_materials.values()}  # positive values = visited
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

    @staticmethod
    def _get_base_machines(recipe_row, default_voltage_tier: int | None = None) -> list[Machine]:
        groups = defaultdict(set)
        for machine in recipe_row.MACHINES:
            for voltage_tier in machine.voltage_tiers:
                if default_voltage_tier is None or voltage_tier <= default_voltage_tier:
                    groups[(frozenset(machine.machine_types), machine.multiblock)].add(machine)
                    break
        if default_voltage_tier is None:
            base_machines = [
                min(group, key=lambda m: (m.weight, m.minimal_voltage_tier()))
                for group in groups.values()
            ]
        else:
            base_machines = [
                min(group, key=lambda m: (m.weight, -m.minimal_voltage_tier()))
                for group in groups.values()
            ]
        if not base_machines:
            _LOGGER.debug(f'No base machines found. Machine groups: '
                            f'{[(t, [(m.name, m.voltage_tiers) for m in g]) for t, g in groups.items()]}')
        return base_machines

    def get_default_machine(self, recipe_row, default_voltage_tier: int) -> Machine | None:
        base_machines = self._get_base_machines(recipe_row, default_voltage_tier)
        if not all(m.multiblock for m in base_machines):
            base_machines = [m for m in base_machines if not m.multiblock]
        base_machine_names = [m.name for m in base_machines]
        if 'Large Chemical Reactor' in base_machine_names and 'Mega Chemical Reactor' in base_machine_names:
            base_machines = [m for m in base_machines if m.name != 'Mega Chemical Reactor']
        if 'Large Scale Auto-Assembler v1.01' in base_machine_names and 'Precise Auto-Assembler MT-3662' in base_machine_names:
            base_machines = [m for m in base_machines if m.name != 'Precise Auto-Assembler MT-3662']
        if 'Dangote Distillus' in base_machine_names and 'Mega Distillation Tower' in base_machine_names:
            base_machines = [m for m in base_machines if m.name != 'Mega Distillation Tower']
        if 'Distillation Tower' in base_machine_names and 'Dangote Distillus' in base_machine_names:
            base_machines = [m for m in base_machines if m.name != 'Dangote Distillus']
        if 'Neutronium Compressor' in base_machine_names and 'Pseudostable Black Hole Containment Field' in base_machine_names:
            base_machines = [m for m in base_machines if m.name != 'Pseudostable Black Hole Containment Field']

        if len(base_machines) == 1:
            return base_machines[0]
        if 'Superdense Magnetohydrodynamically Constrained Star Matter Plate' in [m.name for m in
                                                                                  recipe_row.AVG_OUTPUTS.keys()]:
            return [m for m in base_machines if m.name == 'Pseudostable Black Hole Containment Field'][0]

        _LOGGER.debug(f'No default machine: {base_machines} | {recipe_row}. \n'
                      f'Machines: {[(m.name, m.voltage_tiers) for m in recipe_row.MACHINES]}')
        return None


@dataclass
class DatabaseExtractor:
    database_path = 'db/gtnh-2-8-db.db'
    timer = True
    validity_check: bool

    def extract_database(self) -> GTNHDatabase:
        extracted_fluids = self.extract_fluids()
        yield 0.05
        extracted_items = self.extract_items(extracted_fluids)
        extracted_materials = extracted_items | extracted_fluids
        yield 0.1
        machine_options_path = 'config/fixed_settings/machine_options_db.yaml'
        machine_options_book = load_possible_machine_options(machine_options_path, extracted_materials)
        yield 0.15
        machines, machine_types = self.extract_machine_types(extracted_items)
        yield 0.2
        df_recipes = yield from self.extract_recipes(extracted_items, extracted_fluids, machines)
        return GTNHDatabase(
            df_recipes=df_recipes,
            extracted_materials=extracted_materials,
            extracted_machines=machines,
            machine_options_book=machine_options_book
        )

    def extract_recipes(
        self, extracted_items: Dict[str, ExtractedItem], extracted_fluids: Dict[str, ExtractedFluid],
            extracted_machines: Dict[str, Machine]
    ):
        conn = sqlite3.connect(self.database_path)
        conn.execute("PRAGMA cache_size = -200000")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_item_group_stacks_group_cover
            ON ITEM_GROUP_ITEM_STACKS(ITEM_GROUP_ID, ITEM_STACKS_ITEM_ID, ITEM_STACKS_STACK_SIZE);
            
            CREATE INDEX IF NOT EXISTS idx_recipe_item_group_join
            ON RECIPE_ITEM_GROUP(ITEM_INPUTS_ID, RECIPE_ID);
            
            CREATE INDEX IF NOT EXISTS idx_item_group_stacks_group
            ON ITEM_GROUP_ITEM_STACKS(ITEM_GROUP_ID);
            
            CREATE INDEX IF NOT EXISTS idx_recipe_item_group_input
            ON RECIPE_ITEM_GROUP(ITEM_INPUTS_ID);
            
            CREATE INDEX IF NOT EXISTS idx_recipe_item_group_recipe
            ON RECIPE_ITEM_GROUP(RECIPE_ID);
            
            CREATE INDEX IF NOT EXISTS idx_recipe_type ON RECIPE(RECIPE_TYPE_ID);
            
            CREATE INDEX IF NOT EXISTS idx_recipe_fluid_group_recipe
            ON RECIPE_FLUID_GROUP(RECIPE_ID);
            
            CREATE INDEX IF NOT EXISTS idx_fluid_group_items
            ON FLUID_GROUP_FLUID_STACKS(FLUID_GROUP_ID);
            
            CREATE INDEX IF NOT EXISTS idx_item_outputs_recipe
            ON RECIPE_ITEM_OUTPUTS(RECIPE_ID);
            
            CREATE INDEX IF NOT EXISTS idx_fluid_outputs_recipe
            ON RECIPE_FLUID_OUTPUTS(RECIPE_ID);
            
            CREATE INDEX IF NOT EXISTS idx_greg_recipe_recipe
            ON GREG_TECH_RECIPE(RECIPE_ID);
            
            CREATE INDEX IF NOT EXISTS idx_metadata_greg_recipe
            ON GREG_TECH_RECIPE_METADATA(GREG_TECH_RECIPE_ID);
            
            CREATE INDEX IF NOT EXISTS idx_fluid_group_cover
            ON FLUID_GROUP_FLUID_STACKS(
                FLUID_GROUP_ID,
                FLUID_STACKS_FLUID_ID,
                FLUID_STACKS_AMOUNT
            );
            
            CREATE INDEX IF NOT EXISTS idx_recipe_fluid_group_input
            ON RECIPE_FLUID_GROUP(FLUID_INPUTS_ID);
        """)
        yield 0.25

        with Timer('static', active=self.timer):
            query = """
                SELECT
                    RECIPE.ID,
                    RECIPE.RECIPE_TYPE_ID,
                    RECIPE_TYPE.CATEGORY,
                    GREG_TECH_RECIPE.ADDITIONAL_INFO,
                    GREG_TECH_RECIPE.AMPERAGE,
                    GREG_TECH_RECIPE.DURATION,
                    GREG_TECH_RECIPE.RECIPE_SPECIAL_VALUE,
                    GREG_TECH_RECIPE.VOLTAGE,
                    GREG_TECH_RECIPE.VOLTAGE_TIER
                FROM RECIPE
                LEFT JOIN RECIPE_TYPE ON RECIPE.RECIPE_TYPE_ID = RECIPE_TYPE.ID
                LEFT JOIN GREG_TECH_RECIPE ON RECIPE.ID = GREG_TECH_RECIPE.RECIPE_ID
            """
            static_df = pd.read_sql_query(query, conn)
            static_df['EU_PER_TICK'] = static_df['VOLTAGE'] * static_df['AMPERAGE']
            static_df['DURATION'] = static_df['DURATION'].fillna(0)
            static_df['TOTAL_EU'] = static_df['EU_PER_TICK'] * static_df['DURATION']
            static_df['DURATION'] /= 20
            static_df['VOLTAGE_TIER'] = static_df['VOLTAGE_TIER'].map(VoltageTier.to_voltage_tier)
            static_df["AMPERAGE"] = static_df["AMPERAGE"].fillna(0)
            recipe_ids = static_df["ID"].to_numpy()
            yield 0.3

        with Timer('recipe_types', active=self.timer):
            df_recipe_types = self.extract_recipe_types(extracted_machines)
            yield 0.32

        with Timer('valid_machines', active=self.timer):
            df_valid_machines = (
                static_df
                .merge(df_recipe_types, on="RECIPE_TYPE_ID", how="left")
                .groupby("ID")["MACHINES"]
                .agg(lambda x: set(chain.from_iterable(x)))
                .reset_index()
            )
            yield 0.35

        with (Timer('item_inputs_all', active=self.timer)):
            query = """
                WITH item_groups AS MATERIALIZED (
                    SELECT
                        ITEM_GROUP_ID,
                        json_group_array(ITEM_STACKS_ITEM_ID) AS item_ids,
                        - MIN(ITEM_STACKS_STACK_SIZE) AS amount
                    FROM ITEM_GROUP_ITEM_STACKS
                    GROUP BY ITEM_GROUP_ID
                )

                SELECT
                    rig.RECIPE_ID AS ID,
                    json_group_array(
                        json_object(
                            'item_ids', json(ig.item_ids),
                            'key', rig.ITEM_INPUTS_KEY,
                            'amount', ig.amount
                        )
                    ) AS ITEM_INPUTS_JSON
                FROM RECIPE_ITEM_GROUP rig
                LEFT JOIN item_groups ig
                    ON ig.ITEM_GROUP_ID = rig.ITEM_INPUTS_ID
                GROUP BY rig.RECIPE_ID
            """
            item_inputs_all_df = pd.read_sql_query(query, conn)
            yield 0.39
            item_inputs_all_df["ITEM_INPUTS_JSON"] = item_inputs_all_df["ITEM_INPUTS_JSON"].apply(json.loads)
            yield 0.4
            item_inputs_all = {}
            # for row in item_inputs_all_df.itertuples(index=False):
            #     for input_group in row.ITEM_INPUTS_JSON:
            #         item_inputs_all.setdefault(row.ID, defaultdict(int))[
            #             MaterialGroup([extracted_items[id] for id in input_group['item_ids']])
            #         ] += input_group['amount']
            for row in item_inputs_all_df.itertuples(index=False):
                for input_group in row.ITEM_INPUTS_JSON:
                    item_inputs_all.setdefault(row.ID, {})[input_group['key']] = (
                        MaterialGroup([extracted_items[id] for id in input_group['item_ids']]), input_group['amount']
                    )
            yield 0.45

        with Timer('fluid_inputs_all', active=self.timer):
            query = """
                WITH fluid_groups AS MATERIALIZED (
                    SELECT
                        FLUID_GROUP_ID,
                        json_group_array(FLUID_STACKS_FLUID_ID) AS fluid_ids,
                        - MIN(FLUID_STACKS_AMOUNT) AS amount
                    FROM FLUID_GROUP_FLUID_STACKS
                    GROUP BY FLUID_GROUP_ID
                )
                
                SELECT
                    rfg.RECIPE_ID AS ID,
                    json_group_array(
                        json_object(
                            'fluid_ids', json(fg.fluid_ids),
                            'key', - rfg.FLUID_INPUTS_KEY - 1,
                            'amount', fg.amount
                        )
                    ) AS FLUID_INPUTS_JSON
                FROM RECIPE_FLUID_GROUP rfg
                LEFT JOIN fluid_groups fg
                    ON fg.FLUID_GROUP_ID = rfg.FLUID_INPUTS_ID
                GROUP BY rfg.RECIPE_ID
            """
            fluid_inputs_all_df = pd.read_sql_query(query, conn)
            yield 0.47
            fluid_inputs_all_df["FLUID_INPUTS_JSON"] = fluid_inputs_all_df["FLUID_INPUTS_JSON"].apply(json.loads)
            fluid_inputs_all = {}
            for row in fluid_inputs_all_df.itertuples(index=False):
                for input_group in row.FLUID_INPUTS_JSON:
                    fluid_inputs_all.setdefault(row.ID, {})[input_group['key']] = (
                        MaterialGroup([extracted_fluids[id] for id in input_group['fluid_ids']]), input_group['amount']
                    )
            yield 0.5

        with Timer('inputs_all', active=self.timer):
            inputs_all = pd.DataFrame({
                "ID": list(recipe_ids),
                "INPUT_GROUPS": [
                    item_inputs_all.get(id, {}) | fluid_inputs_all.get(id, {}) for id in recipe_ids
                ]
            })
            yield 0.53

            def average_inputs(inputs):
                result = defaultdict(float)
                for input_group, amount in inputs.values():
                    result[input_group] += amount
                return result
            inputs_all['TOTAL_INPUTS'] = inputs_all['INPUT_GROUPS'].map(average_inputs)
            yield 0.55

        with Timer('item_outputs', active=self.timer):
            query = """
                SELECT
                    rio.RECIPE_ID AS ID,
                    json_group_array(
                        json_object(
                            'item_id', rio.ITEM_OUTPUTS_VALUE_ITEM_ID,
                            'amount', rio.ITEM_OUTPUTS_VALUE_STACK_SIZE,
                            'probability', rio.ITEM_OUTPUTS_VALUE_PROBABILITY,
                            'key', rio.ITEM_OUTPUTS_KEY
                        )
                    ) AS ITEM_OUTPUTS_JSON
                FROM RECIPE_ITEM_OUTPUTS rio
                GROUP BY rio.RECIPE_ID
            """
            item_outputs_all_df = pd.read_sql_query(query, conn)
            yield 0.58
            item_outputs_all_df["ITEM_OUTPUTS_JSON"] = item_outputs_all_df["ITEM_OUTPUTS_JSON"].apply(json.loads)
            item_outputs_all = {}
            for row in item_outputs_all_df.itertuples(index=False):
                for output in row.ITEM_OUTPUTS_JSON:
                    item = extracted_items[output['item_id']]
                    item_outputs_all.setdefault(row.ID, {})[output['key']] = \
                        (item, output['amount'], output['probability'])
            yield 0.6

        with Timer('fluid_outputs', active=self.timer):
            query = """
                SELECT
                    rfo.RECIPE_ID AS ID,
                    json_group_array(
                        json_object(
                            'fluid_id', rfo.FLUID_OUTPUTS_VALUE_FLUID_ID,
                            'amount', rfo.FLUID_OUTPUTS_VALUE_AMOUNT,
                            'probability', rfo.FLUID_OUTPUTS_VALUE_PROBABILITY,
                            'key', - rfo.FLUID_OUTPUTS_KEY - 1
                        )
                    ) AS FLUID_OUTPUTS_JSON
                FROM RECIPE_FLUID_OUTPUTS rfo
                GROUP BY rfo.RECIPE_ID
            """
            fluid_outputs_all_df = pd.read_sql_query(query, conn)
            yield 0.63
            fluid_outputs_all_df["FLUID_OUTPUTS_JSON"] = fluid_outputs_all_df["FLUID_OUTPUTS_JSON"].apply(json.loads)
            fluid_outputs_all = {}
            for row in fluid_outputs_all_df.itertuples(index=False):
                for output in row.FLUID_OUTPUTS_JSON:
                    fluid = extracted_fluids[output['fluid_id']]
                    fluid_outputs_all.setdefault(row.ID, {})[output['key']] = \
                        (fluid, output['amount'], output['probability'])
            yield 0.65

        with Timer('all_outputs', active=self.timer):
            def average_outputs(outputs):
                result = defaultdict(float)
                for output, amount, probability in outputs.values():
                    result[output] += amount * probability
                return result

            outputs_dict = {
                "ID": list(recipe_ids),
                "OUTPUTS": [
                    item_outputs_all.get(id, {}) | fluid_outputs_all.get(id, {}) for id in recipe_ids
                ]
            }
            outputs_all = pd.DataFrame(outputs_dict)
            outputs_all['AVG_OUTPUTS'] = outputs_all['OUTPUTS'].map(average_outputs)
            yield 0.7

        with Timer('special_items', active=self.timer):
            query = """
                SELECT
                    RECIPE.ID,
                    json_group_array(SPECIAL_ITEMS_ID) AS SPECIAL_ITEMS_ID
                FROM GREG_TECH_RECIPE_ITEM
                LEFT JOIN GREG_TECH_RECIPE ON GREG_TECH_RECIPE_ITEM.GREG_TECH_RECIPE_ID = GREG_TECH_RECIPE.ID
                LEFT JOIN RECIPE ON GREG_TECH_RECIPE.RECIPE_ID = RECIPE.ID
                GROUP BY RECIPE.ID
            """
            special_items_df = pd.read_sql_query(query, conn)
            yield 0.73
            special_items_df['SPECIAL_ITEMS'] = special_items_df["SPECIAL_ITEMS_ID"].apply(json.loads).map(
                lambda ids: [extracted_items[id] for id in ids]
            )
            special_items_df = special_items_df.drop(columns=['SPECIAL_ITEMS_ID'])
            yield 0.75

        with Timer('metadata', active=self.timer):
            query = """
                SELECT
                    RECIPE.ID,
                    json_group_array(
                        json_object(
                            'metadata_key', GREG_TECH_RECIPE_METADATA.METADATA_KEY,
                            'metadata_value', GREG_TECH_RECIPE_METADATA.METADATA_VALUE
                        )
                    ) AS METADATA
                FROM GREG_TECH_RECIPE_METADATA
                LEFT JOIN GREG_TECH_RECIPE ON GREG_TECH_RECIPE_METADATA.GREG_TECH_RECIPE_ID = GREG_TECH_RECIPE.ID
                LEFT JOIN RECIPE ON GREG_TECH_RECIPE.RECIPE_ID = RECIPE.ID
                GROUP BY RECIPE.ID
            """
            metadata_df = pd.read_sql_query(query, conn)
            yield 0.78
            metadata_df['METADATA'] = metadata_df["METADATA"].apply(json.loads).map(
                lambda x: {d["metadata_key"]: d["metadata_value"] for d in x} if x else {}
            )
            yield 0.8

        conn.close()

        df_all = static_df.set_index("ID")
        yield 0.82
        df_all = df_all.join(inputs_all.set_index("ID"))
        yield 0.84
        df_all = df_all.join(outputs_all.set_index("ID"))
        yield 0.86
        df_all = df_all.join(special_items_df.set_index("ID"))
        yield 0.87
        df_all = df_all.join(metadata_df.set_index("ID"))
        mask = df_all['METADATA'].isna()
        df_all.loc[mask, 'METADATA'] = [{} for _ in range(mask.sum())]
        yield 0.88
        df_all = df_all.join(df_valid_machines.set_index("ID"))
        df_all = df_all[df_all['MACHINES'].map(len) > 0]
        yield 0.9

        # df_test = df_all[df_all['OUTPUTS'].map(lambda x: any('Sodium Hydroxide' in o[0].name for o in x.values()))]
        # df_test = df_all[df_all['MACHINES'].map(lambda x: any('Assembling Machine' in m.name for m in x))]
        # print_df(df_test, limit_rows=False)

        # TODO: Special Cases: Plant Mass. Save number of output slots of every machine somewhere

        # starting_materials = [extracted_materials['i~IC2~itemCellEmpty~0']]
        # reachable_materials, df_reachable_recipes = (
        #     self.get_reachable_recipes(df_all, extracted_materials, starting_materials, sort=True))
        # print_df(df_reachable_recipes, limit_rows=False, max_rows=100)

        yield 1
        return df_all

    # def get_recipes(self, df_recipes: pd.DataFrame) -> Dict[int, Recipe]:
    #     recipes = {}
    #     for row in df_recipes.itertuples(index=True):
    #         # raw_recipe = RawRecipe()
    #         recipes[row.INDEX] = 0
    #     return recipes

    def extract_items(self, extracted_fluids: Dict[str, ExtractedFluid]) -> Dict[str, ExtractedItem]:
        conn = sqlite3.connect(self.database_path)

        query = """
            SELECT
                ITEM.ID, 
                ITEM.IMAGE_FILE_PATH, 
                ITEM.LOCALIZED_NAME, 
                ITEM.MOD_ID, 
                ITEM.NBT, 
                ITEM.TOOLTIP,
                FLUID_CONTAINER.FLUID_STACK_AMOUNT AS FLUID_STACK_AMOUNT,
                FLUID_CONTAINER.EMPTY_CONTAINER_ID AS EMPTY_CONTAINER_ID,
                FLUID_CONTAINER.FLUID_STACK_FLUID_ID AS FLUID_ID
            FROM ITEM
            LEFT JOIN FLUID_CONTAINER ON ITEM.ID = FLUID_CONTAINER.CONTAINER_ID
        """
        df_items = pd.read_sql_query(query, conn)
        df_items["FLUID_STACK_AMOUNT"] = df_items["FLUID_STACK_AMOUNT"].fillna(0)
        df_items = df_items.rename(columns={
            'ID': 'id', 'IMAGE_FILE_PATH': 'image_file_path', 'LOCALIZED_NAME': 'name', 'MOD_ID': 'mod',
            'NBT': 'nbt', 'TOOLTIP': 'tooltip', 'FLUID_STACK_AMOUNT': 'fluid_amount',
            'EMPTY_CONTAINER_ID': 'empty_fluid_container', 'FLUID_ID': 'fluid'
        })
        conn.close()
        extracted_items = {
            row[0]: ExtractedItem(
                *row[:8],
                fluid=extracted_fluids[row.fluid] if row.fluid in extracted_fluids.keys() else None,
            ) for row in df_items.itertuples(index=False)
        }
        for item in extracted_items.values():
            if item.empty_fluid_container in extracted_items.keys():
                item.empty_fluid_container = extracted_items[item.empty_fluid_container]
        _LOGGER.info(f'Extracted {len(extracted_items)} items from the database')
        return extracted_items

    def extract_fluids(self) -> Dict[str, ExtractedFluid]:
        conn = sqlite3.connect(self.database_path)

        query = """
        SELECT
            FLUID.ID,
            FLUID.IMAGE_FILE_PATH,
            FLUID.LOCALIZED_NAME,
            FLUID.MOD_ID,
            FLUID.NBT
        FROM FLUID
        """
        df_fluids = pd.read_sql_query(query, conn)
        df_fluids = df_fluids.rename(columns={
            'ID': 'id', 'IMAGE_FILE_PATH': 'image_file_path', 'LOCALIZED_NAME': 'name', 'MOD_ID': 'mod', 'NBT': 'nbt'
        })
        conn.close()

        extracted_fluids = {}
        for row in df_fluids.itertuples(index=False, name=None):
            fluid = ExtractedFluid(*row)
            extracted_fluids[fluid.id] = fluid
        _LOGGER.info(f'Extracted {len(extracted_fluids)} fluids from the database')
        return extracted_fluids

    def _get_recipe_type_dataframe(self) -> pd.DataFrame:
        conn = sqlite3.connect(self.database_path)

        query = """
            SELECT
                RECIPE_TYPE.ID AS RECIPE_TYPE_ID,
                RECIPE_TYPE.CATEGORY,
                RECIPE_TYPE.ICON_INFO,
                RECIPE_TYPE.TYPE AS TYPE_WITH_VOLTAGE,
                RECIPE_TYPE_ITEM.ICON_ID AS MACHINES
            FROM RECIPE_TYPE
            INNER JOIN (
                SELECT DISTINCT RECIPE_TYPE_ID FROM RECIPE
            ) RECIPE_TYPE_IDS ON RECIPE_TYPE.ID = RECIPE_TYPE_IDS.RECIPE_TYPE_ID
            LEFT JOIN RECIPE_TYPE_ITEM ON RECIPE_TYPE.ID = RECIPE_TYPE_ITEM.RECIPE_TYPE_ID
        """
        df_recipe_types = pd.read_sql_query(query, conn)
        conn.close()

        # Special treatments
        df_recipe_types.loc[
            (df_recipe_types['TYPE_WITH_VOLTAGE'] == 'Compressor') & (df_recipe_types['CATEGORY'] == 'avaritia'), 'TYPE_WITH_VOLTAGE'
        ] = 'Avaritia Compressor'  # Differentiate from GT Compressor
        return df_recipe_types

    def generate_machine_type_yaml(self, extracted_items: Dict[str, ExtractedItem]) -> None:
        df_recipe_types = self._get_recipe_type_dataframe()
        machines = {}
        voltages = [str(VoltageTier.eu_per_tick(v)) for v in VoltageTier.voltage_tiers_int()]
        for row in df_recipe_types.drop_duplicates('MACHINES').itertuples(index=False):
            item = extracted_items[row.MACHINES]
            if item.name in steam_machines:  # this tool is not for steam machines
                continue

            matches_voltage = re.search(r"§a(\d{1,3}(?:,\d{3})*)", item.tooltip)
            matches_type = re.search(r"Machine Type: §e([A-Za-z ,]*)§r", item.tooltip)
            voltage_tier = VoltageTier.voltage_tier_by_eu(str_to_float(
                matches_voltage.group(1).replace(',', ''))) if matches_voltage else VoltageTier.NO_REQUIREMENT
            types = [t.strip() for t in matches_type.group(1).split(',')] if matches_type else []
            deprecated = 'deprecated' in item.tooltip.lower()
            multiblock = 'structure guidelines' in item.tooltip.lower()
            if voltage_tier < 0 and not multiblock:
                if deprecated:
                    print('DEPRECATED:')
                print(f"'{item.name}': {voltage_tier}, {types}, {multiblock}")

            machines[row.MACHINES] = {
                'name': item.name,
                'voltage_tier': [voltage_tier] if not multiblock else VoltageTier.voltage_tiers_int(minimum=0),
                'multiblock': multiblock,
                'machine_types': types if types else [item.name]
            }
            if deprecated:
                machines[row.MACHINES]['deprecated'] = True

        with open("raw_machine_types.yaml", "w") as file:
            yaml.dump(machines, file)

    def extract_machine_types(
        self, extracted_items: Dict[str, ExtractedItem]
    ) -> tuple[Dict[str, Machine], Dict[str, MachineType]]:
        with (open('config/fixed_settings/machine_types_db.yaml') as f):
            machine_dict = yaml.safe_load(f)
            machine_count = len(machine_dict)
            machine_types = {}
            extracted_machines = {}
            for item_id, specification in machine_dict.items():
                deprecated = 'deprecated' in specification and specification['deprecated']
                if deprecated and not INCLUDE_DEPRECATED_MACHINES:
                    _LOGGER.info(f'Skipping deprecated machine {specification["name"]} ({item_id})')
                    continue
                try:
                    valid_options = (
                        [MachineOptionType(o.strip()) for o in specification['valid_options'].strip().split(',')]
                        if 'valid_options' in specification else []
                    )
                except ValueError as e:
                    raise ValueError(f'MachineOptionType could not be determined for {specification}')
                voltage_tier = min(specification['voltage_tier'])
                extracted_machines[item_id] = Machine(
                    name=specification['name'],
                    multiblock=specification['multiblock'],
                    deprecated=deprecated,
                    disabled='disabled' in specification and specification['disabled'],
                    unspecified='unspecified' in specification and specification['unspecified'],
                    item=extracted_items[item_id],
                    weight=specification['weight'] if 'weight' in specification else 0,
                    valid_options=valid_options,
                    machine_types=set(),
                    machine_stats=MachineStats(
                        voltage_tiers=[int(v) for v in specification['voltage_tier']],
                        _voltage_tier=voltage_tier,
                        speedup=specification['speedup'] if 'speedup' in specification else 1,
                        efficiency=specification['efficiency'] if 'efficiency' in specification else 1
                    ),
                    machine_behaviour=MachineBehaviour.create_machine_behaviour(specification)
                )
                for machine_type_name in specification['machine_types']:
                    if machine_type_name not in machine_types.keys():
                        machine_types[machine_type_name] = []
                    machine_types[machine_type_name].append(extracted_machines[item_id])
            machine_types = {name: MachineType(name, machines) for name, machines in machine_types.items()}
            for machine_type in machine_types.values():
                for machine in machine_type.machines:
                    machine.machine_types.add(machine_type)
            _LOGGER.info(f'Extracted {machine_count} machines')
            _LOGGER.info(f'Built {len(machine_types)} machine types')

            if not self.validity_check:
                return extracted_machines, machine_types

            # Validity checks
            valid_voltages = VoltageTier.valid_voltage_tiers()
            for machine in extracted_machines.values():
                for v in machine.voltage_tiers:
                    if not isinstance(v, int) or v not in valid_voltages:
                        _LOGGER.error(f'Invalid voltage tier "{v}" for machine {machine}')

            for name, machine_type in machine_types.items():
                machines = [m for m in machine_type.machines if not m.unspecified]
                multiblocks = [m for m in machines if m.multiblock]
                sb_voltage_tiers = [v for m in machines if not m.multiblock for v in m.voltage_tiers]
                sb_voltage_tiers.sort()
                missing_vts = sb_voltage_tiers and (max(sb_voltage_tiers) - min(sb_voltage_tiers) + 1) != len(sb_voltage_tiers)
                duplicate_vts = len(sb_voltage_tiers) != len(set(sb_voltage_tiers))
                multiple_mbs = len(multiblocks) >= 2
                if missing_vts or duplicate_vts or multiple_mbs:
                    print(f'Potential problem for Machine Type {machine_type}')
                    if missing_vts or duplicate_vts:
                        print(f'Singleblock voltage tiers: {sb_voltage_tiers}')
                    if multiple_mbs:
                        print(f'Multiple multiblocks: {multiblocks}')
                    print()
            return extracted_machines, machine_types

    def extract_recipe_types(
            self, extracted_machines: Dict[str, Machine]
    ) -> pd.DataFrame:
        df_recipe_types = self._get_recipe_type_dataframe()

        df_recipe_types = (
            df_recipe_types
            .dropna(subset=['RECIPE_TYPE_ID'])
            .groupby(['RECIPE_TYPE_ID'], as_index=False)
            .agg({
                'CATEGORY': 'first',
                'ICON_INFO': 'first',
                'TYPE_WITH_VOLTAGE': 'first',
                'MACHINES': 'unique'
            })
        )

        def update_items(row):
            machines = [extracted_machines[x] for x in row['MACHINES'] if x in extracted_machines.keys()]
            return {m for m in machines if max(m.voltage_tiers) >= VoltageTier.to_voltage_tier(row['ICON_INFO'])}

        df_recipe_types['MACHINES'] = df_recipe_types.apply(update_items, axis=1)

        if self.validity_check:
            _LOGGER.warning(f'The following recipe types have no valid machines. This is not a problem by default,'
                            f'only if a recipe itself does not have valid machines.')
            print_df(df_recipe_types[df_recipe_types['MACHINES'].map(len) == 0], limit_rows=False)

        _LOGGER.info(f'Extracted {df_recipe_types.shape[0]} recipe types from the database')
        return df_recipe_types
