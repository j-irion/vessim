"""1st example scenario.

As described in 'Software-in-the-loop simulation for developing and testing carbon-aware
applications'.
"""

import mosaik
from simulator.power_meter import NodeApiMeter
from vessim.storage import SimpleBattery, DefaultStoragePolicy

# Config file for parameters and settings specification.
sim_config = {
    "CSV": {
        "python": "mosaik_csv:CSV",
    },
    "ComputingSystem": {
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
}


def main(start_date: str,
         duration: int,
         carbon_data_file: str,
         solar_data_file: str,
         battery_capacity: float,
         battery_initial_soc: float,
         battery_min_soc: float,
         battery_c_rate: float):
    """Execute the example scenario simulation."""
    world = mosaik.World(sim_config)

    gcp_power_meter = NodeApiMeter("http://34.159.204.246", name="gcp_power_meter")
    computing_system_sim = world.start('ComputingSystem', step_size=60)
    computing_system = computing_system_sim.ComputingSystemModel(
        power_meters=[gcp_power_meter],
        pue=1.5
    )

    # Carbon Sim from CSV dataset
    carbon_sim = world.start("CSV", sim_start=start_date, datafile=carbon_data_file)
    carbon = carbon_sim.CarbonIntensity.create(1)[0]

    # Carbon Controller acts as a medium between carbon module and VES or
    # direct consumer since producer is only a CSV generator.
    carbon_controller = world.start("CarbonController")
    carbon_agent = carbon_controller.CarbonAgent()

    # Solar Sim from CSV dataset
    solar_sim = world.start("CSV", sim_start=start_date, datafile=solar_data_file)
    solar = solar_sim.PV.create(1)[0]

    # Solar Controller acts as medium between solar module and VES or consumer,
    # as the producer only generates CSV data.
    solar_controller = world.start("SolarController")
    solar_agent = solar_controller.SolarAgent()

    ## Carbon -> CarbonAgent -> VES
    world.connect(carbon, carbon_agent, ("Carbon Intensity", "ci"))

    ## Solar -> SolarAgent -> VES
    world.connect(solar, solar_agent, ("P", "solar"))


    world.run(until=duration)


if __name__ == "__main__":
    main(
        start_date="2014-01-01 00:00:00",
        duration=600,
        carbon_data_file="data/ger_ci_testing.csv",
        solar_data_file="data/pv_10kw.csv",
        battery_capacity=10 * 5 * 3600,  # 10Ah * 5V * 3600 := Ws
        battery_initial_soc=.7,
        battery_min_soc=.6,
        battery_c_rate=.2,
    )
