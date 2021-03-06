import sys
sys.path.remove('/n/app/python/3.7.4-ext/lib/python3.7/site-packages')
import pandas as pd
import numpy as np 
import os 
import pdb
import scipy.special
import pickle
import tgfm_causal_twas
#import tgfm_fine_mapping
import tgfm_rss_fine_mapping
import rpy2
import rpy2.robjects.numpy2ri as numpy2ri
import rpy2.robjects as ro
ro.conversion.py2ri = numpy2ri
numpy2ri.activate()
from rpy2.robjects.packages import importr
susieR_pkg = importr('susieR')




def extract_gwas_component_susie_pmces_in_same_order_as_twas_data(gwas_component_susie_pmces_file, twas_bim):
	num_twas_var = twas_bim.shape[0]
	# First create mapping from twas variants to position
	mapping = {}
	for var_iter in range(num_twas_var):
		var_name = twas_bim[var_iter, 1]
		mapping[var_name] = (var_iter, twas_bim[var_iter,4], twas_bim[var_iter,5])
		var_info = var_name.split('_')
		alt_var_name = var_info[0] + '_' + var_info[1] + '_' + var_info[3] + '_' + var_info[2] + '_' + var_info[4]
		mapping[alt_var_name] = (var_iter, twas_bim[var_iter,4], twas_bim[var_iter,5])

	# Load in gwas pmces data
	gwas_component_pmces_data = np.loadtxt(gwas_component_susie_pmces_file, dtype=str,delimiter='\t')
	gwas_component_pmces_data = gwas_component_pmces_data[1:,:]

	
	# Initialize output array
	gwas_pmces = np.zeros(num_twas_var)
	gwas_susie_mu = np.zeros(num_twas_var)
	gwas_susie_mu_sd = np.zeros(num_twas_var)
	gwas_susie_alpha = np.zeros(num_twas_var)


	used_positions = {}
	for var_iter in range(gwas_component_pmces_data.shape[0]):
		variant_id = gwas_component_pmces_data[var_iter,0] + '_b38'
		if variant_id in mapping:
			variant_info = variant_id.split('_')
			rev = 1.0
			if variant_info[2] != mapping[variant_id][1]:
				rev = -1.0
			gwas_pmces[mapping[variant_id][0]] = float(gwas_component_pmces_data[var_iter,1])*rev
			gwas_susie_mu[mapping[variant_id][0]] = float(gwas_component_pmces_data[var_iter,2])*rev
			gwas_susie_mu_sd[mapping[variant_id][0]] = float(gwas_component_pmces_data[var_iter,4])
			gwas_susie_alpha[mapping[variant_id][0]] = float(gwas_component_pmces_data[var_iter,3])

			used_positions[mapping[variant_id][0]] = 1
	if len(used_positions) != num_twas_var:
		print('assumption eroror')
		pdb.set_trace()
	return gwas_pmces, gwas_susie_mu, gwas_susie_mu_sd, gwas_susie_alpha


def get_eqtl_component_level_pmces(susie_mu, susie_alpha):
	susie_pmces = []
	for component_num in range(len(susie_mu)):
		susie_pmces.append(susie_mu[component_num]*susie_alpha[component_num])
	return susie_pmces

def extract_tissue_names(gtex_pseudotissue_file):
	f = open(gtex_pseudotissue_file)
	arr = []
	head_count = 0
	for line in f:
		line = line.rstrip()
		data = line.split('\t')
		if head_count == 0:
			head_count = head_count + 1
			continue
		arr.append(data[0])
	f.close()
	return np.asarray(arr)

def run_variant_level_susie_on_this_region(betas, betas_se, sample_size, ref_ld, original_gwas_susie_alpha):
	# res <- susie_rss(bhat=as.numeric(beta_mat[trait_num,]), shat=as.numeric(std_err_mat[trait_num,]), R=LD, n=sample_sizes[trait_num])
	try:
		m = len(betas)
		susie_variant_obj = susieR_pkg.susie_rss(bhat=betas.reshape((m,1)), shat=betas_se.reshape((m,1)), R=ref_ld, n=sample_size)

		susie_alpha = susie_variant_obj.rx2('alpha')
		susie_mu = susie_variant_obj.rx2('mu')
		susie_mu2 = susie_variant_obj.rx2('mu2')
		susie_mu_sd = np.sqrt(susie_mu2 - np.square(susie_mu))

		component_num = -1
		correlations = []
		for temp_component in range(susie_alpha.shape[0]):
			corry = np.corrcoef(susie_alpha[temp_component, :], original_gwas_susie_alpha)[0,1]
			correlations.append(corry)
		correlations = np.asarray(correlations)

		component_num = np.nanargmax(correlations)

		if correlations[component_num] < .5:
			print('low correlation error')
			discover_component_bool = False
		else:
			discover_component_bool = True
		pass_bool = True
	except ValueError:
		pass_bool = False
		susie_alpha = 'na'
		susie_mu = 'na'
		susie_mu_sd = 'na'
		component_num = -1
		discover_component_bool = False
		pass_bool = False

	return susie_alpha, susie_mu, susie_mu_sd, component_num, discover_component_bool, pass_bool
	


chrom_num = sys.argv[1]
trait_name = sys.argv[2]
gtex_pseudotissue_file = sys.argv[3]
component_data_file = sys.argv[4]
ukbb_genome_wide_susie_organized_results_dir = sys.argv[5]
output_dir = sys.argv[6]
gene_version = sys.argv[7]
fusion_weights = sys.argv[8]


ordered_tissue_names = extract_tissue_names(gtex_pseudotissue_file)
tissue_to_position_mapping = {}
for i, val in enumerate(ordered_tissue_names):
	tissue_to_position_mapping[val] = i

# Extract tissue specific prior (vector of length number of tissues)
tissue_specific_prior_precision_file = output_dir + trait_name + '_' + gene_version + '_count_genes_once_null_init_fusion_weights_' + fusion_weights + '_tissue_specific_prior_precision_temp.txt'
tissue_specific_prior_data = np.loadtxt(tissue_specific_prior_precision_file,dtype=str,delimiter='\t')
tissue_specific_prior_expected_variance = 1.0/tissue_specific_prior_data[1:,1].astype(float)



ordered_tissue_names = extract_tissue_names(gtex_pseudotissue_file)

# open output file
output_file = output_dir + trait_name + '_' + chrom_num + '_summary_tgfm_results_' + gene_version + '_fusion_' + fusion_weights + '_tissue_specific_prior.txt'

print(output_file)
t = open(output_file,'w')
# write header
t.write('component_name\tnum_genes\ttgfm_twas_pickle\ttgfm_rss_regression_fine_mapping_table_file\ttgfm_rss_regression_tissue_fine_mapping_table_file\tpickled_data_file\n')

# Loop through trait components
f = open(component_data_file)
head_count = 0
for line in f:
	line = line.rstrip()
	data = line.split('\t')
	# Skip header
	if head_count == 0:
		head_count = head_count + 1
		continue
	# Extract relevent fields from line corresponding to trait component
	component_name = data[1]
	num_genes = int(data[2])
	pickled_data_file = data[3]

	print(component_name + '\t' + str(num_genes))

	if pickled_data_file == 'NA':
		t.write(component_name + '\t' + str(num_genes) + '\t' 'NA' + '\t' + 'NA' + '\t' + 'NA' + '\t' + 'NA' + '\n')
	else:
		# Load in pickled data for this component
		f = open(pickled_data_file, "rb")
		twas_data = pickle.load(f)
		f.close()

		# Load in gwas component susie pmces
		gwas_component_susie_pmces_file = ukbb_genome_wide_susie_organized_results_dir + trait_name + '_' + component_name + '_component_posterior_mean_causal_effect_sizes.txt'
		gwas_component_susie_pmces, gwas_susie_mu, gwas_susie_mu_sd, gwas_susie_alpha = extract_gwas_component_susie_pmces_in_same_order_as_twas_data(gwas_component_susie_pmces_file, twas_data['bim'])

		# Run variant-level susie on this region
		gwas_new_susie_alpha, gwas_new_susie_mu, gwas_new_susie_mu_sd, gwas_new_susie_component_num, gwas_new_susie_discover_component_bool, pass_bool = run_variant_level_susie_on_this_region(twas_data['gwas_beta'], twas_data['gwas_beta_se'], twas_data['gwas_sample_size'], twas_data['reference_ld'], gwas_susie_alpha)

		if pass_bool == False:
			t.write(component_name + '\t' + str(num_genes) + '\t' 'NA' + '\t' + 'NA' + '\t' + 'NA' + '\t' + 'NA' + '\n')
			continue

		# Convert gwas summary statistics to *STANDARDIZED* effect sizes
		# Following SuSiE code found in these two places:
		########1. https://github.com/stephenslab/susieR/blob/master/R/susie_rss.R  (LINES 277-279)
		########2. https://github.com/stephenslab/susieR/blob/master/R/susie_ss.R (LINES 148-156 AND 203-205)
		beta_scaled, beta_se_scaled, XtX = tgfm_causal_twas.convert_to_standardized_summary_statistics(twas_data['gwas_beta'], twas_data['gwas_beta_se'], twas_data['gwas_sample_size'], twas_data['reference_ld'])
		twas_data['gwas_beta'] = beta_scaled
		twas_data['gwas_beta_se'] = beta_se_scaled

		pred = np.sum(gwas_new_susie_alpha*gwas_new_susie_mu,axis=0)
		resid =twas_data['gwas_beta']- np.dot(XtX, pred)*(1.0/np.diag(XtX))


		# Extract ordered tissues for this component
		component_tissues = []
		for gene_full_name in twas_data['genes']:
			component_tissues.append('_'.join(gene_full_name.split('_')[1:]))
		component_tissues = np.asarray(component_tissues)

		# Extract ordered gene prior variances for this component
		ordered_gene_prior_variances = []
		for component_tissue in component_tissues:
			prior_var = tissue_specific_prior_expected_variance[tissue_to_position_mapping[component_tissue]]
			ordered_gene_prior_variances.append(prior_var)
		ordered_gene_prior_variances = np.asarray(ordered_gene_prior_variances)

		# RUN TGFM CAUSAL TWAS
		#twas_obj = tgfm_causal_twas.TGFM_CAUSAL_TWAS(estimate_prior_variance=True, convergence_thresh=1e-6)
		if fusion_weights == 'True':
			twas_obj = tgfm_causal_twas.TGFM_CAUSAL_TWAS(fusion_weights=True, estimate_prior_variance=False, prior_variance_vector=ordered_gene_prior_variances, convergence_thresh=1e-8)
		else:
			twas_obj = tgfm_causal_twas.TGFM_CAUSAL_TWAS(estimate_prior_variance=False, prior_variance_vector=ordered_gene_prior_variances, convergence_thresh=1e-8)
		twas_obj.fit(twas_data_obj=twas_data)

		# Prepare data for TGFM fine mapping
		tgfm_fine_mapping_data = {'gwas_component_pmces': gwas_component_susie_pmces, 'gwas_susie_mu': gwas_susie_mu, 'gwas_susie_mu_sd': gwas_susie_mu_sd, 'gwas_susie_alpha': gwas_susie_alpha, 'eqtl_pmces': get_eqtl_component_level_pmces(twas_data['susie_mu'], twas_data['susie_alpha']), 'eqtl_mu':twas_data['susie_mu'], 'eqtl_mu_sd': twas_data['susie_mu_sd'], 'eqtl_alpha':twas_data['susie_alpha'], 'twas_alpha': twas_obj.alpha_mu, 'twas_alpha_sd': np.sqrt(twas_obj.alpha_var), 'genes': twas_data['genes'], 'variants': twas_data['variants'], 'ordered_tissue_names': ordered_tissue_names}

		# Run TGFM fine mapping
		#tgfm_fm_obj = tgfm_fine_mapping.TGFM_FM(likelihood_version='probabilistic_full', mean_component_boolean=False)
		#tgfm_fm_obj.fit(fm_data_obj=tgfm_fine_mapping_data)

		# Run RSS TGFM fine mapping
		tgfm_rss_fm_data = {'gwas_susie_mu': gwas_new_susie_alpha, 'gwas_susie_alpha': gwas_new_susie_alpha, 'gwas_susie_mu_sd':gwas_new_susie_mu_sd, 'gwas_susie_component': gwas_new_susie_component_num, 'twas_alpha': twas_obj.alpha_mu, 'twas_alpha_sd': np.sqrt(twas_obj.alpha_var), 'ordered_tissue_names': ordered_tissue_names}

		tgfm_rss_fm_obj_regr = tgfm_rss_fine_mapping.TGFM_RSS_FM(residual_version='regress')
		tgfm_rss_fm_obj_regr.fit(twas_data_obj=twas_data, tgfm_data_obj=tgfm_rss_fm_data)

		#tgfm_rss_fm_obj_pred = tgfm_rss_fine_mapping.TGFM_RSS_FM(residual_version='predict')
		#tgfm_rss_fm_obj_pred.fit(twas_data_obj=twas_data, tgfm_data_obj=tgfm_rss_fm_data)


		#tgfm_rss_fm_data = {'gwas_susie_mu': gwas_new_susie_mu, 'gwas_susie_alpha': gwas_new_susie_alpha, 'gwas_susie_mu_sd':gwas_new_susie_mu_sd, 'gwas_susie_component': gwas_new_susie_component_num, 'gwas_susie_XtX': XtX, 'twas_alpha': twas_obj.nominal_twas_rss_alpha_mu, 'twas_alpha_sd': np.sqrt(twas_obj.nominal_twas_rss_alpha_var), 'ordered_tissue_names': ordered_tissue_names}
		#tgfm_rss_fm_obj_nom_regr = tgfm_rss_fine_mapping.TGFM_RSS_FM(residual_version='regress')
		#tgfm_rss_fm_obj_nom_regr.fit(twas_data_obj=twas_data, tgfm_data_obj=tgfm_rss_fm_data)


		'''
		tissues = get_tissues(twas_data['genes'])
		twas_z = twas_obj.alpha_mu/np.sqrt(twas_obj.alpha_var)
		blood_z = twas_z[tissues == 'Whole_Blood']
		if len(blood_z) > 0 and np.max(np.abs(blood_z)) > 3.0:
			correlate_predicted_trait_effect_sizes_with_predictec_trait_eqtl_effect_sizes(gwas_new_susie_mu, gwas_new_susie_alpha, twas_data['susie_mu'], twas_data['susie_alpha'], twas_obj.alpha_mu, np.sqrt(twas_obj.alpha_var))
		'''

		# Save TWAS results to output file
		tgfm_twas_pkl_file = output_dir + trait_name + '_' + component_name + '_' + gene_version + '_fusion_' + fusion_weights + '_tgfm_twas_tissue_specific_prior_results.pkl'
		g = open(tgfm_twas_pkl_file, "wb")
		pickle.dump(twas_obj, g)
		g.close()	


		# Save Fine-mapping results to output files
		#tgfm_fm_results_table_file = output_dir + trait_name + '_' + component_name + '_' + gene_version + '_tgfm_fine_mapping_tissue_specific_prior_table.txt'
		#tgfm_fm_obj.posterior_prob_df.to_csv(tgfm_fm_results_table_file, sep='\t', index=False)
		#tgfm_tissue_fm_results_table_file = output_dir + trait_name + '_' + component_name + '_' + gene_version + '_tgfm_tissue_fine_mapping_tissue_specific_prior_table.txt'
		#tgfm_fm_obj.tissue_posterior_prob_df.to_csv(tgfm_tissue_fm_results_table_file, sep='\t', index=False)
		# TGFM RSS Regression
		tgfm_rss_regression_fm_results_table_file = output_dir + trait_name + '_' + component_name + '_' + gene_version + '_fusion_' + fusion_weights + '_tgfm_rss_regression_fine_mapping_tissue_specific_prior_table.txt'
		tgfm_rss_fm_obj_regr.posterior_prob_df.to_csv(tgfm_rss_regression_fm_results_table_file, sep='\t', index=False)
		tgfm_rss_regression_tissue_fm_results_table_file = output_dir + trait_name + '_' + component_name + '_' + gene_version + '_fusion_' + fusion_weights + '_tgfm_rss_regression_tissue_fine_mapping_tissue_specific_prior_table.txt'
		tgfm_rss_fm_obj_regr.tissue_posterior_prob_df.to_csv(tgfm_rss_regression_tissue_fm_results_table_file, sep='\t', index=False)
		# TGFM RSS prediction
		#tgfm_rss_prediction_fm_results_table_file = output_dir + trait_name + '_' + component_name + '_' + gene_version + '_tgfm_rss_prediction_fine_mapping_tissue_specific_prior_table.txt'
		#tgfm_rss_fm_obj_pred.posterior_prob_df.to_csv(tgfm_rss_prediction_fm_results_table_file, sep='\t', index=False)
		##tgfm_rss_prediction_tissue_fm_results_table_file = output_dir + trait_name + '_' + component_name + '_' + gene_version + '_tgfm_rss_prediction_tissue_fine_mapping_tissue_specific_prior_table.txt'
		#tgfm_rss_fm_obj_pred.tissue_posterior_prob_df.to_csv(tgfm_rss_prediction_tissue_fm_results_table_file, sep='\t', index=False)
		# TGFM RSS NOMINAL Regression
		#tgfm_rss_regression_nom_fm_results_table_file = output_dir + trait_name + '_' + component_name + '_' + gene_version + '_tgfm_rss_regression_nom_fine_mapping_tissue_specific_prior_table.txt'
		#tgfm_rss_fm_obj_nom_regr.posterior_prob_df.to_csv(tgfm_rss_regression_nom_fm_results_table_file, sep='\t', index=False)
		#tgfm_rss_regression_nom_tissue_fm_results_table_file = output_dir + trait_name + '_' + component_name + '_' + gene_version + '_tgfm_rss_regression_nom_tissue_fine_mapping_tissue_specific_prior_table.txt'
		#tgfm_rss_fm_obj_nom_regr.tissue_posterior_prob_df.to_csv(tgfm_rss_regression_nom_tissue_fm_results_table_file, sep='\t', index=False)


		# Write output files to component level output
		t.write(component_name + '\t' + str(num_genes) + '\t' + tgfm_twas_pkl_file  + '\t' + tgfm_rss_regression_fm_results_table_file + '\t' + tgfm_rss_regression_tissue_fm_results_table_file + '\t' + pickled_data_file + '\n')
f.close()
t.close()



'''

# open output file
output_file = output_dir + trait_name + '_' + chrom_num + '_summary_tgfm_results_tissue_specific_prior.txt'
t = open(output_file,'w')
# write header
t.write('component_name\tnum_genes\ttgfm_twas_pickle\ttgfm_fine_mapping_table_file\ttgfm_tissue_fine_mapping_table_file\ttgfm_input_data_file\n')

# Loop through trait components
f = open(component_data_file)
head_count = 0
for line in f:
	line = line.rstrip()
	data = line.split('\t')
	# Skip header
	if head_count == 0:
		head_count = head_count + 1
		continue
	# Extract relevent fields from line corresponding to trait component
	component_name = data[1]
	num_genes = int(data[2])
	pickled_data_file = data[3]

	print(component_name + '\t' + str(num_genes))

	if pickled_data_file == 'NA':
		t.write(component_name + '\t' + str(num_genes) + '\t' 'NA' + '\t' + 'NA' + '\t' + 'NA' + '\t' + 'NA' + '\n')
	else:
		# Load in pickled data for this component
		f = open(pickled_data_file, "rb")
		twas_data = pickle.load(f)
		f.close()

		# Load in gwas component susie pmces
		gwas_component_susie_pmces_file = ukbb_genome_wide_susie_organized_results_dir + trait_name + '_' + component_name + '_component_posterior_mean_causal_effect_sizes.txt'
		gwas_component_susie_pmces, gwas_susie_mu, gwas_susie_mu_sd, gwas_susie_alpha = extract_gwas_component_susie_pmces_in_same_order_as_twas_data(gwas_component_susie_pmces_file, twas_data['bim'])


		# Convert gwas summary statistics to *STANDARDIZED* effect sizes
		# Following SuSiE code found in these two places:
		########1. https://github.com/stephenslab/susieR/blob/master/R/susie_rss.R  (LINES 277-279)
		########2. https://github.com/stephenslab/susieR/blob/master/R/susie_ss.R (LINES 148-156 AND 203-205)
		beta_scaled, beta_se_scaled = tgfm_causal_twas.convert_to_standardized_summary_statistics(twas_data['gwas_beta'], twas_data['gwas_beta_se'], twas_data['gwas_sample_size'], twas_data['reference_ld'])
		twas_data['gwas_beta'] = beta_scaled
		twas_data['gwas_beta_se'] = beta_se_scaled

		# Extract ordered tissues for this component
		component_tissues = []
		for gene_full_name in twas_data['genes']:
			component_tissues.append('_'.join(gene_full_name.split('_')[1:]))
		component_tissues = np.asarray(component_tissues)

		# Extract ordered gene prior variances for this component
		ordered_gene_prior_variances = []
		for component_tissue in component_tissues:
			prior_var = tissue_specific_prior_expected_variance[tissue_to_position_mapping[component_tissue]]
			ordered_gene_prior_variances.append(prior_var)
		ordered_gene_prior_variances = np.asarray(ordered_gene_prior_variances)

		# RUN TGFM CAUSAL TWAS
		#twas_obj = tgfm_causal_twas.TGFM_CAUSAL_TWAS(estimate_prior_variance=True, convergence_thresh=1e-6)
		twas_obj = tgfm_causal_twas.TGFM_CAUSAL_TWAS(estimate_prior_variance=False, prior_variance_vector=ordered_gene_prior_variances, convergence_thresh=1e-6)
		twas_obj.fit(twas_data_obj=twas_data)

		# Prepare data for TGFM fine mapping
		tgfm_fine_mapping_data = {'gwas_component_pmces': gwas_component_susie_pmces, 'gwas_susie_mu': gwas_susie_mu, 'gwas_susie_mu_sd': gwas_susie_mu_sd, 'gwas_susie_alpha': gwas_susie_alpha, 'eqtl_pmces': get_eqtl_component_level_pmces(twas_data['susie_mu'], twas_data['susie_alpha']), 'eqtl_mu':twas_data['susie_mu'], 'eqtl_mu_sd': twas_data['susie_mu_sd'], 'eqtl_alpha':twas_data['susie_alpha'], 'twas_alpha': twas_obj.alpha_mu, 'twas_alpha_sd': np.sqrt(twas_obj.alpha_var), 'genes': twas_data['genes'], 'variants': twas_data['variants'], 'ordered_tissue_names': ordered_tissue_names}
		# Run TGFM fine mapping
		tgfm_fm_obj = tgfm_fine_mapping.TGFM_FM()
		tgfm_fm_obj.fit(fm_data_obj=tgfm_fine_mapping_data)


		# Save TWAS results to output file
		tgfm_twas_pkl_file = output_dir + trait_name + '_' + component_name + '_tgfm_twas_tissue_specific_prior_results.pkl'
		g = open(tgfm_twas_pkl_file, "wb")
		pickle.dump(twas_obj, g)
		g.close()	

		# Save Fine-mapping results to output files
		tgfm_fm_results_table_file = output_dir + trait_name + '_' + component_name + '_tgfm_fine_mapping_tissue_specific_prior_table.txt'
		tgfm_fm_obj.posterior_prob_df.to_csv(tgfm_fm_results_table_file, sep='\t', index=False)
		tgfm_tissue_fm_results_table_file = output_dir + trait_name + '_' + component_name + '_tgfm_tissue_fine_mapping_tissue_specific_prior_table.txt'
		tgfm_fm_obj.tissue_posterior_prob_df.to_csv(tgfm_tissue_fm_results_table_file, sep='\t', index=False)	

		# Write output files to component level output
		t.write(component_name + '\t' + str(num_genes) + '\t' + tgfm_twas_pkl_file + '\t' + tgfm_fm_results_table_file + '\t' + tgfm_tissue_fm_results_table_file + '\t' + pickled_data_file + '\n')

f.close()
t.close()

'''