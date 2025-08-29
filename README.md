# GTNH: Recipe Calculator
## Installation

To install this project and the required libraries, the following steps are required:
1. Clone the repository.
2. Install all packages via ```poetry install```. (To install the venv in the project folder, use ```poetry config virtualenvs.in-project true``` in advance.)

## Usage

1. Specify **input and output materials** in the main.py file.
2. Edit the ```time``` variable. It is a string starting with an integer and ending in either 's' or 't' (for seconds of ticks). 
The time variable defines the amount of time, in which the output materials are to be produced.
3. Edit the ```time_interval``` variable. It needs to be formatted in the same way as the ```time``` variable, but has no influence
on the calculation itself, only one the displayed information about the recipe chain at the end. All materials in this
recipe chain are displayed in the form "x per time interval" (usually, x/tick oder x/second).
4. Associate **weights to materials** to prioritize some materials over others. Input materials should have negative
weights, output materials should have positive weights. Every non-infinite input and output material should be
assigned a weight.
5. Note: All materials in the ```infinite_materials``` set are automatically included as inputs with weight 0.
6. Adapt the ```recipe_weight_factor``` variable to emphasize material costs or machine costs (higher ```recipe_weight_factor``` means more emphasis on machine costs).
7. To each material one can also assign a **upper bound** via the `material_weights` dictionary. If `None` is inserted as
an upper bound, then no upper bound is set.
8. The ```mode``` variable must be one of the following: `Fixed_Input` or `Fixed_Output`. In the former case, there can
be only one input material (excluding infinite materials) and the `fixed_amount` variable specifies the amount of this
input material. In the latter case, there can be only one output material and the `fixed_amount` variable specifies the 
amount of this output material. 
9. The script then displays the complete optimal recipe chain under the specified constraints.

## Adding Recipes

Recipes are stored in the following Google Sheet: https://docs.google.com/spreadsheets/d/1OSog0iIKua5T7ms0Iv9OZxCR1Qw45QSPtZd7EDP-FK4/edit?usp=sharing
Here one can (currently) also define **upper bound on the number of machines** for each recipe (via the column 
`Machine Cap`) and specify, whether a **multiblock** should be used for the recipe (Simply insert the voltage tier of 
the multiblock in the `Parallel Voltage` column). 
