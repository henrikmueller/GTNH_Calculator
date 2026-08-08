import numpy as np
import pytest

from packages.recipes_db.behaviours.capacity_utilization_behaviour import DefaultCapacityUtilizationBehaviour
from packages.recipes_db.behaviours.machine_behaviours import FittingContext
from packages.recipes_db.material import MaterialGroup
from packages.recipes_db.voltage_tiers import VoltageTier
from utility.helper_functions import *

@pytest.mark.parametrize(
    "voltage_tier, capacity_utilization, processing_time, min_total_eu, max_total_eu, throughput",
    [
    (2, 1, 90, -120 * 20 * 90, -120 * 20 * 90, 1),
    (3, 1, 90, -480 * 20 * 90, -480 * 20 * 90, 4),
    (3, 0.5, 90, -240 * 20 * 90, -480 * 20 * 90, 2),
    (3, 0.25, 90, -120 * 20 * 90, -480 * 20 * 45, 1),
    (3, 0, 90, 0, 0, 0),
    (3, 2, 90, -480 * 20 * 90 * 2, -480 * 20 * 90 * 2, 8),
    (3, 1.5, 90, -480 * 20 * 90 * 1.5, -480 * 20 * 90 * 2, 6),
    (3, 1.25, 90, -480 * 20 * 90 * 1.25, -480 * 20 * 90 * 2, 5),
    (3, 1.2, 90, -480 * 20 * 90 * 1.2, -480 * 20 * 90 * 2, 4.8),
    (3, 1.75, 90, -480 * 20 * 90 * 1.75, -480 * 20 * 90 * 2, 7),
    (6, 0.25, 90, -120 * 20 * 90 * 64, -120 * 20 * 90 * 256 * 0.2 - 120 * 256 * 20 * 90 * 0.8, 64),
])
def test_fit_to_capacity_utilization_mega_vacuum_freezer(
    voltage_tier, capacity_utilization, processing_time, min_total_eu, max_total_eu, throughput
):
    behaviour = mega_vacuum_freezer_behaviour()
    material_group = MaterialGroup([get_test_material("Helium")])
    output_material = get_test_material("Liquid Helium")
    base_recipe = raw_recipe(
        eu_per_tick=-120,
        processing_time=90,
        voltage_tier=VoltageTier.MV,
        inputs={material_group: -1000.0},
        output_specifications={0: (output_material, 1000.0, 1.0)}
    )
    fitting_context = FittingContext(
        raw_recipe=base_recipe,
        voltage_tier=voltage_tier,
        machine_stats=machine_stats(voltage_tiers=tuple(VoltageTier.voltage_tiers_int())),
        machine_options=empty_machine_options(),
    )
    adapted_recipe = behaviour.fit_recipe(fitting_context=fitting_context)
    assert adapted_recipe is not None

    capacity_behaviour = DefaultCapacityUtilizationBehaviour()
    partially_utilized = capacity_behaviour.fit_to_capacity_utilization(
        adapted_recipe=adapted_recipe,
        capacity_utilization=capacity_utilization,
        machine_behaviour=behaviour,
        fitting_context=fitting_context,
        log=True
    )

    assert partially_utilized.processing_time == pytest.approx(processing_time)
    assert partially_utilized.min_total_eu == pytest.approx(min_total_eu)
    assert partially_utilized.max_total_eu == pytest.approx(max_total_eu)
    assert_approximate_dict_equality(
        partially_utilized.average_inputs, {g: throughput * a for g, a in base_recipe.inputs.items()})
    assert_approximate_dict_equality(
        partially_utilized.average_outputs, {g: throughput * a for g, a in base_recipe.output_dict.items()})
