from vessim import ClcBattery
from vessim.actor import Actor
from vessim.environment import Environment
from vessim.signal import SAMSignal, FileSignal
from vessim.controller import Monitor
import hydra
import math
import pandas as pd
import json
import logging
import numpy as np

log = logging.getLogger(__name__)


@hydra.main(
    config_path="data", config_name="config_battery_analysis_sweep_submitit", version_base=None
)
def main(cfg):
    all_turbines = pd.read_csv(
        cfg.file_paths.wind_turbines, header=0, skiprows=[1, 2], on_bad_lines="warn"
    )
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
    initial_soc = 7500 / cfg.battery_capacity if cfg.battery_capacity > 0 else 0

    environment = Environment(sim_start="2020-01-01 00:00:00", step_size=60)

    if cfg.battery_capacity > 0:
        microgrid = environment.add_microgrid(
            actors=[
                Actor(
                    signal=FileSignal(
                        file_path=cfg.file_paths.power_data,
                        unit="MW",
                        date_format="%a %d %b %Y %H:%M:%S GMT",
                        name="Perlmutter",
                    ),
                    name="ComputingSystem",
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
            storage=ClcBattery(
                number_of_cells=num_of_cells,
                initial_soc=initial_soc,
                nom_voltage=3.63,
                min_soc=0.0,
                v_1=0.0,
                v_2=cfg.single_cell_capacity,
                u_1=-0.087,
                u_2=-1.326,
                eta_c=0.95,
                eta_d=1.05,
                alpha_c=0.5,
                alpha_d=-0.5,
            ),
        )
        monitor = Monitor([microgrid])
        environment.add_controller(monitor)
    else:
        microgrid = environment.add_microgrid(
            actors=[
                Actor(
                    signal=FileSignal(
                        file_path=cfg.file_paths.power_data,
                        unit="MW",
                        date_format="%a %d %b %Y %H:%M:%S GMT",
                        name="Perlmutter",
                        invert=True,
                    ),
                    name="ComputingSystem",
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
        )
        monitor = Monitor([microgrid])
        environment.add_controller(monitor)

    environment.run(until=24 * 3600 * 2)
    monitor.to_csv("result.csv")

    df = pd.read_csv(
        "result.csv",
        parse_dates=["time"],
        index_col="time",
    )

    df["total_consumption"] = df["actor_states.ComputingSystem.p"]
    df["total_renewable_power"] = df["actor_states.Wind.p"] + df["actor_states.Solar.p"]

    carbon_data = pd.read_csv(cfg.file_paths.carbon_data, parse_dates=["Datetime (UTC)"])
    carbon_data["Datetime (UTC)"] = pd.to_datetime(carbon_data["Datetime (UTC)"])
    carbon_data.set_index("Datetime (UTC)", inplace=True)
    carbon_data.index = carbon_data.index.tz_localize(None)
    carbon_data = carbon_data[["Carbon Intensity gCO₂eq/kWh (LCA)"]].rename(
        columns={"Carbon Intensity gCO₂eq/kWh (LCA)": "carbon_intensity"}
    )
    carbon_data_resampled = carbon_data.resample("60s").ffill()
    carbon_data_filtered = carbon_data_resampled.loc[df.index.min() : df.index.max()]

    merged_data = df.merge(carbon_data_filtered, left_index=True, right_index=True, how="left")

    dt_h = 1.0 / 60.0

    E_load = np.abs(merged_data["total_consumption"]) * dt_h
    E_renew = merged_data["total_renewable_power"] * dt_h

    if "storage.charge_level" in merged_data.columns:
        dSOC_wh = merged_data["storage.charge_level"].diff().fillna(0)
        E_batt = (-dSOC_wh).clip(lower=0)
    else:
        E_batt = pd.Series(0.0, index=merged_data.index)

    E_nonren = np.maximum(E_load - (E_renew + E_batt), 0)

    merged_data["carbon_emissions"] = (E_nonren / 1000.0) * merged_data["carbon_intensity"]

    cov = (E_renew + E_batt) / E_load.replace({0: np.nan})
    merged_data["coverage"] = cov.clip(0, 1) * 100

    emb_ci = {"wind": 12, "solar": 19, "battery": 74}
    total_wind_kwh = (merged_data["actor_states.Wind.p"].sum() / 1000) * dt_h
    total_solar_kwh = (merged_data["actor_states.Solar.p"].sum() / 1000) * dt_h
    emb_wind = emb_ci["wind"] * total_wind_kwh
    emb_solar = emb_ci["solar"] * total_solar_kwh
    batt_cap = cfg.battery_capacity  # kWh
    emb_batt = batt_cap * (emb_ci["battery"] * 1000)
    embodied_emissions_g = emb_wind + emb_solar + emb_batt

    op_emissions_g = ((E_nonren / 1000.0) * merged_data["carbon_intensity"]).sum()

    coverage_pct = merged_data["coverage"].mean()

    log.info(f"Embodied emissions: {embodied_emissions_g:.2f} gCO₂")
    log.info(f"Operational emissions: {op_emissions_g:.2f} gCO₂")
    log.info(f"Average coverage: {coverage_pct:.2f}%")

    merged_data.to_csv(
        hydra.core.hydra_config.HydraConfig.get().runtime.output_dir + "/merged_data.csv"
    )

    return coverage_pct


def automatic_farm_layout(
    desired_farm_size: float, wind_turbine_kw_rating: float, wind_turbine_rotor_diameter: float
):
    num = math.floor(desired_farm_size / wind_turbine_kw_rating)
    if num <= 1:
        num = 1
    num_turbines = num

    x = [0] * num_turbines
    y = [0] * num_turbines

    rows = math.floor(math.sqrt(num_turbines))
    cols = num_turbines / rows
    while rows * math.floor(cols) != num_turbines:
        rows -= 1
        cols = num_turbines / rows

    spacing_x = 8 * wind_turbine_rotor_diameter
    spacing_y = 8 * wind_turbine_rotor_diameter

    x[0] = 0
    y[0] = 0

    for i in range(1, num_turbines):
        x[i] = (i - cols * math.floor(i / cols)) * spacing_x
        y[i] = math.floor(i / cols) * spacing_y

    return {
        "wind_farm_xCoordinates": x,
        "wind_farm_yCoordinates": y,
    }


if __name__ == "__main__":
    main()
