from utils.plots import load_data_from_csv_wrapper, add_subplot_axes
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import os
import json

plt.rcParams['interactive'] = False
subpos = np.array([0.35, 0.25, 0.5, 0.4])
fig = plt.figure(figsize=(15.0, 8.0))

# setting all experiments
all_ks = [1, 3, 4, 5, 6, 7, 8, 9, 10,
          12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40,
          45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100,
          110, 120, 130, 140, 150, 160, 170, 180, 190, 200,
          220, 240, 260, 280, 300,
          350, 400, 450, 500,
          600, 700, 800, 900, 1000]

logdir_vec = [
    '/data/gilad/logs/knn_bayes/wrn/cifar10/log_bs_200_lr_0.1s_n_0.2k-SUPERSEED=19121800',
    '/data/gilad/logs/knn_bayes/wrn/cifar10/log_bs_200_lr_0.1s_n_0.3k-SUPERSEED=19121800',
    '/data/gilad/logs/knn_bayes/wrn/cifar10/log_bs_200_lr_0.1s_n_0.4k-SUPERSEED=19121800',
    '/data/gilad/logs/knn_bayes/wrn/cifar10/log_bs_200_lr_0.1s_n_0.5k-SUPERSEED=19121800',
    '/data/gilad/logs/knn_bayes/wrn/cifar10/log_bs_200_lr_0.1s_n_0.6k-SUPERSEED=19121800',
    '/data/gilad/logs/knn_bayes/wrn/cifar10/log_bs_200_lr_0.1s_n_0.7k-SUPERSEED=19121800',
    '/data/gilad/logs/knn_bayes/wrn/cifar10/log_bs_200_lr_0.1s_n_0.8k-SUPERSEED=19121800',
    '/data/gilad/logs/knn_bayes/wrn/cifar10/log_bs_200_lr_0.1s_n_0.9k-SUPERSEED=19121800',
]
n_vec = [200, 300, 400, 500, 600, 700, 800, 900]
max_ks = [20 , 30 , 40 , 50 , 60 , 70 , 80 , 90]

for i in range(1, 51):
    if i in [4, 13]:  # not ready yet
        continue
    logdir_vec.append('/data/gilad/logs/knn_bayes/wrn/cifar10/log_bs_200_lr_0.1s_n_{}k-SUPERSEED=19121800'.format(i))
    n_vec.append(int(i * 1000))
    max_ks.append(int(i * 100))

knn_error_rate = []
optimal_k      = []
for i, root_dir in enumerate(logdir_vec):
    json_file = os.path.join(root_dir, 'data_for_figures', 'data.json')
    max_k = max_ks[i]
    with open(json_file) as f:
        data = json.load(f)
    best_error_rate = np.inf
    best_k          = None
    for k in all_ks:
        if k <= max_k:
            # measure = 'knn_k_{}_norm_L2_knn_score'.format(k)
            measure = 'knn_k_{}_norm_L2_knn_kl_div2_median'.format(k)
            # error_rate = 1.0 - data['test']['regular'][measure]['values'][0]
            error_rate = data['test']['regular'][measure]['values'][0]
            if error_rate < best_error_rate:
                best_error_rate = error_rate
                best_k = k
    knn_error_rate.append(best_error_rate)
    optimal_k.append(best_k)

ax1 = fig.add_subplot(211)
ax1.plot(n_vec, knn_error_rate)
ax1.yaxis.grid()
ax1.set_ylabel('k-NN error rate', labelpad=5, fontdict={'fontsize': 12})
ax1.set_xlabel('number of samples')
ax1.set_title('KNN error rate for optimal K (max knn_score)')

ax2 = fig.add_subplot(212)
ax2.plot(n_vec, optimal_k)
ax2.yaxis.grid()
ax2.set_ylabel('optimal k', labelpad=5, fontdict={'fontsize': 12})
ax2.set_xlabel('number of samples')
# ax2.set_ylim(top=100)
ax2.set_title('optimal K (max knn_score)')

plt.tight_layout()
plt.savefig('knn_error_rate_optimal_k_max_knn_score.png')

