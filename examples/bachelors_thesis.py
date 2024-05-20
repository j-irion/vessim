from vessim.actor import ComputingSystem, Generator
from vessim.controller import Monitor
from vessim.cosim import Environment
from vessim.power_meter import MockPowerMeter, FilePowerMeter
from vessim.signal import SAMSignal
from vessim.storage import SimpleBattery
import hydra
import math


@hydra.main(config_path="data", config_name="config", version_base=None)
def main(cfg):
    turbine_rating = 1500  # kW

    wind_config = cfg.windpower_cfg
    farm_layout = automatic_farm_layout(
        desired_farm_size=wind_config.system_capacity,
        wind_turbine_kw_rating=turbine_rating,
        wind_turbine_rotor_diameter=wind_config.wind_turbine_rotor_diameter,
    )
    wind_config = {**wind_config, **farm_layout}

    environment = Environment(sim_start="2020-06-11 00:00:00")

    monitor = Monitor()  # stores simulation result on each step
    environment.add_microgrid(
        actors=[
            ComputingSystem(
                power_meters=[
                    FilePowerMeter(
                        file_path=cfg.file_paths.power_data,
                        unit="MW",
                        date_format="%a %d %b %Y %H:%M:%S GMT",
                    )
                ],
                pue=1.07,
            ),
            Generator(
                signal=SAMSignal(
                    model="Windpower",
                    weather_file=cfg.file_paths.wind_data,
                    config_object=wind_config,
                )
            ),
            # Generator(
            #     signal=SAMSignal(
            #         model="Pvwattsv8",
            #         weather_file=cfg.file_paths.solar_data,
            #         config_file=cfg.file_paths.solar_config,
            #     )
            # ),
        ],
        controllers=[monitor],
        storage=SimpleBattery(capacity=100, charge_level=100),
        step_size=60,  # global step size (can be overridden by actors or controllers)
    )

    environment.run(until=24 * 3600)  # 24h
    monitor.to_csv("result.csv")


def automatic_farm_layout(desired_farm_size, wind_turbine_kw_rating, wind_turbine_rotor_diameter):
    num = math.floor(desired_farm_size / wind_turbine_kw_rating)
    if num <= 1:
        num = 1
    num_turbines = num

    x = [0] * num_turbines
    y = [0] * num_turbines

    # Assume they are laid out in roughly a square
    rows = math.floor(math.sqrt(num_turbines))
    cols = num_turbines / rows
    while rows * math.floor(cols) != num_turbines:  # If not evenly divisible
        rows -= 1  # Decrease the number of rows until it does divide evenly
        # If num_turbines is prime, this will continue until rows = 1
        cols = num_turbines / rows

    # Use default spacing assumptions, in multiples of rotor diameters
    spacing_x = 8 * wind_turbine_rotor_diameter
    spacing_y = 8 * wind_turbine_rotor_diameter

    # First turbine placement
    x[0] = 0
    y[0] = 0

    # Remainder of turbines
    for i in range(1, num_turbines):
        x[i] = (i - cols * math.floor(i / cols)) * spacing_x
        y[i] = math.floor(i / cols) * spacing_y

    return {
        "wind_farm_xCoordinates": x,
        "wind_farm_yCoordinates": y,
    }


if __name__ == "__main__":
    main()
