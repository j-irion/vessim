from numpy import number

from vessim import Actor, ClcBattery
from vessim.actor import ComputingSystem
from vessim.controller import Monitor
from vessim.cosim import Environment
from vessim.signal import SAMSignal, FileSignal
from vessim.storage import SimpleBattery
import hydra
import math
import pandas as pd
import json
import logging

log = logging.getLogger(__name__)


@hydra.main(config_path="data", config_name="config_battery_analysis_sweep", version_base=None)
def main(cfg):
    all_turbines = pd.read_csv(cfg.file_paths.wind_turbines, on_bad_lines="warn")
    turbine_data = all_turbines[all_turbines["Name"] == cfg.wind_turbine_model]
    turbine_rating = int(turbine_data["kW Rating"].values[0])
    turbine_rotor_diameter = int(turbine_data["Rotor Diameter"].values[0])
    turbine_power_curve = [
        float(value) for value in turbine_data["Power Curve Array"].values[0].split("|")
    ]
    turbine_wind_speeds = [
        float(value) for value in turbine_data["Wind Speed Array"].values[0].split("|")
    ]

    # Create wind config object
    with open(cfg.file_paths.wind_config, "r", errors="replace") as file:
        wind_config = json.load(file)
    farm_layout = automatic_farm_layout(
        desired_farm_size=cfg.wind_system_capacity,
        wind_turbine_kw_rating=turbine_rating,
        wind_turbine_rotor_diameter=turbine_rotor_diameter,
    )

    wind_config = {
        **wind_config,
        **farm_layout,
        "system_capacity": cfg.wind_system_capacity,
        "wind_turbine_powercurve_windspeeds": turbine_wind_speeds,
        "wind_turbine_powercurve_powerout": turbine_power_curve,
        "wind_turbine_rotor_diameter": turbine_rotor_diameter,
    }

    # Create solar config object
    with open(cfg.file_paths.solar_config, "r", errors="replace") as file:
        solar_config = json.load(file)

    solar_config["system_capacity"] = cfg.solar_system_capacity

    num_of_cells = int((cfg.battery_capacity * 1000) / cfg.single_cell_capacity)

    environment = Environment(sim_start="2020-05-01 00:00:00")

    monitor = Monitor()  # stores simulation result on each step
    environment.add_microgrid(
        actors=[
            ComputingSystem(
                nodes=[
                    FileSignal(
                        file_path=cfg.file_paths.power_data,
                        unit="MW",
                        date_format="%a %d %b %Y %H:%M:%S GMT",
                        name="Perlmutter",
                    )
                ],
                pue=1.07,
            ),
            Actor(
                signal=SAMSignal(
                    model="Windpower",
                    weather_file=cfg.file_paths.wind_data,
                    config_object=wind_config,
                ),
                name="Wind",
            ),
            Actor(
                signal=SAMSignal(
                    model="Pvwattsv8",
                    weather_file=cfg.file_paths.solar_data,
                    config_object=solar_config,
                ),
                name="Solar",
            ),
        ],
        controllers=[monitor],
        storage=ClcBattery(
            number_of_cells=num_of_cells,
            initial_soc=1.0,
            nom_voltage=3.63,
            min_soc=0.0,
            v_1=0.0,
            v_2=cfg.single_cell_capacity,
            u_1=-(0.01 / 3.63),
            u_2=-(0.04 / 3.63),
            eta_c=0.97,
            eta_d=1.04,
            alpha_c=3.0,
            alpha_d=-3.0,
        ),
        step_size=60,  # global step size (can be overridden by actors or controllers)
    )

    environment.run(until=24 * 3600 * 14)  # 14 Tage
    monitor.to_csv("result.csv")

    # Load the CSV file and calculate statistics
    df = pd.read_csv("result.csv", index_col=0, parse_dates=True)
    abs_p_delta = df["p_delta"].abs()
    avg_abs_p_delta = abs_p_delta.mean()
    std_abs_p_delta = abs_p_delta.std()

    # Calculate the embodied carbon of the wind power
    sum_wind_power_watts = df["Wind.p"].sum()
    total_wind_power_kWh = (sum_wind_power_watts / 1000) * (1 / 60)
    embodied_carbon_wind_grams_co2 = 12 * total_wind_power_kWh

    # Calculate the embodied carbon of the solar power
    sum_solar_power_watts = df["Solar.p"].sum()
    total_solar_power_kWh = (sum_solar_power_watts / 1000) * (1 / 60)
    embodied_carbon_solar_grams_co2 = 55 * total_solar_power_kWh

    # Calculate the embodied carbon of the battery
    battery_capacity_kWh = num_of_cells * cfg.single_cell_capacity / 1000
    embodied_carbon_battery_grams_co2 = battery_capacity_kWh * 74000

    embodied_carbon = (
        embodied_carbon_wind_grams_co2
        + embodied_carbon_solar_grams_co2
        + embodied_carbon_battery_grams_co2
    )

    # embodied_carbon = embodied_carbon_solar_grams_co2

    # Calculate the operational carbon
    carbon_data = pd.read_csv(cfg.file_paths.carbon_data, index_col=0, parse_dates=True)

    carbon_data.index = carbon_data.index.tz_localize(None)

    carbon_data_resampled = carbon_data.resample("60s").ffill()
    carbon_data_filtered = carbon_data_resampled.loc[df.index.min() : df.index.max()]

    merged_data = df.merge(carbon_data_filtered, left_index=True, right_index=True, how="left")

    merged_data["carbon_emissions"] = merged_data.apply(
        lambda row: (
            (-1 * row["p_delta"] / 1000 * (1 / 60) * row["carbon_intensity"])
            if row["p_delta"] < 0
            else 0
        ),
        axis=1,
    )

    operational_carbon = merged_data["carbon_emissions"].sum()

    # calculate renewable coverage

    # Calculate the total power production from wind and solar
    merged_data["total_renewable_power"] = merged_data["Wind.p"] + merged_data["Solar.p"]

    # Calculate the total power consumption of the computing system
    column_name = next(
        col for col in merged_data.columns if "ComputingSystem-" in col and col.endswith(".p")
    )
    merged_data["total_consumption"] = merged_data[column_name]

    # Calculate renewable coverage as the percentage of renewable power over total consumption
    # Renewable Coverage (%) = (Total Renewable Power / Total Consumption) * 100
    merged_data["renewable_coverage_percent"] = (
        merged_data["total_renewable_power"] / merged_data["total_consumption"].abs()
    ) * 100

    # Replace any infinite values with 0 (which can occur if there are periods of zero consumption)
    merged_data.replace(
        {"renewable_coverage_percent": {float("inf"): 0, -float("inf"): 0}}, inplace=True
    )

    merged_data["netzero"] = (merged_data["p_delta"] >= 0).astype(int)

    # Summarize the renewable coverage
    renewable_coverage_summary = merged_data["renewable_coverage_percent"].describe()

    # Calculate the percentage of time (24/7 coverage) where renewable coverage is 100% or more
    coverage_100_percent_or_more = merged_data[
        merged_data["renewable_coverage_percent"] >= 100
    ].shape[0]
    total_time_periods = merged_data.shape[0]

    coverage_247_percentage = (coverage_100_percent_or_more / total_time_periods) * 100

    # calculate percentage of time where netzero is achieved
    netzero_percentage = (merged_data["netzero"].sum() / total_time_periods) * 100

    merged_data.to_csv(
        hydra.core.hydra_config.HydraConfig.get().runtime.output_dir + "/merged_data.csv"
    )
    log.info(f"24/7 coverage: {coverage_247_percentage}")
    log.info(f"Netzero percentage: {netzero_percentage}")
    log.info(f"Operational carbon: {operational_carbon}")
    log.info(f"Embodied carbon: {embodied_carbon}")
    return coverage_247_percentage


def automatic_farm_layout(
    desired_farm_size: float, wind_turbine_kw_rating: float, wind_turbine_rotor_diameter: float
):
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
