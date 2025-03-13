#!/bin/bash

# Initial wind system capacity
wind_system_capacity=1500

# Run the command 14 times
for i in {1..14}
do
    # Wait until there are no SLURM jobs for the user
    while true; do
        job_count=$(squeue -u $USER | wc -l)  # Get job count
        job_count=$((job_count - 1))  # Subtract 1 to remove header line

        echo "Current job count: $job_count"  # Debugging output

        if [[ $job_count -eq 0 ]]; then
            break  # Exit loop when there are no jobs
        fi

        echo "Waiting for all SLURM jobs to finish..."
        sleep 30
    done

    # Run the Python script
    stdbuf -oL -eL python renewable_battery_analysis.py --multirun --config-name config_battery_analysis_sweep_submitit wind_system_capacity=$wind_system_capacity | tee -a output.log

    # Increase wind system capacity by 1500
    wind_system_capacity=$((wind_system_capacity + 1500))

    # Sleep for 30 seconds before next run
    sleep 30
done
