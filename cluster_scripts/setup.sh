#!/bin/bash
sbatch <<EOT
#!/bin/bash

#SBATCH -o setup.out      # Output-File
#SBATCH -D ./               # Working Directory
#SBATCH -J setup          # Job Name
#SBATCH --ntasks=16          # Number of requested CPU-Cores
#SBATCH --mem=8000M         # resident memory per node

##Provide Max Walltime :
#SBATCH --time=20:00:00     # Expected Runtime -> if exceeded your job gets killed!!!

#Define the node type:
#SBATCH --partition=standard

#Job-Status per Mail (see doc):
#SBATCH --mail-type=ALL
#SBATCH --mail-user=irion@campus.tu-berlin.de

module load python/3.9.19

# Setup
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install poetry

# Install dependencies using Poetry
poetry install

EOT
