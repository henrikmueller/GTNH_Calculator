import pytest
from frozendict import frozendict

from packages.recipes_db.behaviours.machine_behaviours import FittingContext
from packages.recipes_db.machine_stats import MachineStatType
from packages.recipes_db.material import MaterialGroup
from packages.recipes_db.recipe_options import RecipeOptions, RecipeOptionType
from packages.recipes_db.voltage_tiers import VoltageTier
from packages.recipes_db.machine_options.machine_option_types import MachineOptionType
from utility.helper_functions import *


@pytest.mark.parametrize("voltage_tier", [
    (1), (2), (3), (4), (5), (6), (7), (8), (9)
])
def test_fit_recipe_scales_by_voltage_tier(voltage_tier: int):
    """
    Tested on Hydrofluoric Acid in Large Chemical Reactor
    """
    behaviour = default_behaviour()
    g = MaterialGroup([get_test_material("Material 1")])
    m2 = get_test_material("Material 2")
    raw = raw_recipe(
        eu_per_tick=-8,
        processing_time=3,
        voltage_tier=VoltageTier.LV,
        inputs={g: -1000.0},
        output_specifications={0: (m2, 1000.0, 1.0)}
    )

    out = behaviour.fit_recipe(FittingContext(
        raw_recipe=raw,
        voltage_tier=voltage_tier,
        machine_stats=machine_stats(voltage_tiers=(voltage_tier,)),
        machine_options=empty_machine_options(),
    ))
    assert out is not None
    assert out.eu_per_tick == pytest.approx(-8 * 4**(voltage_tier - 1))
    assert out.processing_time == pytest.approx(3 / 2**(voltage_tier - 1))
    assert raw.inputs[g] == -1000.0
    _, amount, prob = out.output_specifications[0]
    assert amount == 1000.0
    assert prob == 1.0


@pytest.mark.parametrize("voltage_tier", [
    (3), (4), (5), (6), (7), (8), (9), (10)
])
def test_fit_recipe_scales_by_voltage_tier_lcr(voltage_tier: int):
    """
    Tested on Oxalic Acid in Large Chemical Reactor
    """
    behaviour = large_chemical_reactor_behaviour()
    g = MaterialGroup([get_test_material("Material 1")])
    m2 = get_test_material("Material 2")
    raw = raw_recipe(
        eu_per_tick=-240,
        processing_time=202.5,
        voltage_tier=VoltageTier.HV,
        inputs={g: -9000.0},
        output_specifications={0: (m2, 9000.0, 1.0)}
    )

    out = behaviour.fit_recipe(FittingContext(
        raw,
        voltage_tier=voltage_tier,
        machine_stats=machine_stats(voltage_tiers=tuple(VoltageTier.voltage_tiers_int())),
        machine_options=empty_machine_options(),
    ))
    assert out is not None
    assert out.eu_per_tick == pytest.approx(-240 * 4**(voltage_tier - 3))
    assert out.processing_time == pytest.approx(202.5 / 4**(voltage_tier - 3))
    assert raw.inputs[g] == -9000.0
    _, amount, prob = out.output_specifications[0]
    assert amount == 9000.0
    assert prob == 1.0


@pytest.mark.parametrize("voltage_tier, expected_eu_per_tick, expected_processing_time, expected_parallels", [
    (1, -27, 100 / 2.8, 1),
    (2, -27 * 4, 100 / 2.8, 4),
    (3, -27 * 6, 100 / 2.8, 6),
    (4, -27 * 8 * 4, 100 / 2.8 / 2, 8)
])
def test_fit_recipe_scales_by_voltage_tier_industrial_electrolyzer(
    voltage_tier: int, expected_eu_per_tick: float, expected_processing_time: float, expected_parallels: int
):
    """
    Tested on electrolyzing water in Industrial Electrolyzer
    """
    behaviour = industrial_electrolyzer_behaviour()
    g = MaterialGroup([get_test_material("Material 1")])
    m2 = get_test_material("Material 2")
    raw = raw_recipe(
        eu_per_tick=-30,
        processing_time=100,
        voltage_tier=VoltageTier.LV,
        inputs={g: -1000.0},
        output_specifications={0: (m2, 1000.0, 1.0)}
    )

    out = behaviour.fit_recipe(FittingContext(
        raw_recipe=raw,
        voltage_tier=voltage_tier,
        machine_stats=machine_stats(voltage_tiers=tuple(VoltageTier.voltage_tiers_int())),
        machine_options=empty_machine_options(),
    ))
    assert out is not None
    assert out.eu_per_tick == pytest.approx(expected_eu_per_tick)
    assert out.processing_time == pytest.approx(expected_processing_time)
    assert out.used_parallels == expected_parallels
    assert out.inputs[g] == -1000.0 * expected_parallels
    _, amount, prob = out.output_specifications[0]
    assert amount == 1000.0 * expected_parallels
    assert prob == 1.0


@pytest.mark.parametrize(
    "voltage_tier, coil_temperature, coil_tier, expected_eu_per_tick, expected_processing_time, expected_parallels", 
    [
    (4, 3601, 3, -1920, 625, 1),
    (4, 4501, 4, -1920 * 0.95, 625, 1),
    (5, 3601, 3, -1920 * 4 * 0.95, 625, 4),
    (5, 4501, 4, -1920 * 4 * 0.95**2, 625, 4),
    (6, 3601, 3, -1920 * 17 * 0.95, 625, 17),
    (6, 4501, 4, -1920 * 18 * 0.95**2, 625, 18),
    (7, 4501, 4, -1920 * 75 * 0.95**2, 625, 75),
    (8, 4501, 4, -1920 * 256 * 0.95**2, 625, 256),
    (8, 9001, 9, -1920 * 256 * 0.95**7, 625, 256),
    (9, 9001, 9, -1920 * 1024 * 0.95**7, 625 / 4, 256),
])
def test_fit_recipe_scales_by_voltage_tier_mega_ebf(
    voltage_tier: int, coil_temperature: float, coil_tier: int, 
    expected_eu_per_tick: float, expected_processing_time: float, expected_parallels: int
):
    """
    Tested on Hot Tungsten Ingots in the Mega EBF
    """
    behaviour = mega_ebf_behaviour()
    g = MaterialGroup([get_test_material("Material 1")])
    m2 = get_test_material("Material 2")
    raw = raw_recipe(
        eu_per_tick=-1920,
        processing_time=625,
        voltage_tier=VoltageTier.EV,
        inputs={g: -1.0},
        output_specifications={0: (m2, 1.0, 1.0)},
        recipe_options=RecipeOptions(frozendict({RecipeOptionType.COIL_HEAT: 3000.0}))
    )

    out = behaviour.fit_recipe(FittingContext(
        raw_recipe=raw,
        voltage_tier=voltage_tier,
        machine_stats=machine_stats(voltage_tiers=tuple(VoltageTier.voltage_tiers_int())),
        machine_options=coil_only_machine_options(temperature=coil_temperature, tier=coil_tier),
    ))
    assert out is not None
    assert out.eu_per_tick == pytest.approx(expected_eu_per_tick)
    assert out.processing_time == pytest.approx(expected_processing_time)
    assert out.used_parallels == expected_parallels
    assert out.inputs[g] == -1.0 * expected_parallels
    _, amount, prob = out.output_specifications[0]
    assert amount == 1.0 * expected_parallels
    assert prob == 1.0


@pytest.mark.parametrize(
    "voltage_tier, coil_temperature, coil_tier, expected_eu_per_tick, expected_processing_time", 
    [
    (2, 1801, 1, -64, 64),
    (2, 2701, 2, -64, 32),
    (3, 1801, 1, -64 * 4, 32),
    (4, 5401, 5, -64 * 16, 32 / 4 / 2.5),
])
def test_fit_recipe_scales_by_voltage_tier_pyrolyse_oven(
    voltage_tier: int, coil_temperature: float, coil_tier: int, 
    expected_eu_per_tick: float, expected_processing_time: float
):
    """
    Tested on Wood Tar in the Pyrolyse Oven
    """
    behaviour = pyrolyse_oven_behaviour()
    g = MaterialGroup([get_test_material("Material 1")])
    m2 = get_test_material("Material 2")
    raw = raw_recipe(
        eu_per_tick=-64,
        processing_time=32,
        voltage_tier=VoltageTier.MV,
        inputs={g: -16.0},
        output_specifications={0: (m2, 1500.0, 1.0)}
    )

    out = behaviour.fit_recipe(FittingContext(
        raw_recipe=raw,
        voltage_tier=voltage_tier,
        machine_stats=machine_stats(voltage_tiers=tuple(VoltageTier.voltage_tiers_int())),
        machine_options=coil_only_machine_options(temperature=coil_temperature, tier=coil_tier),
    ))
    assert out is not None
    assert out.eu_per_tick == pytest.approx(expected_eu_per_tick)
    assert out.processing_time == pytest.approx(expected_processing_time)
    assert out.used_parallels == 1
    assert out.inputs[g] == -16.0
    _, amount, prob = out.output_specifications[0]
    assert amount == 1500.0
    assert prob == 1.0


@pytest.mark.parametrize(
    "voltage_tier, coil_temperature, coil_tier, expected_eu_per_tick, expected_processing_time", 
    [
    (3, 1801, 1, -240 * 0.9, 1),
    (3, 3601, 3, -240 * 0.7, 1),
    (3, 7201, 7, -240 * 0.5 * 4, 1 / 2),
    (5, 3601, 3, -240 * 0.7 * 16, 1 / 4),
])
def test_fit_recipe_scales_by_voltage_tier_oil_cracker(
    voltage_tier: int, coil_temperature: float, coil_tier: int, 
    expected_eu_per_tick: float, expected_processing_time: float
):
    """
    Tested on Lightly Hydro-Cracked Refinery Gas in the Oil Cracker
    """
    behaviour = oil_cracker_behaviour()
    g = MaterialGroup([get_test_material("Material 1")])
    m2 = get_test_material("Material 2")
    raw = raw_recipe(
        eu_per_tick=-240,
        processing_time=1,
        voltage_tier=VoltageTier.HV,
        inputs={g: -1000.0},
        output_specifications={0: (m2, 1000.0, 1.0)}
    )

    out = behaviour.fit_recipe(FittingContext(
        raw_recipe=raw,
        voltage_tier=voltage_tier,
        machine_stats=machine_stats(voltage_tiers=tuple(VoltageTier.voltage_tiers_int())),
        machine_options=coil_only_machine_options(temperature=coil_temperature, tier=coil_tier),
    ))
    assert out is not None
    assert out.eu_per_tick == pytest.approx(expected_eu_per_tick)
    assert out.processing_time == pytest.approx(expected_processing_time)
    assert out.used_parallels == 1
    assert out.inputs[g] == -1000.0
    _, amount, prob = out.output_specifications[0]
    assert amount == 1000.0
    assert prob == 1.0


@pytest.mark.parametrize(
    "voltage_tier, fusion_mk, expected_eu_per_tick, expected_processing_time", 
    [
    (5, 1, -8192, 0.4),
    (6, 1, -8192, 0.4),
    (5, 2, -8192, 0.4),
    (8, 2, -8192 * 4, 0.4 / 2),
    (8, 3, -8192 * 16, 0.4 / 4),
    (8, 4, -8192 * 64, 0.4 / 64),
    (8, 5, -8192 * 64, 0.4 / 64),
    (9, 5, -8192 * 256, 0.4 / 256),
])
def test_fit_recipe_scales_by_voltage_tier_fusion(
    voltage_tier: int, fusion_mk: int, expected_eu_per_tick: float, expected_processing_time: float
):
    """
    Tested on Helium Plasma in the Fusion Reactor
    """
    behaviour = fusion_reactor_behaviour(fusion_mk)
    g = MaterialGroup([get_test_material("Material 1")])
    m2 = get_test_material("Material 2")
    raw = raw_recipe(
        eu_per_tick=-8192,
        processing_time=0.4,
        voltage_tier=VoltageTier.IV,
        inputs={g: -125.0},
        output_specifications={0: (m2, 125.0, 1.0)},
        recipe_options=RecipeOptions(frozendict({RecipeOptionType.FUSION_TIER: 1}))
    )

    out = behaviour.fit_recipe(FittingContext(
        raw_recipe=raw,
        voltage_tier=voltage_tier,
        machine_stats=machine_stats(
            voltage_tiers=tuple(VoltageTier.voltage_tiers_int()), 
            additional_stats={MachineStatType.FUSION_TIER: fusion_mk}
            ),
        machine_options=empty_machine_options()
    ))
    assert out is not None
    assert out.eu_per_tick == pytest.approx(expected_eu_per_tick)
    assert out.processing_time == pytest.approx(expected_processing_time)
    assert out.used_parallels == 1
    assert out.inputs[g] == -125.0
    _, amount, prob = out.output_specifications[0]
    assert amount == 125.0
    assert prob == 1.0


@pytest.mark.parametrize(
    "voltage_tier, containment_block_tier, expected_eu_per_tick, expected_processing_time, expected_parallels", 
    [
    (10, 1, -7864320, 0.05, 1),
    (10, 3, -7864320, 0.05, 1),
    (11, 2, -7864320 * 4, 0.05, 4),
    (11, 4, -7864320 * 4, 0.05, 4),
    (12, 2, -7864320 * 16, 0.05 / 2, 4),
    (12, 3, -7864320 * 16, 0.05, 16),
    (12, 4, -7864320 * 17, 0.05, 17),
])
def test_fit_recipe_scales_by_voltage_tier_eic(
    voltage_tier: int, containment_block_tier: int, expected_eu_per_tick: float, expected_processing_time: float, 
    expected_parallels: int
):
    """
    Tested on Compressed Dual Aluminium in the Electric Implosion Compressor
    """
    behaviour = eic_behaviour()
    g = MaterialGroup([get_test_material("Material 1")])
    m2 = get_test_material("Material 2")
    raw = raw_recipe(
        eu_per_tick=-7864320,
        processing_time=0.05,
        voltage_tier=VoltageTier.UEV,
        inputs={g: -2.0},
        output_specifications={0: (m2, 1.0, 1.0)}
    )

    out = behaviour.fit_recipe(FittingContext(
        raw_recipe=raw,
        voltage_tier=voltage_tier,
        machine_stats=machine_stats(
            voltage_tiers=tuple(VoltageTier.voltage_tiers_int()),
            ),
        machine_options=machine_options_for_test(
        (
            MachineOptionType.CONTAINMENT_BLOCK,
            machine_option(MachineOptionType.CONTAINMENT_BLOCK, tier=containment_block_tier),
        ),
    )
    ))
    assert out is not None
    assert out.eu_per_tick == pytest.approx(expected_eu_per_tick)
    assert out.processing_time == pytest.approx(expected_processing_time)
    assert out.used_parallels == expected_parallels
    assert out.inputs[g] == -2.0 * expected_parallels
    _, amount, prob = out.output_specifications[0]
    assert amount == 1.0 * expected_parallels
    assert prob == 1.0


# CURRENT: Large Fluid Extractor


def test_fit_recipe_scales_by_used_parallels():
    behaviour = default_behaviour()
    g = MaterialGroup([get_test_material("Material 1")])
    m2 = get_test_material("Material 2")
    raw = raw_recipe(
        eu_per_tick=-8,
        processing_time=3,
        voltage_tier=VoltageTier.LV,
        inputs={g: -1.0},
        output_specifications={0: (m2, 1.0, 1.0)}
    )

    out = behaviour.fit_recipe(FittingContext(
        raw_recipe=raw,
        voltage_tier=VoltageTier.LV,
        machine_stats=machine_stats(voltage_tiers=(VoltageTier.LV,)),
        machine_options=empty_machine_options(),
    ))
    assert out is not None
    assert out.used_parallels >= 1
    assert out.inputs[g] == pytest.approx(raw.inputs[g] * out.used_parallels)
    _, amount, prob = out.output_specifications[0]
    assert amount == pytest.approx(1.0 * out.used_parallels)
    assert prob == 1.0
