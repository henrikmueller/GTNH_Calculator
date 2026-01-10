import logging
from dataclasses import dataclass

import xlsxwriter.worksheet
from xlsxwriter.format import Format
import networkx as nx
import itertools
import xgi
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from typing import Dict
from netgraph import InteractiveGraph
from random import shuffle

from ..recipes.material import Material
from ..recipes.recipe import Recipe
from ..graphs.graded_layout import graded_layout
from ..graphs.graph_conversion import to_full_digraph
from ..utility.general_utility import get_n_colors

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class CraftingChainStatistics:
    time_interval: str
    total_inputs_per_time_interval: dict[Material, float]
    total_outputs_per_time_interval: dict[Material, float]
    total_eu_per_tick: float

    def markdown_inputs(self) -> str:
        return f"""
#### **Total inputs per {self.time_interval}**:

{', \n'.join(f'- {"{:.3f}".format(a)} {m}' for m, a in self.total_inputs_per_time_interval.items())}
"""

    def markdown_outputs(self) -> str:
        return f"""
#### **Total outputs per {self.time_interval}**:
    
{', \n'.join(f'- {"{:.3f}".format(a)} {m}' for m, a in self.total_outputs_per_time_interval.items())}
"""

    def markdown_eu(self) -> str:
        return f"""
#### **Total EU/t**: {"{:.3f}".format(self.total_eu_per_tick)}
"""


class CraftingChain:
    hypergraph: xgi.DiHypergraph
    recipe_amounts: Dict[int, float]
    recipe_matrix: np.ndarray
    materials: Dict[int, Material]
    infinite_materials: Dict[Material, bool]
    recipes: Dict[int, Recipe]
    recipe_indices: list[int]
    ordered_recipes: bool
    machine_amounts: Dict[int, float]
    eu_per_tick: list[float]
    total_eu_per_tick: float
    infinite_recipes: Dict[Recipe, bool]

    def __init__(
            self,
            hypergraph: xgi.DiHypergraph,
            recipe_amounts: Dict[int, float],
            recipe_matrix: np.ndarray,
            materials: Dict[int, Material],
            infinite_materials: Dict[Material, bool],
            recipes: Dict[int, Recipe],
            time: float
    ):
        self.hypergraph = hypergraph
        self.recipe_amounts = recipe_amounts
        self.recipe_matrix = recipe_matrix
        self.materials = materials
        self.infinite_materials = infinite_materials
        recipes = {i: recipe for i, recipe in recipes.items() if self.recipe_amounts[i] > 0}
        self.recipes = recipes

        graph = nx.DiGraph()
        graph.add_nodes_from(recipes.keys())
        graph.add_nodes_from(materials.values())
        for i, recipe in recipes.items():
            for input in recipe.get_inputs():
                graph.add_edge(input, i)
            for output in recipe.get_outputs():
                if output.id > 0: graph.add_edge(i, output)
        # nx.draw_networkx(graph, pos=nx.spring_layout(graph.nodes()), node_size=1000)
        # plt.show()
        if nx.is_directed_acyclic_graph(graph):
            self.recipe_indices = [node for node in nx.topological_sort(graph) if isinstance(node, int)]
            self.ordered_recipes = True
        else:
            self.recipe_indices = list(recipes.keys())
            self.ordered_recipes = False

        eu = materials[0]
        self.machine_amounts = {i: self.recipe_amounts[i] * recipes[i].processing_time / time for i in self.recipe_indices}
        self.eu_per_tick = [-recipes[i].materials[eu] * self.machine_amounts[i] / (20 * recipes[i].processing_time)
                            if recipes[i].processing_time > 0 else 0 for i in self.recipe_indices]
        self.total_eu_per_tick = sum(self.eu_per_tick)

        def calculate_infinites() -> None:

            recipe_vector = np.array([amount for _, amount in self.recipe_amounts.items()])
            total_material_needs = np.matmul(self.recipe_matrix, recipe_vector)
            total_material_amounts = {m: a for a, m in zip(total_material_needs, self.materials.values())}
            for material, infinite in self.infinite_materials.items():
                if infinite and total_material_amounts[material] == 0:
                    # This case probably does not occur for chance based materials
                    self.infinite_materials[material] = False

            remaining_recipes: list[Recipe] = list(self.recipes.values())
            detected_infinites = []
            infinite_recipes = {recipe: False for recipe in self.recipes.values()}

            while True:
                for recipe in remaining_recipes:
                    if all(self.infinite_materials[m] for m in recipe.get_inputs()):
                        for material in recipe.get_outputs():
                            self.infinite_materials[material] = True
                        infinite_recipes[recipe] = True
                        detected_infinites.append(recipe)
                if not detected_infinites:
                    break
                for recipe in detected_infinites:
                    remaining_recipes.remove(recipe)
                detected_infinites = []
            self.infinite_recipes = infinite_recipes

        calculate_infinites()

    def get_recipe(self, recipe_id: int) -> Recipe:
        return self.recipes[recipe_id]

    def materials_by_name(self) -> Dict[str, Material]:
        return {m.name: m for m in self.materials.values()}

    def statistics(self, time_factor, time_interval: str, do_print=False) -> CraftingChainStatistics:
        """
        ----------------------------------------------------------------------------------------------------------------
            Prepare recipe chain data for printing and drawing
        ----------------------------------------------------------------------------------------------------------------
        """
        df = self.to_dataframe(time_factor, time_interval)
        recipe_vector = np.array([amount for _, amount in self.recipe_amounts.items()])
        total_material_needs = time_factor * np.matmul(self.recipe_matrix, recipe_vector)
        total_materials = list(zip(total_material_needs, self.materials.values()))

        """
        ----------------------------------------------------------------------------------------------------------------
            Print crafting chain to console
        ----------------------------------------------------------------------------------------------------------------
        """
        if do_print:
            print(f'\nTotal Inputs per {time_interval}:')
            print(', '.join([f'{"{:.3f}".format(-amount)} {material}' for amount, material in total_materials if amount < 0]) + '\n')
            print(f'Total Outputs per {time_interval}:')
            print(', '.join([f'{"{:.3f}".format(amount)} {material}' for amount, material in total_materials if amount > 0]) + '\n')
            print(f'Total EU per tick {"{:.3f}".format(self.total_eu_per_tick)}:')
            print(f'Complete Recipe List{' (ordered)' if self.ordered_recipes else ''}:')
            print(df.to_string() + '\n')

        return CraftingChainStatistics(
            time_interval=time_interval,
            total_inputs_per_time_interval={material: -amount for amount, material in total_materials if amount < 0},
            total_outputs_per_time_interval={material: amount for amount, material in total_materials if amount > 0},
            total_eu_per_tick=self.total_eu_per_tick
        )

    def to_dataframe(self, time_factor, time_interval: str):
        columns = ['Recipe ID', 'Machine Amount', 'Machine', 'Voltage', f'Inputs per {time_interval}', f'Outputs per {time_interval}',
                   'EU/t', 'Infinite']
        n, q = len(columns), len(self.recipes)
        eu_per_tick = ["{:.3f}".format(entry) for entry in self.eu_per_tick]
        data = np.zeros((q, n), dtype=object)
        data[:, 0] = self.recipe_indices
        data[:, 1] = [f'{"{:.2f}".format(self.machine_amounts[i])}' for i in self.recipe_indices]
        data[:, 2] = [self.recipes[i].machine.__str__() for i in self.recipe_indices]
        data[:, 3] = [self.recipes[i].voltage_tier_name for i in self.recipe_indices]
        data[:, 4] = [self.recipes[i].input_string(time_factor * self.recipe_amounts[i]) for i in self.recipe_indices]
        data[:, 5] = [self.recipes[i].output_string(time_factor * self.recipe_amounts[i]) for i in self.recipe_indices]
        data[:, 6] = eu_per_tick
        data[:, 7] = [self.infinite_recipes[self.recipes[i]] for i in self.recipe_indices]
        return pd.DataFrame(data=data, columns=columns)

    def to_excel(self, time, time_factor, time_interval: str):

        columns = ['Recipe ID', 'Machine', f'Inputs per {time_interval}', f'Outputs per {time_interval}',
                   'EU/t']
        n, q = len(columns), len(self.recipes)
        machine_names = {i: (f'{f'{"{:.2f}".format(self.machine_amounts[i])}'} {self.recipes[i].machine.__str__()} '
                             f'({self.recipes[i].voltage_tier_name})') for i in self.recipe_indices}
        eu_per_tick = ["{:.3f}".format(entry) for entry in self.eu_per_tick]
        data = np.zeros((q, n), dtype=object)
        data[:, 0] = self.recipe_indices
        data[:, 1] = [machine_names[i] for i in self.recipe_indices]
        data[:, 2] = [self.recipes[i].input_string(time_factor * self.recipe_amounts[i]) for i in self.recipe_indices]
        data[:, 3] = [self.recipes[i].output_string(time_factor * self.recipe_amounts[i]) for i in self.recipe_indices]
        data[:, 4] = eu_per_tick

        recipe_vector = np.array([amount for _, amount in self.recipe_amounts.items()])
        total_material_needs = time_factor * np.matmul(self.recipe_matrix, recipe_vector)
        total_materials = list(zip(total_material_needs, self.materials.values()))

        """
        ----------------------------------------------------------------------------------------------------------------
            Write to Excel sheet
        ----------------------------------------------------------------------------------------------------------------
        """

        @dataclass
        class ExcelCell:
            entry: str
            format: Format | None = None

        excel_writer = pd.ExcelWriter('Test.xlsx', engine='xlsxwriter')
        workbook = excel_writer.book
        header_format = workbook.add_format({'bold': True})

        recipe_inputs = [self.recipes[i].input_string_array(time_factor * self.recipe_amounts[i]) for i in self.recipe_indices]
        recipe_outputs = [self.recipes[i].output_string_array(time_factor * self.recipe_amounts[i]) for i in self.recipe_indices]

        """
        ----------------------------------------------------------------------------------------------------------------
            Determine material colors
        ----------------------------------------------------------------------------------------------------------------
        """

        def get_material_colors() -> Dict[Material, int]:
            g = nx.Graph()
            for inputs, outputs in zip(recipe_inputs, recipe_outputs):
                recipe_materials = [entry[1] for entry in inputs + outputs]
                g.add_nodes_from(recipe_materials)
                g.add_edges_from(list(itertools.combinations(recipe_materials, 2)))
            return nx.coloring.greedy_color(g, strategy="largest_first")

        def get_material_colors_full() -> Dict[Material, int]:
            displayed_materials = [entry[1] for m in recipe_inputs + recipe_outputs for entry in m]
            shuffle(displayed_materials)
            return {material: i for i, material in enumerate(displayed_materials)}

        material_colors = get_material_colors_full()
        number_of_colors = max(material_colors.values()) + 1
        material_formats = []
        for color in get_n_colors(number_of_colors, saturation=0.8):
            material_formats.append(workbook.add_format({"font_color": color.hex}))

        def material_cell_entry(entry) -> ExcelCell:
            if isinstance(entry, str):
                return ExcelCell(entry)
            if isinstance(entry, tuple):
                amount, material = entry
                format = material_formats[material_colors[material]]
                return ExcelCell(f'{"{:.3f}".format(amount)} {material.name}', format=format)
            try:
                cell = ExcelCell(str(entry))
                return cell
            except ValueError:
                return ExcelCell('')

        """
        ----------------------------------------------------------------------------------------------------------------
            IO Sheet
        ----------------------------------------------------------------------------------------------------------------
        """

        input_material_table = np.array([[material.name, "{:.3f}".format(-amount)] for amount, material in total_materials if amount < 0])
        output_material_table = np.array([[material.name, "{:.3f}".format(amount)] for amount, material in total_materials if amount > 0])
        cell_array_io_rows = max(input_material_table.shape[0], output_material_table.shape[0]) + 1
        cell_array_io = np.full((cell_array_io_rows, 5), '', dtype=object)
        cell_array_io[0, 0] = f'Input Material'
        cell_array_io[0, 1] = f'Amount per {time_interval}:'
        cell_array_io[0, 3] = f'Output Material'
        cell_array_io[0, 4] = f'Amount per {time_interval}:'
        cell_array_io[1:input_material_table.shape[0]+1, 0:2] = input_material_table
        cell_array_io[1:output_material_table.shape[0]+1, 3:5] = output_material_table
        cell_array_io = np.vectorize(material_cell_entry)(cell_array_io)

        """
        ----------------------------------------------------------------------------------------------------------------
            Crafting chain sheet
        ----------------------------------------------------------------------------------------------------------------
        """

        max_inputs = max(
            [len(self.recipes[i].input_string_array(time_factor * self.recipe_amounts[i])) for i in self.recipe_indices]
        )
        max_outputs = max(
            [len(self.recipes[i].output_string_array(time_factor * self.recipe_amounts[i])) for i in self.recipe_indices]
        )
        cell_array_recipes = np.full((len(self.recipe_indices) + 1, 2 + max_inputs + max_outputs), '', dtype=object)

        input_array = np.full((len(self.recipe_indices), max_inputs), '', dtype=object)
        output_array = np.full((len(self.recipe_indices), max_outputs), '', dtype=object)
        for i in range(len(self.recipe_indices)):
            input_array[i, :len(recipe_inputs[i])] = recipe_inputs[i]
            output_array[i, :len(recipe_outputs[i])] = recipe_outputs[i]
        cell_array_recipes[0, :] = ([columns[0]] + [f'Input {i}' for i in range(1, max_inputs+1)] +
                             [f'Output {i}' for i in range(1, max_outputs+1)] + columns[3:])
        first_input_index, first_output_index = 1, 1 + max_inputs
        cell_array_recipes[1:, 0] = [machine_names[i] for i in self.recipe_indices]
        cell_array_recipes[1:, first_input_index:first_output_index] = input_array
        cell_array_recipes[1:, first_output_index:-1] = output_array
        cell_array_recipes[1:, -1] = eu_per_tick
        cell_array_recipes = np.vectorize(material_cell_entry)(cell_array_recipes)

        for cell in cell_array_io[0, :]:
            cell.format = header_format
        for cell in cell_array_recipes[0, :]:
            cell.format = header_format

        """
        ----------------------------------------------------------------------------------------------------------------
            Create excel file
        ----------------------------------------------------------------------------------------------------------------
        """

        @dataclass
        class ExcelWorksheet:
            worksheet: xlsxwriter.worksheet.Worksheet
            cell_array: np.ndarray

        excel_worksheets = [
            ExcelWorksheet(workbook.add_worksheet('IO'), cell_array_io),
            ExcelWorksheet(workbook.add_worksheet('Recipes'), cell_array_recipes)
        ]

        # Apply formatting row by row
        for excel_worksheet in excel_worksheets:
            for row_index, row in enumerate(excel_worksheet.cell_array):
                for column_index, excel_cell in enumerate(row):
                    if excel_cell.format is None:
                        excel_worksheet.worksheet.write(row_index, column_index, excel_cell.entry)
                    else:
                        excel_worksheet.worksheet.write(row_index, column_index, excel_cell.entry, excel_cell.format)

        for excel_worksheet in excel_worksheets:
            excel_worksheet.worksheet.autofit()
        excel_writer.close()

    def draw_graph(self, time_factor, time_interval: str, input_materials: set[Material]):
        columns = ['Machine', f'Inputs per {time_interval}', f'Outputs per {time_interval}',
                   'EU/t']
        n, q = len(columns), len(self.recipes)
        machine_names = {i: (f'{f'{"{:.2f}".format(self.machine_amounts[i])}'} {self.recipes[i].machine.__str__()} '
                             f'({self.recipes[i].voltage_tier_name})') for i in self.recipe_indices}
        recipe_vector = np.array([amount for _, amount in self.recipe_amounts.items()])
        total_material_needs = time_factor * np.matmul(self.recipe_matrix, recipe_vector)
        total_materials = list(zip(total_material_needs, self.materials.values()))

        """
        ----------------------------------------------------------------------------------------------------------------
            Draw Graph
        ----------------------------------------------------------------------------------------------------------------
        """

        node_labels = {self.materials[material_id].id: self.materials[material_id].get_abbreviation() for material_id
                       in self.hypergraph.nodes if material_id >= 0}
        node_fc = {material_id: 'grey' if material_id < 0 or total_materials[material_id][0] >= 0.0005 else 'white'
                   for material_id in self.hypergraph.nodes}
        input_nodes = set(material.id for material in input_materials)
        for i in input_nodes:
            node_fc[i] = 'green'
        pos = graded_layout(self.hypergraph, input_nodes, node_labels)
        if pos is None:
            logging.warning(f'Graded layout could not be determined.')
            xgi.draw_bipartite(self.hypergraph, node_labels=node_labels, node_size=47, node_fc=node_fc, aspect='auto')
        else:
            g = to_full_digraph(self.hypergraph)
            node_pos, edge_pos = pos
            min_x = np.min([p[0] for p in node_pos.values()] + [p[0] for p in edge_pos.values()])
            min_y = np.min([p[1] for p in node_pos.values()] + [p[1] for p in edge_pos.values()])
            shift = np.array([max(-min_x, 0), max(-min_y, 0)]) + 0.05
            combined_pos = ({f'N{n}': tuple((p + shift + 0.1 * np.random.rand(2)).tolist()) for n, p in node_pos.items()} |
                            {f'E{e}': tuple((p + shift + 0.1 * np.random.rand(2)).tolist()) for e, p in edge_pos.items()})

            horizontal_diff = max(p[0] for p in combined_pos.values()) - min(p[0] for p in combined_pos.values())
            vertical_diff = max(p[1] for p in combined_pos.values()) - min(p[1] for p in combined_pos.values())
            if vertical_diff > 0.5 * horizontal_diff:
                combined_pos = {k: p * np.array([vertical_diff / (0.5 * horizontal_diff), 1]) for k, p in combined_pos.items()}

            combined_node_labels = ({f'N{n}': self.materials[n].get_abbreviation() for n in node_pos.keys() if n >= 0} |
                                    {f'E{e}': '' for e in edge_pos.keys()})
            combined_node_size = {f'N{n}': 5 for n in node_pos.keys()} | {f'E{e}': 2 for e in edge_pos.keys()}

            node_color = {n: ('tab:blue' if n.startswith('N') else 'tab:red') for n in g.nodes}
            for e in edge_pos.keys():
                if self.machine_amounts[int(e)].is_integer():
                    node_color[f'E{e}'] = 'green'

            node_shape = {f'N{n}': 'o' for n in node_pos.keys()} | {f'E{e}': 's' for e in edge_pos.keys()}
            annotations = {f'E{e}': machine_names[int(e)] for e in edge_pos.keys()}

            plot_instance = InteractiveGraph(
                g, node_size=combined_node_size, node_color=node_color,
                node_labels=combined_node_labels, node_label_offset=0, node_label_fontdict=dict(size=20),
                edge_width=0.5, arrows=True, node_layout=combined_pos, node_edge_width=0.2, node_shape=node_shape,
                annotations=annotations, node_alpha=0.7
            )
            # xgi.draw_bipartite(
            #     self.hypergraph, node_labels=node_labels, node_size=47, node_fc=node_fc, aspect='auto', pos=pos
            # )
        plt.show()
