import networkx as nx
import xgi
from typing import Dict, Any
import numpy as np
import matplotlib.pyplot as plt

from .graph_conversion import to_digraph


def graded_node_position(g: nx.DiGraph, input_nodes: set[int], node_labels: Dict[int, str], debug=False)\
        -> Dict[str, list[Any]] | None:
    if debug:
        pos = nx.spring_layout(g)
        nx.draw(g, pos=pos)
        nx.draw_networkx_labels(g, pos=pos, labels=node_labels, font_color="black")
        plt.show()

    layers = {}
    if len(g.nodes) <= 0:
        return layers

    first_layer = set([n for n in g.nodes if g.in_degree(n) == 0])
    first_layer = list(first_layer.union(input_nodes.intersection(g.nodes)))
    layers['0'] = first_layer
    visited_nodes = first_layer.copy()
    current_layer = 1
    while True:
        layer = [n for n in g.nodes if n not in visited_nodes and any(p in visited_nodes for p in g.predecessors(n))]
        visited_nodes += layer
        if not layer:
            break
        layers[str(current_layer)] = layer
        current_layer += 1

    other = set(g.nodes).difference(set(visited_nodes))
    if other:
        print(f'Remaining Nodes: {[node_labels[n] for n in other]}')
        return None

    # for i, layer in layers.items():
    #     print(f'{i}: {[node_labels[n] if n in node_labels.keys() else '???' for n in layer]}')
    return layers


def graded_layout(dh: xgi.DiHypergraph, input_nodes, node_labels)\
        -> tuple[Dict[str, np.ndarray], Dict[str, np.ndarray]] | None:
    g = to_digraph(dh)
    subset_key = graded_node_position(g, input_nodes, node_labels)
    if subset_key is None:
        return None

    node_pos: Dict[Any, np.ndarray] = nx.multipartite_layout(
        g, subset_key=subset_key
    )
    edge_pos = {}
    for e in dh.edges:
        neighbors = dh.edges.tail(e).union(dh.edges.head(e))
        array = np.stack([node_pos[n] for n in neighbors], axis=1)
        edge_pos[e] = np.mean(array, axis=1)
    return node_pos, edge_pos
