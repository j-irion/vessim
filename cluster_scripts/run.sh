#!/bin/bash

# init default values
jobname="Exhaustive Battery Sweep"
command="poetry run python renewable_battery_analysis.py --multirun"
ntasks=128  # cores
memory=32000M
mail="irion@tu-berlin.de"
#license="~/gurobi.lic"

while getopts j:c:n:m:r: flag
do
    case "${flag}" in
        j) jobname=${OPTARG};;
        c) command=${OPTARG};;
        n) ntasks=${OPTARG};;
        m) memory=${OPTARG};;
        r) mail=${OPTARG};;
        #l) license=${OPTARG};;
    esac
done

echo Starting job \"$jobname\" using $ntasks cores
echo Command: $command
echo Results will be sent to $mail

sbatch <<EOT
#!/bin/bash

#SBATCH -o ${jobname}.out      # Output-File
#SBATCH -D ./               # Working Directory
#SBATCH -J $jobname            # Job Name
#SBATCH --ntasks=$ntasks     # Number of requested CPU-Cores
#SBATCH --mem=$memory         # resident memory per node

##Provide Max Walltime :
#SBATCH --time=48:00:00     # Expected Runtime -> if exceeded your job gets killed!!!

#Define the node type:
#SBATCH --partition=standard

#Job-Status per Mail (see doc):
#SBATCH --mail-type=ALL
#SBATCH --mail-user=$mail

module load python/3.9.19

export HYDRA_FULL_ERROR=1

source venv/bin/activate
cd examples
$command
EOT