import networkx as nx
import xgi
from typing import Dict, Any
import matplotlib.pyplot as plt


def to_digraph(dh: xgi.DiHypergraph) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(dh.nodes)
    for e in dh.edges:
        tails, heads = dh.edges.tail(e), dh.edges.head(e)
        g.add_edges_from([(t, h) for t in tails for h in heads if t != h])
    return g


def to_full_digraph(dh: xgi.DiHypergraph) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(f'N{n}' for n in dh.nodes)
    g.add_nodes_from(f'E{e}' for e in dh.edges)
    for e in dh.edges:
        tails, heads = dh.edges.tail(e), dh.edges.head(e)
        g.add_edges_from([(f'N{t}', f'E{e}') for t in tails])
        g.add_edges_from([(f'E{e}', f'N{h}') for h in heads])
    return g