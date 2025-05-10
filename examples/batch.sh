#!/bin/bash

battery_capacity=0

# Run the command 14 times
for i in {1..7}
do
    echo "-----------------------------------------"
    echo "Iteration: $i / 7"
    echo "Target battery capacity: $battery_capacity"
    echo "Checking for running SLURM jobs..."

    # Wait until there are no SLURM jobs for the user
    while true; do
        job_count=$(squeue -u $USER | wc -l)  # Get job count
        job_count=$((job_count - 1))  # Subtract 1 to remove header line

        echo "Current running jobs: $job_count"  # Debugging output

        if [[ $job_count -eq 0 ]]; then
            echo "No jobs detected. Proceeding with next iteration."
            break  # Exit loop when there are no jobs
        fi

        echo "Waiting for all SLURM jobs to finish..."
        sleep 30
    done

    echo "Executing Python script with battery_capacity=$battery_capacity..."

    # Run the Python script
    stdbuf -oL -eL python renewable_battery_analysis.py --multirun --config-name config_battery_analysis_sweep_submitit battery_capacity=$battery_capacity | tee -a output.log

    battery_capacity=$((battery_capacity + 7500))

    echo "Iteration $i completed. Sleeping for 30 seconds before next run..."

    # Sleep for 30 seconds before next run
    sleep 30
done

echo "All iterations completed successfully!"
