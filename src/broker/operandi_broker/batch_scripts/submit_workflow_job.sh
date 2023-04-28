#!/bin/bash
#SBATCH --constraint scratch
#SBATCH --partition medium
#SBATCH --cpus-per-task 8
#SBATCH --mem 32G
#SBATCH --output ./jobs_output/workflow-job-%J.txt

# Parameters are as follows:
# S0 - This batch script
# $1 - Workflow job id
# $2 - Nextflow script id
# $3 - Entry input file group

WORKFLOW_JOB_ID=$1
NEXTFLOW_SCRIPT_ID=$2
IN_FILE_GRP=$3

hostname
slurm_resources

module purge
module load singularity
module load nextflow

SIF_PATH="/scratch1/users/mmustaf/ocrd_all_image_2023_04_17_1422.sif"
HOME_BASE="/home/users/${USER}/workflow_jobs"
SCRATCH_BASE="/scratch1/users/${USER}/workflow_jobs"

if [ ! -f "${SIF_PATH}" ]; then
  echo "Required ocrd_all_image sif file not found at: ${SIF_PATH}"
  exit 1
fi

if [ ! -d "${SCRATCH_BASE}" ]; then
  mkdir -p "${SCRATCH_BASE}"
fi

if [ ! -d "${SCRATCH_BASE}" ]; then
  echo "Required scratch base dir was not created: ${SCRATCH_BASE}"
  exit 1
fi

mv "${HOME_BASE}/${WORKFLOW_JOB_ID}" "${SCRATCH_BASE}"

# shellcheck disable=SC2164
cd "${SCRATCH_BASE}/${WORKFLOW_JOB_ID}"

# Execute the Nextflow script
nextflow run "${SCRATCH_BASE}/${WORKFLOW_JOB_ID}/${NEXTFLOW_SCRIPT_ID}" \
-ansi-log false \
-with-report \
--volume_map_dir "${SCRATCH_BASE}/${WORKFLOW_JOB_ID}" \
--sif_path ${SIF_PATH} \
--input_file_group "${IN_FILE_GRP}" \
--mets "${SCRATCH_BASE}/${WORKFLOW_JOB_ID}/data/mets.xml"

# Delete symlinks created for the Nextflow workers
find "${SCRATCH_BASE}/${WORKFLOW_JOB_ID}" -type l -delete
mv "${SCRATCH_BASE}/${WORKFLOW_JOB_ID}" "${HOME_BASE}"
