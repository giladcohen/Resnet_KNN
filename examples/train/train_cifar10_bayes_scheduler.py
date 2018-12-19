import subprocess
import time
import numpy as np

def run_cmd(cmd):
    print ('start running command {}'.format(cmd))
    process = subprocess.call(cmd, shell=True)
    print ('finished running command {}'.format(cmd))
    time.sleep(3)

n_vec = np.arange(1, 18)
for n in n_vec:
    logdir = '/data/gilad/logs/knn_bayes/wrn/cifar10/log_bs_200_lr_0.1s_n_{}k-SUPERSEED=19121800'.format(n)
    cmd = 'CUDA_VISIBLE_DEVICES=0 python scripts/train_automated.py' + \
          ' --ROOT_DIR ' + logdir + \
          ' --SUPERSEED ' + logdir[-8:] + \
          ' --TRAIN_SET_SIZE ' + str(n)+'000' + \
          ' --ARCHITECTURE ' + 'Wide-Resnet-28-10' \
          ' -c examples/train/train_simple_cifar10.ini'
    run_cmd(cmd)

print('end of script.')