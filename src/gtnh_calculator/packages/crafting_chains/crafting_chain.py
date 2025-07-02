import xgi
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import numpy as np
import pandas as pd
from typing import Dict
import networkx as nx

from ..recipes.material import Material
from ..recipes.recipe import Recipe


class CraftingChain:
    hypergraph: xgi.DiHypergraph  # needs to be acyclic
    recipe_vector: np.ndarray
    recipe_matrix: np.ndarray

    def __init__(self, hypergraph: xgi.DiHypergraph, recipe_vector: np.ndarray, recipe_matrix: np.ndarray):
        self.hypergraph = hypergraph
        self.recipe_vector = recipe_vector
        self.recipe_matrix = recipe_matrix

    def draw(self, materials: Dict[int, Material], recipes, time, time_factor, time_interval_name: str):
        recipes = {i: recipe for i, recipe in recipes.items() if self.recipe_vector[i] > 0}

        # first sort the recipes topologically along the graph
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
            recipe_indices = [node for node in nx.topological_sort(graph) if isinstance(node, int)]
        else:
            recipe_indices = list(recipes.keys())

        columns = ['Machine', f'Inputs per {time_interval_name}', f'Outputs per {time_interval_name}']
        n, q = len(columns), len(recipes)
        data = np.zeros((q, n), dtype=object)
        data[:, 0] = [(f'{"{:.2f}".format(self.recipe_vector[i] * recipes[i].processing_time / time)} '
                       f'{recipes[i].machine.name} ({recipes[i].voltage_tier_name()})') for i in recipe_indices]
        data[:, 1] = [recipes[i].input_string(time_factor * self.recipe_vector[i]) for i in recipe_indices]
        data[:, 2] = [recipes[i].output_string(time_factor * self.recipe_vector[i]) for i in recipe_indices]
        df = pd.DataFrame(data=data, columns=columns)

        total_material_needs = np.matmul(self.recipe_matrix, self.recipe_vector)
        total_materials = list(zip(total_material_needs, materials.values()))

        # fig, axs = plt.subplots(nrows=2, ncols=1)
        # for ax in axs:
        #     ax.axis('off')
        # table = axs[0].table(cellText=df.values, colLabels=df.keys(), loc='center', cellLoc='center',
        #                      edges='horizontal')
        # table.auto_set_font_size(False)
        # table.set_fontsize(18)
        # table.auto_set_column_width(col=list(range(n)))
        # for (row, col), cell in table.get_celld().items():
        #     if row == 0:
        #         cell.set_text_props(fontproperties=FontProperties(weight='bold', size=18))

        node_labels = {materials[material_id].id: materials[material_id].get_abbreviation() for material_id
                       in self.hypergraph.nodes if material_id >= 0}
        node_labels[-1] = 'Start'
        node_fc = {material_id: 'white' if material_id >= 0 else 'grey' for material_id in self.hypergraph.nodes}
        xgi.draw_bipartite(self.hypergraph, node_labels=node_labels, node_size=47, node_fc=node_fc,
                           aspect='auto')
        print('\n+---------+')
        print('| Results |')
        print('+---------+\n')
        print(f'Total Inputs per {time_interval_name}:')
        print(', '.join([f'{"{:.3f}".format(-amount)} {material}' for amount, material in total_materials if amount < 0]) + '\n')
        print(f'Total Outputs per {time_interval_name}:')
        print(', '.join([f'{"{:.3f}".format(amount)} {material}' for amount, material in total_materials if amount > 0]) + '\n')
        print('Complete Recipe List:')
        print(df.to_string() + '\n')
        plt.show()
