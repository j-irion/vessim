#!/bin/bash

# Initial wind system capacity
wind_system_capacity=1500

# Run the command 14 times
for i in {1..14}
do
    python renewable_battery_analysis.py --multirun --config-name config_battery_analysis_sweep_submitit wind_system_capacity=$wind_system_capacity

    # Increase wind system capacity by 1500
    wind_system_capacity=$((wind_system_capacity + 1500))

    # Sleep for 30 seconds before next run
    sleep 30
done