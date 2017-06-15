
"""ResNet Train/Eval module.
"""
import time
import six
import sys
sys.path.append('/Users/giladcohen/workspace/Resnet_KNN/lib') #for debug
import active_input
import cifar_input
import tf_utils
import numpy as np
import resnet_model
import tensorflow as tf
from keras.datasets import cifar10, cifar100
import matplotlib.pyplot as plt #for debug
from sklearn.cluster import KMeans, k_means_
import random

flags = tf.app.flags
FLAGS = flags.FLAGS
flags.DEFINE_string('dataset', 'cifar10', 'cifar10 or cifar100.')
flags.DEFINE_string('mode', 'train', 'train or eval.')
flags.DEFINE_string('train_data_path', 'images.bin', 'Filepattern for training data.')
flags.DEFINE_string('eval_data_path', '', 'Filepattern for eval data')
flags.DEFINE_integer('image_size', 32, 'Image side length.')
flags.DEFINE_string('train_dir', '', 'Directory to keep training outputs.')
flags.DEFINE_string('eval_dir', '', 'Directory to keep eval outputs.')
flags.DEFINE_integer('eval_batch_count', 50, 'Number of batches to eval.')
flags.DEFINE_bool('eval_once', False, 'Whether evaluate the model only once.')
flags.DEFINE_string('log_root', '',
                           'Directory to keep the checkpoints. Should be a '
                           'parent directory of FLAGS.train_dir/eval_dir.')
flags.DEFINE_integer('num_gpus', 0, 'Number of gpus used for training. (0 or 1)')
flags.DEFINE_bool('active_learning', False, 'Use active learning')
flags.DEFINE_integer('batch_size', -1, 'batch size for train/test')
flags.DEFINE_integer('clusters', 128, 'batch size for train/test')

TRAIN_SET_SIZE = 50000
TEST_SET_SIZE  = 10000
ACTIVE_EPOCHS = 5

if (FLAGS.batch_size != -1):
    BATCH_SIZE = FLAGS.batch_size
elif (FLAGS.mode == 'train'):
  BATCH_SIZE=128
else:
  BATCH_SIZE=100

def update_pool(available_samples, pool, clusters=FLAGS.clusters):
    if (len(available_samples) < clusters):
        pool_tmp = available_samples
        print ('Adding %0d indices instead of %d to pool. pool is full' %(len(pool_tmp), clusters))
    else:
        pool_tmp = random.sample(available_samples, clusters)
    pool += pool_tmp
    pool = sorted(pool)
    available_samples = [i for j, i in enumerate(available_samples) if i not in pool]
    return available_samples, pool

def train(hps):
    """Training loop."""

    available_samples = range(TRAIN_SET_SIZE)
    pool = []
    available_samples, pool = update_pool(available_samples, pool)

    """Training loop. Step1 - selecting 128 randomized images"""
    (train_images, train_labels), (test_images, test_labels) = cifar10.load_data()
    pool = sorted(random.sample(range(TRAIN_SET_SIZE), BATCH_SIZE))
    tf_utils.convert_numpy_to_bin(train_images[pool], train_labels[pool], 'images.bin')

    images_raw, images, labels = active_input.build_input(FLAGS.dataset, FLAGS.train_data_path, BATCH_SIZE)
    model = resnet_model.ResNet(hps, images, labels, FLAGS.mode)
    model.build_graph()

    param_stats = tf.contrib.tfprof.model_analyzer.print_model_analysis(
        tf.get_default_graph(),
        tfprof_options=tf.contrib.tfprof.model_analyzer.
            TRAINABLE_VARS_PARAMS_STAT_OPTIONS)
    sys.stdout.write('total_params: %d\n' % param_stats.total_parameters)

    tf.contrib.tfprof.model_analyzer.print_model_analysis(
        tf.get_default_graph(),
        tfprof_options=tf.contrib.tfprof.model_analyzer.FLOAT_OPS_OPTIONS)

    truth = tf.argmax(model.labels, axis=1)
    predictions = tf.argmax(model.predictions, axis=1)
    precision = tf.reduce_mean(tf.to_float(tf.equal(predictions, truth)))

    summary_hook = tf.train.SummarySaverHook(
        save_steps=1, #was 100
        output_dir=FLAGS.train_dir,
        summary_op=tf.summary.merge([model.summaries,
                                     tf.summary.scalar('Precision', precision)]))

    logging_hook = tf.train.LoggingTensorHook(
        tensors={'step': model.global_step,
                 'loss': model.cost,
                 'precision': precision},
        every_n_iter=1) #was 100

    class _LearningRateSetterHook(tf.train.SessionRunHook):
        """Sets learning_rate based on global step."""

        def begin(self):
            self._lrn_rate = 0.1

        def before_run(self, run_context):
            return tf.train.SessionRunArgs(
                model.global_step,  # Asks for global step value.
                feed_dict={model.lrn_rate: self._lrn_rate})  # Sets learning rate

        def after_run(self, run_context, run_values):
            train_step = run_values.results
            epoch = (BATCH_SIZE*train_step) // TRAIN_SET_SIZE
            if epoch < 60:
                self._lrn_rate = 0.1
            elif epoch < 120:
                self._lrn_rate = 0.02
            elif epoch < 160:
                self._lrn_rate = 0.004
            else:
                self._lrn_rate = 0.0008

    sess = tf.train.MonitoredTrainingSession(
            checkpoint_dir=FLAGS.log_root,
            hooks=[logging_hook, _LearningRateSetterHook()],
            chief_only_hooks=[summary_hook],
            # Since we provide a SummarySaverHook, we need to disable default
            # SummarySaverHook. To do that we set save_summaries_steps to 0.
            save_summaries_steps=0,
            config=tf.ConfigProto(allow_soft_placement=True))

    if (FLAGS.active_learning == False):
        while not sess.should_stop():
            steps_to_go = ACTIVE_EPOCHS * (len(pool) / BATCH_SIZE)
            for i in range(steps_to_go):
                sess.run(model.train_op)
            print('updating pool from:')
            print(pool)
            available_samples, pool = update_pool(available_samples, pool)
            print('to:')
            print(pool)
            tf_utils.convert_numpy_to_bin(train_images[pool], train_labels[pool], 'images.bin')

def evaluate(hps):
  """Eval loop."""
  images_raw, images, labels = cifar_input.build_input(
      FLAGS.dataset, FLAGS.eval_data_path, hps.batch_size, FLAGS.mode)
  model = resnet_model.ResNet(hps, images, labels, FLAGS.mode)
  model.build_graph()
  saver = tf.train.Saver()
  summary_writer = tf.summary.FileWriter(FLAGS.eval_dir)

  sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True))
  tf.train.start_queue_runners(sess)

  best_precision = 0.0
  while True:
    try:
      ckpt_state = tf.train.get_checkpoint_state(FLAGS.log_root)
    except tf.errors.OutOfRangeError as e:
      tf.logging.error('Cannot restore checkpoint: %s', e)
      continue
    if not (ckpt_state and ckpt_state.model_checkpoint_path):
      tf.logging.info('No model to eval yet at %s', FLAGS.log_root)
      continue
    tf.logging.info('Loading checkpoint %s', ckpt_state.model_checkpoint_path)
    saver.restore(sess, ckpt_state.model_checkpoint_path)

    total_prediction, correct_prediction = 0, 0
    for _ in six.moves.range(FLAGS.eval_batch_count):
      (summaries, loss, predictions, truth, train_step) = sess.run(
          [model.summaries, model.cost, model.predictions,
           model.labels, model.global_step])

      truth = np.argmax(truth, axis=1)
      predictions = np.argmax(predictions, axis=1)
      correct_prediction += np.sum(truth == predictions)
      total_prediction += predictions.shape[0]

    precision = 1.0 * correct_prediction / total_prediction
    best_precision = max(precision, best_precision)

    precision_summ = tf.Summary()
    precision_summ.value.add(
        tag='Precision', simple_value=precision)
    summary_writer.add_summary(precision_summ, train_step)
    best_precision_summ = tf.Summary()
    best_precision_summ.value.add(
        tag='Best Precision', simple_value=best_precision)
    summary_writer.add_summary(best_precision_summ, train_step)
    summary_writer.add_summary(summaries, train_step)
    tf.logging.info('loss: %.4f, precision: %.4f, best precision: %.4f' %
                    (loss, precision, best_precision))
    summary_writer.flush()

    if FLAGS.eval_once:
      break

    time.sleep(60)


def main(_):
  if FLAGS.num_gpus == 0:
    dev = '/cpu:0'
  elif FLAGS.num_gpus == 1:
    dev = '/gpu:0'
  else:
    raise ValueError('Only support 0 or 1 gpu.')

  if FLAGS.dataset == 'cifar10':
    num_classes = 10
  elif FLAGS.dataset == 'cifar100':
    num_classes = 100

  hps = resnet_model.HParams(batch_size=BATCH_SIZE,
                             num_classes=num_classes,
                             min_lrn_rate=0.0001,
                             lrn_rate=0.1,
                             num_residual_units=4, #was 5 in source code
                             use_bottleneck=False,
                             weight_decay_rate=0.0005, #was 0.0002
                             relu_leakiness=0.1,
                             pool='gap', #use gap or mp
                             optimizer='mom',
                             use_nesterov=True)

  with tf.device(dev):
    if FLAGS.mode == 'train':
      train(hps)
    elif FLAGS.mode == 'eval':
      evaluate(hps)


if __name__ == '__main__':
  tf.logging.set_verbosity(tf.logging.INFO)
  tf.app.run()
