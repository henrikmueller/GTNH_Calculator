# GTNH: Recipe Calculator
## Installation

To install this project and the required libraries, the following steps are required:
1. Clone the repository.
2. Install all packages via ```poetry install```. (To install the venv in the project folder, use ```poetry config virtualenvs.in-project true``` in advance.)

## Usage

1. Specify input and output materials in the main.py file.
2. Edit the ```time``` variable. It is a string starting with an integer and ending in either 's' or 't' (for seconds of ticks). 
The time variable defines the amount of time, in which the output materials are to be produced.
3. Edit the ```time_interval``` variable. It needs to be formatted in the same way as the ```time``` variable, but has no influence
on the calculation itself, only one the displayed information about the recipe chain at the end. All materials in this
recipe chain are displayed in the form "x per time interval" (usually, x/tick oder x/second).
4. Associate weights to the input materials.
5. All materials in the ```infinite_materials``` set are automatically included as inputs with weight 0.
6. The script then displays the complete optimal recipe chain under the specified constraints. If the optimization problem

## Adding Recipes

Recipes are stored in the following Google Sheet: https://docs.google.com/spreadsheets/d/1OSog0iIKua5T7ms0Iv9OZxCR1Qw45QSPtZd7EDP-FK4/edit?usp=sharing

