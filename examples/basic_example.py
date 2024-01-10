from examples._data import get_ci_time_series_api, get_solar_time_series_api
from vessim.cosim import Microgrid, Environment, ComputingSystem, Generator, Monitor, \
    MockPowerMeter, SimpleBattery

SIM_START = "2020-06-11 00:00:00"
DURATION = 3600 * 24 * 2  # two days
STORAGE = SimpleBattery(
    capacity=32 * 5 * 3600,  # 10Ah * 5V * 3600 := Ws
    charge_level=32 * 5 * 3600 * .6,
    min_soc=.6
)


def main(result_csv: str):
    environment = Environment(sim_start=SIM_START)
    environment.add_grid_signal("carbon_intensity", get_ci_time_series_api())

    monitor = Monitor(step_size=60)
    microgrid = Microgrid(
        actors=[
            ComputingSystem(
                name="server",
                step_size=60,
                power_meters=[
                    MockPowerMeter(name="mpm0", p=2.194),
                    MockPowerMeter(name="mpm1", p=7.6)
                ]
            ),
            Generator(
                name="solar",
                step_size=60,
                time_series_api=get_solar_time_series_api(),
                zone="solar",
            ),
        ],
        controllers=[monitor],
        storage=STORAGE,
        zone="DE",
    )

    environment.add_microgrid(microgrid)
    environment.run(until=DURATION)
    monitor.monitor_log_to_csv(result_csv)


if __name__ == "__main__":
    main(result_csv="result.csv")
