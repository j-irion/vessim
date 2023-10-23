"""Co-simulation example.

Runs a fully simulated example scenario over the course of two days.
"""

import mosaik  # type: ignore

from examples._data import load_carbon_data, load_solar_data
from vessim.core.consumer import ComputingSystem, MockPowerMeter
from vessim.core.microgrid import SimpleMicrogrid
from vessim.core.simulator import Generator, CarbonApi, WindGenerator
from vessim.core.storage import SimpleBattery, DefaultStoragePolicy

COSIM_CONFIG = {
    "Microgrid": {"python": "vessim.cosim:MicrogridSim"},
    "Consumer": {
        "python": "vessim.cosim:ConsumerSim",
    },
    "Generator": {
        "python": "vessim.cosim:GeneratorSim",
    },
    "CarbonApi": {
        "python": "vessim.cosim:CarbonApiSim",
    },
    "Monitor": {
        "python": "vessim.cosim:MonitorSim",
    },
    "Cacu": {
        "python": "examples.cosim_example.cacu:CacuSim",
    },
}
SIM_START = "2020-06-11 00:00:00"
DURATION = 3600 * 24 * 2  # two days
STORAGE = SimpleBattery(
    capacity=32 * 5 * 3600,  # 10Ah * 5V * 3600 := Ws
    charge_level=32 * 5 * 3600 * 0.6,
    min_soc=0.6,
)
STORAGE_POLICY = DefaultStoragePolicy()


def run_simulation(carbon_aware: bool, result_csv: str, weather_data_file: str):
    world = mosaik.World(COSIM_CONFIG)

    mock_power_meters = [
        MockPowerMeter(name="mpm0", p=2.194),
        MockPowerMeter(name="mpm1", p=7.6),
    ]

    # Initialize computing system
    consumer_sim = world.start("Consumer", step_size=60)
    computing_system = consumer_sim.Consumer(
        consumer=ComputingSystem(power_meters=mock_power_meters)
    )

    # Initialize solar generator
    wind_sim = world.start("Generator", sim_start=SIM_START)
    wind = wind_sim.Generator(generator=WindGenerator(weather_data_file))

    # Initialize carbon intensity API
    carbon_api_sim = world.start(
        "CarbonApi", sim_start=SIM_START, carbon_api=CarbonApi(data=load_carbon_data())
    )
    carbon_api_de = carbon_api_sim.CarbonApi(zone="DE")

    if carbon_aware:
        # Initialize carbon-aware control unit
        cacu_sim = world.start("Cacu", step_size=60)
        cacu = cacu_sim.Cacu(
            mock_power_meters=mock_power_meters, battery=STORAGE, policy=STORAGE_POLICY
        )
        # Connect ci to cacu
        world.connect(carbon_api_de, cacu, ("carbon_intensity", "ci"))

    # Connect consumers and producers to microgrid
    microgrid_sim = world.start("Microgrid")
    microgrid = microgrid_sim.Microgrid(
        microgrid=SimpleMicrogrid(storage=STORAGE, policy=STORAGE_POLICY)
    )
    world.connect(computing_system, microgrid, "p")
    world.connect(wind, microgrid, "p")

    # Connect all simulation entities and the battery to the monitor
    monitor_sim = world.start("Monitor", sim_start=SIM_START, step_size=60)
    monitor = monitor_sim.Monitor(
        out_path=result_csv,
        fn=lambda: dict(battery_soc=STORAGE.soc(), battery_min_soc=STORAGE.min_soc),
    )
    world.connect(wind, monitor, ("p", "p_wind"))
    world.connect(computing_system, monitor, ("p", "p_computing_system"))
    world.connect(computing_system, monitor, ("info", "computing_system_info"))
    world.connect(microgrid, monitor, ("p_delta", "p_grid"))
    world.connect(carbon_api_de, monitor, "carbon_intensity")

    world.run(until=DURATION)


if __name__ == "__main__":
    run_simulation(
        carbon_aware=True,
        result_csv="data.csv",
        weather_data_file="../_data/WIND-Toolkit_lat39.74_lon-104.99_2014_60min.csv",
    )
