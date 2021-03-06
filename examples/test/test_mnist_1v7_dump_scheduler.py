import subprocess
import time
import numpy as np
import os

def run_cmd(cmd):
    print ('start running command {}'.format(cmd))
    process = subprocess.call(cmd, shell=True)
    print ('finished running command {}'.format(cmd))
    time.sleep(3)


n_vec = np.arange(1, 13)

for n in n_vec:
    logdir = '/data/gilad/logs/knn_bayes/wrn/mnist_1v7/w_dropout/log_bs_200_lr_0.1s_n_{}k-SUPERSEED=08011900'.format(n)
    train_validation_info = os.path.join(logdir, 'train_validation_info.csv')
    cmd = 'CUDA_VISIBLE_DEVICES=3 python scripts/test_automated.py' + \
          ' --ROOT_DIR ' + logdir + \
          ' --PCA_REDUCTION False' + \
          ' --CHECKPOINT_FILE ' + 'model_schedule.ckpt-3000' + \
          ' --TRAIN_VALIDATION_MAP_REF ' + train_validation_info + \
          ' -c examples/test/test_simple_mnist_1v7.ini'
    run_cmd(cmd)

print('end of script.')
