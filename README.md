# GTNH Calculator

A calculator and optimizer for production chains in the well-known [GregTech: New Horizons](https://www.gtnewhorizons.com/) (GTNH) modpack (Version 2.8.0). The underlying database is directly extracted from the game using the [NESQL Exporter](https://github.com/ShadowTheAge/nesql-exporter).

Link to the tool: https://gtnhcalculator.streamlit.app/

_Note_: This project is still work in progress.

## Overview

- Recipe and material data is stored in a SQLite database. Due to over 200,000 recipes, the aggregation process may take up to 30 seconds depending on the hardware.
- Existing materials and recipes can be explored in their respective tabs on the website. Changing the machine, the voltage tier or any machine-specific options like coils or pipe casings correctly influences the properties of the recipes.
- In the Crafting Chain Calculator tab, one can specify inputs, outputs and other options for a production chain using a config file in yaml format (template will follow). The tool then returns a _mathematically optimal production chain_ by leveraging the [HiGHS](https://highs.dev/) optimizer for sparse matrices.

## Local installation

To install this project and the required libraries, the following steps are required:
1. Clone the repository.
2. Install all packages via `poetry install`. (To install the venv in the project folder, use `poetry config virtualenvs.in-project true` in advance.)

## Config file

1. Specify **input and output materials** along possible constraints.
2. Edit the `time` variable. It is a string starting with an integer and ending in either 's' or 't' (for seconds of ticks). 
The time variable defines the amount of time, in which the output materials are to be produced.
3. Edit the `time_interval` variable. It needs to be formatted in the same way as the `time` variable, but has no influence on the calculation itself, only on the displayed information about the production chain at the end. All materials in this production chain are displayed in the form "x per time interval" (usually, x/tick oder x/second).
4. Associate weights to materials to prioritize some materials over others. Input materials should have negative
weights, output materials should have positive weights. Every non-infinite input and output material should be
assigned a weight.
5. Note: All materials in the `infinite_materials` set are automatically included as inputs with weight 0.
6. Additional constraints can be specified under `restrictions`.

## Planned features

- Multi-objective optimization to weigh production chain outputs against total energy consumption and complexity of the factory (number and size of machines) and allow the user to compare different production chains (i.e. points on the Pareto front).
- Automatically select machines with parallel mode if the number of machines for one recipe grows too large.
