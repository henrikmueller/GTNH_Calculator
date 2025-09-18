import logging

import xgi
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from typing import Dict
import networkx as nx
from netgraph import InteractiveGraph

from ..recipes.material import Material
from ..recipes.recipe import Recipe
from ..graphs.graded_layout import graded_layout
from ..graphs.graph_conversion import to_full_digraph


class CraftingChain:
    hypergraph: xgi.DiHypergraph
    recipe_amounts: Dict[int, float]
    recipe_matrix: np.ndarray

    def __init__(self, hypergraph: xgi.DiHypergraph, recipe_amounts: Dict[int, float], recipe_matrix: np.ndarray):
        self.hypergraph = hypergraph
        self.recipe_amounts = recipe_amounts
        self.recipe_matrix = recipe_matrix

    def draw(self, materials: Dict[int, Material], recipes: Dict[int, Recipe], time, time_factor,
             time_interval_name: str, input_materials: set[Material]):
        recipes = {i: recipe for i, recipe in recipes.items() if self.recipe_amounts[i] > 0}

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

        columns = ['Machine', f'Inputs per {time_interval_name}', f'Outputs per {time_interval_name}',
                   'EU/t']
        eu = materials[0]
        n, q = len(columns), len(recipes)
        machine_amounts = {i: self.recipe_amounts[i] * recipes[i].processing_time / time for i in recipe_indices}
        machine_names = {i: (f'{f'{"{:.2f}".format(machine_amounts[i])}'} {recipes[i].machine.name} '
                             f'({recipes[i].voltage_tier_name})') for i in recipe_indices}
        data = np.zeros((q, n), dtype=object)
        data[:, 0] = [machine_names[i] for i in recipe_indices]
        data[:, 1] = [recipes[i].input_string(time_factor * self.recipe_amounts[i]) for i in recipe_indices]
        data[:, 2] = [recipes[i].output_string(time_factor * self.recipe_amounts[i]) for i in recipe_indices]
        data[:, 3] = [-recipes[i].materials[eu] * machine_amounts[i] / (20 * recipes[i].processing_time)
                      if recipes[i].processing_time > 0 else 0 for i in recipe_indices]
        df = pd.DataFrame(data=data, columns=columns)

        recipe_vector = np.array([amount for _, amount in self.recipe_amounts.items()])
        total_material_needs = time_factor * np.matmul(self.recipe_matrix, recipe_vector)
        total_materials = list(zip(total_material_needs, materials.values()))

        node_labels = {materials[material_id].id: materials[material_id].get_abbreviation() for material_id
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

            combined_node_labels = ({f'N{n}': materials[n].get_abbreviation() for n in node_pos.keys() if n >= 0} |
                                    {f'E{e}': '' for e in edge_pos.keys()})
            combined_node_size = {f'N{n}': 5 for n in node_pos.keys()} | {f'E{e}': 2 for e in edge_pos.keys()}

            node_color = {n: ('tab:blue' if n.startswith('N') else 'tab:red') for n in g.nodes}
            for e in edge_pos.keys():
                if machine_amounts[int(e)].is_integer():
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

        print(f'\nTotal Inputs per {time_interval_name}:')
        print(', '.join([f'{"{:.3f}".format(-amount)} {material}' for amount, material in total_materials if amount < 0]) + '\n')
        print(f'Total Outputs per {time_interval_name}:')
        print(', '.join([f'{"{:.3f}".format(amount)} {material}' for amount, material in total_materials if amount > 0]) + '\n')
        print(f'Complete Recipe List{' (ordered)' if nx.is_directed_acyclic_graph(graph) else ''}:')
        print(df.to_string() + '\n')
        plt.show()
