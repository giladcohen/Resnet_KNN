from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import logging
import numpy as np
import tensorflow as tf
import os

from cleverhans.attacks import FastGradientMethod
from cleverhans.augmentation import random_horizontal_flip, random_shift
from tensorflow.python.platform import flags
from cleverhans.loss import CrossEntropy, WeightDecay, WeightedSum
from tensorflow_TB.lib.models.darkon_replica_model import DarkonReplica
from tensorflow_TB.cleverhans_alias.train_alias import train
from cleverhans.utils import AccuracyReport, set_log_level
from cleverhans.utils_tf import model_eval
from tensorflow_TB.lib.datasets.influence_feeder_val_test import MyFeederValTest

FLAGS = flags.FLAGS

flags.DEFINE_integer('nb_epochs', 200, 'Number of epochs to train model')
flags.DEFINE_integer('batch_size', 125, 'Size of training batches')
flags.DEFINE_float('weight_decay', 0.0004, 'weight decay')
flags.DEFINE_string('optimizer', 'mom', 'optimizer')
flags.DEFINE_float('learning_rate', 0.1, 'Learning rate for training')
flags.DEFINE_float('lr_factor', 0.9, 'A factor to decay a learning rate')
flags.DEFINE_integer('lr_patience', 3, 'epochs with no metric improvements')
flags.DEFINE_integer('lr_cooldown', 2, 'epochs in refractory period')
flags.DEFINE_string('checkpoint_name', 'svhn_mini/log_300519_b_125_wd_0.0004_mom_lr_0.1_f_0.9_p_3_c_2_val_size_1000', 'checkpoint name')
flags.DEFINE_float('label_smoothing', 0.1, 'label smoothing')
flags.DEFINE_string('dataset', 'svhn', 'dataset: cifar10/100 or svhn')

if FLAGS.dataset == 'cifar10':
    _classes = (
        'airplane',
        'car',
        'bird',
        'cat',
        'deer',
        'dog',
        'frog',
        'horse',
        'ship',
        'truck'
    )
    ARCH_NAME = 'model1'
elif FLAGS.dataset == 'cifar100':
    _classes = (
        'apple', 'aquarium_fish', 'baby', 'bear', 'beaver', 'bed', 'bee', 'beetle',
        'bicycle', 'bottle', 'bowl', 'boy', 'bridge', 'bus', 'butterfly', 'camel',
        'can', 'castle', 'caterpillar', 'cattle', 'chair', 'chimpanzee', 'clock',
        'cloud', 'cockroach', 'couch', 'crab', 'crocodile', 'cup', 'dinosaur',
        'dolphin', 'elephant', 'flatfish', 'forest', 'fox', 'girl', 'hamster',
        'house', 'kangaroo', 'keyboard', 'lamp', 'lawn_mower', 'leopard', 'lion',
        'lizard', 'lobster', 'man', 'maple_tree', 'motorcycle', 'mountain', 'mouse',
        'mushroom', 'oak_tree', 'orange', 'orchid', 'otter', 'palm_tree', 'pear',
        'pickup_truck', 'pine_tree', 'plain', 'plate', 'poppy', 'porcupine',
        'possum', 'rabbit', 'raccoon', 'ray', 'road', 'rocket', 'rose',
        'sea', 'seal', 'shark', 'shrew', 'skunk', 'skyscraper', 'snail', 'snake',
        'spider', 'squirrel', 'streetcar', 'sunflower', 'sweet_pepper', 'table',
        'tank', 'telephone', 'television', 'tiger', 'tractor', 'train', 'trout',
        'tulip', 'turtle', 'wardrobe', 'whale', 'willow_tree', 'wolf', 'woman', 'worm'
    )
    ARCH_NAME = 'model_cifar_100'
elif FLAGS.dataset == 'svhn':
    _classes = (
        '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'
    )
    ARCH_NAME = 'model_svhn'
else:
    raise AssertionError('dataset {} not supported'.format(FLAGS.dataset))

# Object used to keep track of (and return) key accuracies
report = AccuracyReport()

# Set TF random seed to improve reproducibility
superseed = 15101985
rand_gen = np.random.RandomState(superseed)
tf.set_random_seed(superseed)

# Set logging level to see debug information
set_log_level(logging.DEBUG)

# Create TF session
config_args = dict(allow_soft_placement=True)
sess = tf.Session(config=tf.ConfigProto(**config_args))

feeder = MyFeederValTest(dataset=FLAGS.dataset, rand_gen=rand_gen, as_one_hot=True, test_val_set=True)
model_dir = os.path.join('/data/gilad/logs/influence', FLAGS.checkpoint_name)
if not os.path.exists(model_dir):
    os.makedirs(model_dir)
np.save(os.path.join(model_dir, 'val_indices.npy'), feeder.val_inds)

# get the data
X_train, y_train       = feeder.train_indices(range(feeder.get_train_size()))
X_val, y_val           = feeder.val_indices(range(feeder.get_val_size()))
X_test, y_test         = feeder.test_data, feeder.test_label  # getting the real test set
y_train_sparse         = y_train.argmax(axis=-1).astype(np.int32)
y_val_sparse           = y_val.argmax(axis=-1).astype(np.int32)
y_test_sparse          = y_test.argmax(axis=-1).astype(np.int32)

dataset_size  = X_train.shape[0]
dataset_train = tf.data.Dataset.range(dataset_size)
dataset_train = dataset_train.shuffle(4096)
dataset_train = dataset_train.repeat()

def lookup(p):
    return X_train[p], y_train[p]
dataset_train = dataset_train.map(lambda i: tf.py_func(lookup, [i], [tf.float32] * 2))

dataset_train = dataset_train.map(lambda x, y: (random_shift(random_horizontal_flip(x)), y), 4)
dataset_train = dataset_train.batch(FLAGS.batch_size)
dataset_train = dataset_train.prefetch(16)

# Use Image Parameters
img_rows, img_cols, nchannels = X_val.shape[1:4]
nb_classes = y_val.shape[1]

# Define input TF placeholder
x = tf.placeholder(tf.float32, shape=(None, img_rows, img_cols, nchannels))
y = tf.placeholder(tf.float32, shape=(None, nb_classes))

# Train a model
train_params = {
    'nb_epochs': FLAGS.nb_epochs,
    'batch_size': FLAGS.batch_size,
    'learning_rate': FLAGS.learning_rate,
    'lr_factor': FLAGS.lr_factor,
    'lr_patience': FLAGS.lr_patience,
    'lr_cooldown': FLAGS.lr_cooldown,
    'best_model_path': os.path.join(model_dir, 'best_model.ckpt')
}
eval_params = {'batch_size': FLAGS.batch_size}
fgsm_params = {
    'eps': 0.3,
    'clip_min': 0.,
    'clip_max': 1.
}

model = DarkonReplica(scope=ARCH_NAME, nb_classes=feeder.num_classes, n=5, input_shape=[32, 32, 3])
logits = model.get_logits(x)
loss = CrossEntropy(model, smoothing=FLAGS.label_smoothing)
regu_losses = WeightDecay(model)
full_loss = WeightedSum(model, [(1.0, loss), (FLAGS.weight_decay, regu_losses)])

def do_eval(preds, x_set, y_set, report_key, is_adv=None):
    acc = model_eval(sess, x, y, preds, x_set, y_set, args=eval_params)
    setattr(report, report_key, acc)
    if is_adv is None:
        report_text = None
    elif is_adv:
        report_text = 'adversarial'
    else:
        report_text = 'legitimate'
    if report_text:
        print('Test accuracy on %s examples: %0.4f' % (report_text, acc))
    return acc

def evaluate():
    return do_eval(logits, X_val, y_val, 'clean_train_clean_eval', False)


train(sess, full_loss, None, None,
      dataset_train=dataset_train, dataset_size=dataset_size,
      evaluate=evaluate, args=train_params, rng=rand_gen,
      var_list=model.get_params(),
      optimizer=FLAGS.optimizer)

save_path = os.path.join(model_dir, "model_checkpoint.ckpt")
saver = tf.train.Saver()
saver.save(sess, save_path, global_step=tf.train.get_global_step())

# print best score
evaluate()

# Initialize the Fast Gradient Sign Method (FGSM) attack object and graph
fgsm = FastGradientMethod(model, sess=sess)
adv_x = fgsm.generate(x, **fgsm_params)
logits_adv = model.get_logits(adv_x)

# Evaluate the accuracy of the CIFAR-10 model on adversarial examples
do_eval(logits_adv, X_val, y_val, 'clean_train_adv_eval', True)

print('done')