from abc import ABC
from datetime import datetime
from typing import Union, List, Optional

import pandas as pd
import PySAM.Windpower as wp

Time = Union[int, float, str, datetime]


class TraceSimulator(ABC):
    def __init__(self, data: Union[pd.Series, pd.DataFrame]):
        self.data = data

    def next_update(self, dt: Time):
        """Returns the next time of when the trace will change.

        This method is being called in the time-based simulation model for Mosaik.
        """
        current_index = self.data.index.asof(dt)
        next_iloc = self.data.index.get_loc(current_index) + 1
        return self.data.index[next_iloc]


class CarbonApi(TraceSimulator):
    def __init__(self, data: pd.DataFrame, unit: str = "g_per_kWh"):
        """Service for querying the carbon intensity at different times and locations.

        Args:
            data: DataFrame with carbon intensity values. Each index represents a
                timestamp and each column a location.
            unit: Unit of the carbon intensity data: gCO2/kWh (`g_per_kWh`) or lb/MWh
                (`lb_per_MWh`). Note that Vessim internally assumes gCO2/kWh, so choosing
                lb/MWh will simply convert this data to gCO2/kWh.
        """
        super().__init__(data)
        if unit == "lb_per_MWh":
            self.data = self.data * 0.45359237
        elif unit != "g_per_kWh":
            raise ValueError(f"Carbon intensity unit '{unit}' is not supported.")

    def zones(self) -> List:
        """Returns a list of all available zones."""
        return list(self.data.columns)

    def carbon_intensity_at(self, dt: Time, zone: Optional[str] = None) -> float:
        """Returns the carbon intensity at a given time and zone.

        If the queried timestamp is not available in the `data` dataframe, the last valid
        datapoint is being returned.
        """
        if zone is None:
            if len(self.zones()) == 1:
                zone = self.zones()[0]
            else:
                raise ValueError("Need to specify carbon intensity zone.")
        try:
            zone_carbon_intensity = self.data[zone]
        except KeyError:
            raise ValueError(f"Cannot retrieve carbon intensity at zone '{zone}'.")
        try:
            return zone_carbon_intensity.loc[self.data.index.asof(dt)]
        except KeyError:
            raise ValueError(
                f"Cannot retrieve carbon intensity at {dt} in zone " f"'{zone}'."
            )


class Generator(TraceSimulator):
    def power_at(self, dt: Time) -> float:
        """Returns the power generated at a given time.

        If the queried timestamp is not available in the `data` dataframe, the last valid
        datapoint is being returned.

        Raises:
            ValueError: If no datapoint is found for the given timestamp.
        """
        try:
            return self.data.loc[self.data.index.asof(dt)]
        except KeyError:
            raise ValueError(f"Cannot retrieve power at {dt}.")


class WindGenerator(Generator):
    def __init__(self, weather_data_file):
        # Load the weather data
        weather_data = pd.read_csv(weather_data_file, skiprows=1)

        # Create a datetime index from the Year, Month, Day, Hour, and Minute columns
        weather_data["Datetime"] = pd.to_datetime(
            weather_data[["Year", "Month", "Day", "Hour", "Minute"]]
        )
        weather_data.set_index("Datetime", inplace=True)

        super().__init__(data=weather_data)  # Call parent constructor
        self.model = wp.default("WindPowerNone")
        # Load the weather data
        self.model.Resource.wind_resource_filename = weather_data_file
        self.model.execute()

    def power_at(self, dt: Time) -> float:
        try:
            # Convert the Time to an appropriate index in the dataframe
            idx = self._time_to_index(dt)

            # Retrieve the power from PySAM model
            power = float(self.model.Outputs.gen[idx])

            return power
        except KeyError:
            # If the exact timestamp isn't found, get the last valid index
            last_valid_idx = self.data.index.asof(dt)

            if pd.isna(last_valid_idx):
                raise ValueError(f"Cannot retrieve power at {dt}.")

            # Convert the last valid datetime to an appropriate index in the dataframe
            last_valid_idx = self.data.index.get_loc(last_valid_idx)

            # Retrieve the power from PySAM model using the last valid index
            power = float(self.model.Outputs.gen[last_valid_idx])

            return power

    def _time_to_index(self, dt: Time) -> int:
        # Convert the provided Time to a datetime object
        datetime_obj = datetime.strptime(
            str(dt), "%Y-%m-%d %H:%M:%S"
        )  # Adjust the format as per your Time object's structure

        # Find the index of the datetime object in the dataframe
        idx = self.data.index.get_loc(datetime_obj)

        return idx
