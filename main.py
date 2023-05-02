import random
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Tuple, Dict

import mosaik
from mosaik.util import connect_many_to_one

from simulator.power_meter import PhysicalPowerMeter, AwsPowerMeter, LinearPowerModel

sim_config = {
    "CSV": {
        "python": "mosaik_csv:CSV",
    },
    "Grid": {"python": "mosaik_pandapower.simulator:Pandapower"},
    "ComputingSystemSim": {
        "python": "simulator.computing_system:ComputingSystemSim",
    },
    "Collector": {
        "python": "simulator.collector:Collector",
    },
    "SolarController": {
        "python": "simulator.solar_controller:SolarController",
    },
    "CarbonController": {
        "python": "simulator.carbon_controller:CarbonController",
    },
    "VirtualEnergySystem": {
        "python": "simulator.virtual_energy_system:VirtualEnergySystem",
    },
}

sim_args = {
    "START": "2014-01-01 00:00:20",
    "END": 300,  # 30 * 24 * 3600  # 10 days
    "GRID_FILE": "data/custom.json",  # "data/custom.json"  # 'data/demo_lv_grid.json'
    "SOLAR_DATA": "data/pv_10kw.csv",
    "CARBON_DATA": "data/ger_ci_testing.csv",
    "BATTERY_MIN_SOC": 0.6,
    "BATTERY_CAPACITY": 10 * 5 * 3600,  # 10Ah * 5V * 3600 := Ws
    "BATTERY_INITIAL_CHARGE_LEVEL": 0.7,
    "BATTERY_C_RATE": 0.2,
}


def main(simulation_args):
    random.seed(23)
    world = mosaik.World(sim_config)  # type: ignore
    create_scenario_simple(world, simulation_args)
    world.run(until=simulation_args["END"], print_progress=False, rt_factor=1)


def create_scenario_simple(world, simulation_args):
    # computing_system_sim = world.start('ComputingSystemSim')
    # aws_power_meter = AwsPowerMeter(instance_id="instance_id", power_model=LinearPowerModel(p_static=30, p_max=150))
    # raspi_power_meter = PhysicalPowerMeter()
    # computing_system = computing_system_sim.ComputingSystem(power_meters=[raspi_power_meter])

    # Carbon Sim from CSV dataset
    carbon_sim = world.start(
        "CSV",
        sim_start=simulation_args["START"],
        datafile=simulation_args["CARBON_DATA"],
    )
    carbon = carbon_sim.CarbonIntensity.create(1)[0]

    # Carbon Controller acts as a medium between carbon module and VES or
    # direct consumer since producer is only a CSV generator.
    carbon_controller = world.start("CarbonController")
    carbon_agent = carbon_controller.CarbonAgent()

    # Solar Sim from CSV dataset
    solar_sim = world.start(
        "CSV",
        sim_start=simulation_args["START"],
        datafile=simulation_args["SOLAR_DATA"],
    )
    solar = solar_sim.PV.create(1)[0]

    # Solar Controller acts as medium between Solar module and VES or direct consumer
    # since producer is only a csv generator.
    solar_controller = world.start("SolarController")
    solar_agent = solar_controller.SolarAgent()

    # VES Sim
    virtual_energy_system_sim = world.start("VirtualEnergySystem")
    virtual_energy_system = virtual_energy_system_sim.VirtualEnergySystemModel(
        battery_capacity=simulation_args["BATTERY_CAPACITY"],
        battery_soc=simulation_args["BATTERY_INITIAL_CHARGE_LEVEL"]
        * simulation_args["BATTERY_CAPACITY"],
        battery_min_soc=simulation_args["BATTERY_MIN_SOC"],
        battery_c_rate=simulation_args["BATTERY_C_RATE"],
    )

    # gridsim = world.start('Grid', step_size=60)
    # buses = filter(lambda e: e.type == 'PQBus', grid)
    # buses = {b.eid.split('-')[1]: b for b in buses}
    # world.connect(consumer, buses["node_a1"], ('P_out', 'P'))
    # world.connect(pvs[0], [e for e in grid if 'node' in e.eid][0], 'P')
    # nodes = [e for e in grid if e.type in ('RefBus, PQBus')]
    # load = [e for e in grid if e.eid == "0-load"][0]
    # ext_grid = [e for e in grid if e.type == "Ext_grid"][0]
    # lines = [e for e in grid if e.type == "Line"]

    collector = world.start("Collector")
    monitor = collector.Monitor()

    # Connect entities
    # world.connect(computing_system, monitor, 'p_cons')

    ## Carbon -> CarbonAgent -> VES
    world.connect(carbon, carbon_agent, ("Carbon Intensity", "ci"))
    world.connect(carbon_agent, virtual_energy_system, "ci")

    ## Solar -> SolarAgent -> VES
    world.connect(solar, solar_agent, ("P", "solar"))
    world.connect(solar_agent, virtual_energy_system, "solar")

    ## computing_system -> VES
    # world.connect(computing_system, virtual_energy_system, ('p_con', 'consumption'))

    world.connect(
        virtual_energy_system,
        monitor,
        "consumption",
        "battery_min_soc",
        "battery_soc",
        "solar",
        "ci",
    )

    # world.connect(load, monitor, 'p_mw')
    # world.connect(ext_grid, monitor, 'p_mw')
    # mosaik.util.connect_many_to_one(world, lines, monitor, 'loading_percent')


if __name__ == "__main__":
    main(sim_args)
