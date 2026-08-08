from dataclasses import dataclass


# Constants for the complete project
COMMENT_CHARACTER = "#"
GT_EU_KEY = 'i~gregtech~gt.eu'
GT_EU_DICT_KEY = 'EU'
INCLUDE_DEPRECATED_MACHINES = False
DEFAULT_MACHINE_LIMIT = 1000
FLUID_WEIGHT_FACTOR = 1 / 250  # between 1 / 144 and 1 / 1000

STARTING_MATERIAL_NAMES = [
    'Acacia Log', 'Dark Oak Log', 'Oak Log', 'Spruce Log', 'Birch Log', 'Jungle Log', 'Pine Log',
    'Water', 'Flint', 'Dirt', 'Gravel', 'Sand', 'Cobblestone', 'Stone', 'Netherrack',
    'Sandstone', 'Soul Sand', 'Clay', 'Gunpowder', 'Terracotta', 'Leather', 'Nether Bricks',
    'Rubber Wood', 'Mortar', 'Wrench', 'File', 'Screwdriver', 'Wire Cutter', 'Hammer',
    'Soldering Iron (LV)', 'Crowbar', 'Soft Mallet', 'Saw', 'Diamond', 'Knife', 'Emerald', 'Bronze Ingot',
    'Slimeball', 'Coangulated Blood', 'Sugar Canes', 'Wheat Seeds', 'Wheat', 'Water Bucket', 'Water Clay Bucket',
    'Lava Bucket', 'Lava Clay Bucket', 'Redstone Dust', 'Steam Alloy Smelter', 'Steam Macerator',
    'Steam Compressor', 'Steam Forge Hammer', 'Steam Extractor'
]


@dataclass(frozen=True)
class ExampleFile:
    key: str
    name: str
    yaml_path: str
    description: str
    

EXAMPLE_FILES = [
    ExampleFile(
        key='hog',
        name='High Octane Gasoline',
        yaml_path='config/fixed_examples/config_hog_example.yaml',
        description=f'''Uses _Oil Combs_ from Forestry and _Spruce Logs_ to produce _High Octane Gasoline_. 
        The config file specifies that the crafting chain should be optimized for maximal Gasoline output, while 
        adhering to the specified material constraints.
        '''
    ),
    ExampleFile(
        key='plat_line',
        name='Platinum Line',
        yaml_path='config/fixed_examples/config_plat_line_example.yaml',
        description=f'''Extracts several elements from _Platinum Metallic Powder Dust_ via Sieving, Electrolysis, 
        Leaching, Pyrometallurgy, Solvent extraction and other processes: _Platinum_, _Rhodium_, _Ruthenium_, _Palladium_, 
        _Iridium_ and _Osmium_. The config file specifies that the crafting chain should be optimized for the unweighted 
        sum of all outputs, while adhering to the specified material constraints.
        '''
    )
]
