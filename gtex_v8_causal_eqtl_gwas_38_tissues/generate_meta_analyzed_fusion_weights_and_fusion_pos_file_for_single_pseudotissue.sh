#!/bin/bash
#SBATCH -c 1                               # Request one core
#SBATCH -t 0-10:00                         # Runtime in D-HH:MM format
#SBATCH -p short                           # Partition to run in
#SBATCH --mem=5GB                         # Memory total in MiB (for all cores)


pseudotissue_name="$1"
composit_tissue_string="$2"
gtex_fusion_weights_data_dir="$3"
gtex_fusion_weights_dir="$4"
pseudotissue_gtex_fusion_weights_dir="$5"

if false; then
	source ~/.bash_profile
fi

echo $pseudotissue_name



python3 generate_meta_analyzed_fusion_weights_and_fusion_pos_file_for_single_pseudotissue.py $pseudotissue_name $composit_tissue_string $gtex_fusion_weights_data_dir $gtex_fusion_weights_dir $pseudotissue_gtex_fusion_weights_dir