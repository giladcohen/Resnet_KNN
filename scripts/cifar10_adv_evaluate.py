from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import logging
import numpy as np
import tensorflow as tf
import os

import darkon.darkon as darkon

from cleverhans.attacks import FastGradientMethod, DeepFool
from tensorflow.python.platform import flags
import darkon_examples.cifar10_resnet.cifar10_input as cifar10_input
from cleverhans.loss import CrossEntropy, WeightDecay, WeightedSum
from tensorflow_TB.lib.models.darkon_replica_model import DarkonReplica
from cleverhans.utils import AccuracyReport, set_log_level
from cleverhans.utils_tf import model_eval
from tensorflow_TB.utils.misc import one_hot
from sklearn.neighbors import NearestNeighbors
import matplotlib.pyplot as plt
from tensorflow_TB.lib.datasets.influence_feeder_val_test import MyFeederValTest
from tensorflow_TB.utils.misc import np_evaluate
import pickle

FLAGS = flags.FLAGS

flags.DEFINE_integer('batch_size', 125, 'Size of training batches')
flags.DEFINE_float('weight_decay', 0.0004, 'weight decay')
flags.DEFINE_string('checkpoint_name', 'log_080419_b_125_wd_0.0004_mom_lr_0.1_f_0.9_p_3_c_2_val_size_1000', 'checkpoint name')
flags.DEFINE_float('label_smoothing', 0.1, 'label smoothing')
flags.DEFINE_string('workspace', 'influence_workspace_validation', 'workspace dir')
flags.DEFINE_bool('prepare', True, 'whether or not we are in the prepare phase, when hvp is calculated')

# cifar-10 classes
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

# Get CIFAR-10 data
cifar10_input.maybe_download_and_extract()

# get records from training
model_dir     = os.path.join('/data/gilad/logs/influence', FLAGS.checkpoint_name)
workspace_dir = os.path.join(model_dir, FLAGS.workspace)

save_val_inds = False
if os.path.isfile(os.path.join(model_dir, 'val_indices.npy')):
    print('re-using val indices from {}'.format(os.path.join(model_dir, 'val_indices.npy')))
    val_indices = np.load(os.path.join(model_dir, 'val_indices.npy'))
else:
    val_indices = None
    save_val_inds = True
feeder = MyFeederValTest(rand_gen=rand_gen, as_one_hot=True, val_inds=val_indices, test_val_set=False)
if save_val_inds:
    print('saving new val indices to'.format(os.path.join(model_dir, 'val_indices.npy')))
    np.save(os.path.join(model_dir, 'val_indices.npy'), feeder.val_inds)

# get the data
X_train, y_train       = feeder.train_indices(range(feeder.get_train_size()))
X_val, y_val           = feeder.val_indices(range(feeder.get_val_size()))
X_test, y_test         = feeder.test_indices(range(feeder.get_test_size()))  # for the validation testing
y_train_sparse         = y_train.argmax(axis=-1).astype(np.int32)
y_val_sparse           = y_val.argmax(axis=-1).astype(np.int32)
y_test_sparse          = y_test.argmax(axis=-1).astype(np.int32)

# Use Image Parameters
img_rows, img_cols, nchannels = X_test.shape[1:4]
nb_classes = y_test.shape[1]

# Define input TF placeholder
x = tf.placeholder(tf.float32, shape=(None, img_rows, img_cols, nchannels))
y = tf.placeholder(tf.float32, shape=(None, nb_classes))

eval_params = {'batch_size': FLAGS.batch_size}
fgsm_params = {
    'eps': 0.3,
    'clip_min': 0.,
    'clip_max': 1.
}
deepfool_params = {
    'clip_min': 0.0,
    'clip_max': 1.0
}

model = DarkonReplica(scope='model1', nb_classes=10, n=5, input_shape=[32, 32, 3])
preds      = model.get_predicted_class(x)
logits     = model.get_logits(x)
embeddings = model.get_embeddings(x)

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

# loading the checkpoint
saver = tf.train.Saver()
checkpoint_path = os.path.join(model_dir, 'best_model.ckpt')
saver.restore(sess, checkpoint_path)

# predict labels from trainset
if not os.path.isfile(os.path.join(model_dir, 'x_train_preds.npy')):
    x_train_preds, x_train_features = np_evaluate(sess, [preds, embeddings], X_train, y_train, x, y, FLAGS.batch_size, log=logging)
    x_train_preds = x_train_preds.astype(np.int32)
    np.save(os.path.join(model_dir, 'x_train_preds.npy'), x_train_preds)
    np.save(os.path.join(model_dir, 'x_train_features.npy'), x_train_features)
else:
    x_train_preds    = np.load(os.path.join(model_dir, 'x_train_preds.npy'))
    x_train_features = np.load(os.path.join(model_dir, 'x_train_features.npy'))

# predict labels from validation set
if not os.path.isfile(os.path.join(model_dir, 'x_val_preds.npy')):
    x_val_preds, x_val_features = np_evaluate(sess, [preds, embeddings], X_val, y_val, x, y, FLAGS.batch_size, log=logging)
    x_val_preds = x_val_preds.astype(np.int32)
    np.save(os.path.join(model_dir, 'x_val_preds.npy'), x_val_preds)
    np.save(os.path.join(model_dir, 'x_val_features.npy'), x_val_features)
else:
    x_val_preds    = np.load(os.path.join(model_dir, 'x_val_preds.npy'))
    x_val_features = np.load(os.path.join(model_dir, 'x_val_features.npy'))

# predict labels from test set
if not os.path.isfile(os.path.join(model_dir, 'x_test_preds.npy')):
    x_test_preds, x_test_features = np_evaluate(sess, [preds, embeddings], X_test, y_test, x, y, FLAGS.batch_size, log=logging)
    x_test_preds = x_test_preds.astype(np.int32)
    np.save(os.path.join(model_dir, 'x_test_preds.npy'), x_test_preds)
    np.save(os.path.join(model_dir, 'x_test_features.npy'), x_test_features)
else:
    x_test_preds    = np.load(os.path.join(model_dir, 'x_test_preds.npy'))
    x_test_features = np.load(os.path.join(model_dir, 'x_test_features.npy'))

# Initialize the advarsarial attack object and graph
attack         = DeepFool(model, sess=sess)
adv_x          = attack.generate(x, **deepfool_params)
preds_adv      = model.get_predicted_class(adv_x)
logits_adv     = model.get_logits(adv_x)
embeddings_adv = model.get_embeddings(adv_x)

if not os.path.isfile(os.path.join(model_dir, 'X_val_adv.npy')):
    # Evaluate the accuracy of the CIFAR-10 model on adversarial examples
    X_val_adv, x_val_preds_adv, x_val_features_adv = np_evaluate(sess, [adv_x, preds_adv, embeddings_adv], X_val, y_val, x, y, FLAGS.batch_size, log=logging)
    x_val_preds_adv = x_val_preds_adv.astype(np.int32)
    # since DeepFool is not reproducible, saving the results in as numpy
    np.save(os.path.join(model_dir, 'X_val_adv.npy'), X_val_adv)
    np.save(os.path.join(model_dir, 'x_val_preds_adv.npy'), x_val_preds_adv)
    np.save(os.path.join(model_dir, 'x_val_features_adv.npy'), x_val_features_adv)
else:
    X_val_adv          = np.load(os.path.join(model_dir, 'X_val_adv.npy'))
    x_val_preds_adv    = np.load(os.path.join(model_dir, 'x_val_preds_adv.npy'))
    x_val_features_adv = np.load(os.path.join(model_dir, 'x_val_features_adv.npy'))

if not os.path.isfile(os.path.join(model_dir, 'X_test_adv.npy')):
    # Evaluate the accuracy of the CIFAR-10 model on adversarial examples
    X_test_adv, x_test_preds_adv, x_test_features_adv = np_evaluate(sess, [adv_x, preds_adv, embeddings_adv], X_test, y_test, x, y, FLAGS.batch_size, log=logging)
    x_test_preds_adv = x_test_preds_adv.astype(np.int32)
    # since DeepFool is not reproducible, saving the results in as numpy
    np.save(os.path.join(model_dir, 'X_test_adv.npy'), X_test_adv)
    np.save(os.path.join(model_dir, 'x_test_preds_adv.npy'), x_test_preds_adv)
    np.save(os.path.join(model_dir, 'x_test_features_adv.npy'), x_test_features_adv)
else:
    X_test_adv          = np.load(os.path.join(model_dir, 'X_test_adv.npy'))
    x_test_preds_adv    = np.load(os.path.join(model_dir, 'x_test_preds_adv.npy'))
    x_test_features_adv = np.load(os.path.join(model_dir, 'x_test_features_adv.npy'))

# accuracy computation
# do_eval(logits, X_train, y_train, 'clean_train_clean_eval_trainset', False)
# do_eval(logits, X_val, y_val, 'clean_train_clean_eval_validationset', False)
# do_eval(logits, X_test, y_test, 'clean_train_clean_eval_testset', False)
# do_eval(logits_adv, X_val, y_val, 'clean_train_adv_eval_validationset', True)
# do_eval(logits_adv, X_test, y_test, 'clean_train_adv_eval_testset', True)

# quick computations
train_acc    = np.mean(y_train_sparse == x_train_preds)
val_acc      = np.mean(y_val_sparse   == x_val_preds)
test_acc     = np.mean(y_test_sparse  == x_test_preds)
val_adv_acc  = np.mean(y_val_sparse   == x_val_preds_adv)
test_adv_acc = np.mean(y_test_sparse  == x_test_preds_adv)
print('train set acc: {}\nvalidation set acc: {}\ntest set acc: {}'.format(train_acc, val_acc, test_acc))
print('adversarial validation set acc: {}\nadversarial test set acc: {}'.format(val_adv_acc, test_adv_acc))

# what are the indices of the cifar10 set which the network succeeded classifying correctly,
# but the adversarial attack changed to a different class?
info = {}
info['val'] = {}
for i, set_ind in enumerate(feeder.val_inds):
    info['val'][i] = {}
    net_succ    = x_val_preds[i] == y_val_sparse[i]
    attack_succ = x_val_preds[i] != x_val_preds_adv[i]
    info['val'][i]['global_index'] = set_ind
    info['val'][i]['net_succ']     = net_succ
    info['val'][i]['attack_succ']  = attack_succ
info['test'] = {}
for i, set_ind in enumerate(feeder.test_inds):
    info['test'][i] = {}
    net_succ    = x_test_preds[i] == y_test_sparse[i]
    attack_succ = x_test_preds[i] != x_test_preds_adv[i]
    info['test'][i]['global_index'] = set_ind
    info['test'][i]['net_succ']     = net_succ
    info['test'][i]['attack_succ']  = attack_succ

info_file = os.path.join(model_dir, 'info.pkl')
if not os.path.isfile(info_file):
    print('saving info as pickle to {}'.format(info_file))
    with open(info_file, 'wb') as handle:
        pickle.dump(info, handle, protocol=pickle.HIGHEST_PROTOCOL)
else:
    print('loading info as pickle from {}'.format(info_file))
    with open(info_file, 'rb') as handle:
        info_old = pickle.load(handle)
    assert info == info_old








# net_succ_attack_succ = []
# net_succ_attack_succ_inds = []
# for i, set_ind in enumerate(feeder.test_inds):
#     net_succ    = x_test_preds[i] == y_test_sparse[i]
#     attack_succ = x_test_preds[i] != x_test_preds_adv[i]
#     if net_succ and attack_succ:
#         net_succ_attack_succ.append(i)
#         net_succ_attack_succ_inds.append(set_ind)
# net_succ_attack_succ      = np.asarray(net_succ_attack_succ     , dtype=np.int32)
# net_succ_attack_succ_inds = np.asarray(net_succ_attack_succ_inds, dtype=np.int32)
#
# # verify everything is ok
# if os.path.isfile(os.path.join(model_dir, relevant_indices_str + '.npy')):
#     # assert match
#     net_succ_attack_succ_old      = np.load(os.path.join(model_dir, relevant_indices_str + '.npy'))
#     net_succ_attack_succ_inds_old = np.load(os.path.join(model_dir, relevant_indices_str + '_inds.npy'))
#     assert (net_succ_attack_succ_old      == net_succ_attack_succ).all()
#     assert (net_succ_attack_succ_inds_old == net_succ_attack_succ_inds).all()
# else:
#     np.save(os.path.join(model_dir, relevant_indices_str + '.npy')     , net_succ_attack_succ)
#     np.save(os.path.join(model_dir, relevant_indices_str + '_inds.npy'), net_succ_attack_succ_inds)

# Due to lack of time, we can also sample 5 inputs of each class. Here we randomly select them...
# test_indices = []
# for cls in range(len(_classes)):
#     cls_test_indices = []
#     got_so_far = 0
#     while got_so_far < 5:
#         cls_test_index = rand_gen.choice(np.where(y_test_sparse == cls)[0])
#         if cls_test_index in net_succ_attack_succ:
#             cls_test_indices.append(cls_test_index)
#             got_so_far += 1
#     test_indices.extend(cls_test_indices)
# optional: divide test indices
# test_indices = test_indices[b:e]

# start the knn observation
knn = NearestNeighbors(n_neighbors=feeder.get_train_size(), p=2, n_jobs=20)
knn.fit(x_train_features)
all_neighbor_dists, all_neighbor_indices = knn.kneighbors(x_test_features, return_distance=True)

# setting adv feeder
adv_feeder = MyFeederValTest(rand_gen=rand_gen, as_one_hot=True, val_inds=feeder.val_inds, test_val_set=False)
adv_feeder.test_origin_data = X_test_adv
adv_feeder.test_data        = X_test_adv
adv_feeder.test_label       = one_hot(x_test_preds_adv, 10).astype(np.float32)

# now finding the influence
feeder.reset()
adv_feeder.reset()

inspector = darkon.Influence(
    workspace=os.path.join(model_dir, FLAGS.workspace, 'real'),
    feeder=feeder,
    loss_op_train=full_loss.fprop(x=x, y=y),
    loss_op_test=loss.fprop(x=x, y=y),
    x_placeholder=x,
    y_placeholder=y)

inspector_adv = darkon.Influence(
    workspace=os.path.join(model_dir, FLAGS.workspace, 'adv'),
    feeder=adv_feeder,
    loss_op_train=full_loss.fprop(x=x, y=y),
    loss_op_test=loss.fprop(x=x, y=y),
    x_placeholder=x,
    y_placeholder=y)

testset_batch_size = 100
train_batch_size = 100
train_iterations = 490  # int(feeder.get_train_size()/train_batch_size)  # was 500 wo validation

approx_params = {
    'scale': 200,
    'num_repeats': 5,
    'recursion_depth': 98,
    'recursion_batch_size': 100
}

print('done')
exit(0)
# go from last to beginning:
# net_succ_attack_succ = net_succ_attack_succ[::-1]

b, e = 0, 250
net_succ_attack_succ = net_succ_attack_succ[b:e]
net_succ_attack_succ_inds = net_succ_attack_succ_inds[b:e]

for i, sub_val_index in enumerate(net_succ_attack_succ):
    validation_index = feeder.val_inds[sub_val_index]
    assert validation_index == net_succ_attack_succ_inds[i]
    real_label = y_val_sparse[sub_val_index]
    adv_label  = x_val_preds_adv[sub_val_index]
    assert real_label != adv_label

    progress_str = 'sample {}/{}: calculating scores for val index {} (sub={}). real label: {}, adv label: {}'\
        .format(i+1, len(net_succ_attack_succ), validation_index, sub_val_index, _classes[real_label], _classes[adv_label])
    logging.info(progress_str)
    print(progress_str)

    for case in ['real', 'adv']:
        if case == 'real':
            insp = inspector
            feed = feeder
        elif case == 'adv':
            insp = inspector_adv
            feed = adv_feeder
        else:
            raise AssertionError('only real and adv are accepted.')

        # creating the relevant index folders
        dir = os.path.join(model_dir, 'val_index_{}'.format(validation_index), case)
        if not os.path.exists(dir):
            os.makedirs(dir)

        if FLAGS.prepare:
            insp._prepare(
                sess=sess,
                test_indices=[sub_val_index],
                test_batch_size=testset_batch_size,
                approx_params=approx_params,
                force_refresh=False
            )
            continue

        if os.path.isfile(os.path.join(dir, 'scores.npy')):
            print('loading scores from {}'.format(os.path.join(dir, 'scores.npy')))
            scores = np.load(os.path.join(dir, 'scores.npy'))
        else:
            scores = insp.upweighting_influence_batch(
                sess=sess,
                test_indices=[sub_val_index],
                test_batch_size=testset_batch_size,
                approx_params=approx_params,
                train_batch_size=train_batch_size,
                train_iterations=train_iterations)
            np.save(os.path.join(dir, 'scores.npy'), scores)

        if not os.path.isfile(os.path.join(dir, 'image.npy')):
            print('saving image {}'.format(os.path.join(dir, 'image.npy')))
            np.save(os.path.join(dir, 'image.npy'), feed.val_inds[sub_val_index])
        else:
            # verifying everything is good
            assert (np.load(os.path.join(dir, 'image.npy')) == feed.val_inds[sub_val_index]).all()

        sorted_indices = np.argsort(scores)
        harmful = sorted_indices[:50]
        helpful = sorted_indices[-50:][::-1]

        # have some figures
        cnt_harmful_in_knn = 0
        print('\nHarmful:')
        for idx in harmful:
            print('[{}] {}'.format(feed.train_inds[idx], scores[idx]))
            if idx in all_neighbor_indices[sub_val_index, 0:50]:
                cnt_harmful_in_knn += 1
        harmful_summary_str = '{}: {} out of {} harmful images are in the {}-NN\n'.format(case, cnt_harmful_in_knn, len(harmful), 50)
        print(harmful_summary_str)

        cnt_helpful_in_knn = 0
        print('\nHelpful:')
        for idx in helpful:
            print('[{}] {}'.format(feed.train_inds[idx], scores[idx]))
            if idx in all_neighbor_indices[sub_val_index, 0:50]:
                cnt_helpful_in_knn += 1
        helpful_summary_str = '{}: {} out of {} helpful images are in the {}-NN\n'.format(case, cnt_helpful_in_knn, len(helpful), 50)
        print(helpful_summary_str)

        fig, axes1 = plt.subplots(5, 10, figsize=(30, 10))
        target_idx = 0
        for j in range(5):
            for k in range(10):
                idx = all_neighbor_indices[sub_val_index, target_idx]
                axes1[j][k].set_axis_off()
                axes1[j][k].imshow(X_train[idx])
                label_str = _classes[y_train_sparse[idx]]
                axes1[j][k].set_title('[{}]: {}'.format(feed.train_inds[idx], label_str))
                target_idx += 1
        plt.savefig(os.path.join(dir, 'nearest_neighbors.png'), dpi=350)
        plt.close()

        # calculate 1000 knn_ranks
        def find_ranks(sub_val_index, sorted_influence_indices):
            ranks = -1 * np.ones(1000, dtype=np.int32)
            dists = -1 * np.ones(1000, dtype=np.float32)
            for target_idx in range(ranks.shape[0]):
                idx = sorted_influence_indices[target_idx]
                loc_in_knn = np.where(all_neighbor_indices[sub_val_index] == idx)[0][0]
                knn_dist = all_neighbor_dists[sub_val_index, loc_in_knn]
                ranks[target_idx] = loc_in_knn
                dists[target_idx] = knn_dist
            return ranks, dists

        helpful_ranks, helpful_dists = find_ranks(sub_val_index, sorted_indices[-1000:][::-1])
        harmful_ranks, harmful_dists = find_ranks(sub_val_index, sorted_indices[:1000])

        if not os.path.isfile(os.path.join(dir, 'helpful_ranks.npy')):
            print('saving knn ranks and dists to {}'.format(dir))
            np.save(os.path.join(dir, 'helpful_ranks.npy'), helpful_ranks)
            np.save(os.path.join(dir, 'helpful_dists.npy'), helpful_dists)
            np.save(os.path.join(dir, 'harmful_ranks.npy'), harmful_ranks)
            np.save(os.path.join(dir, 'harmful_dists.npy'), harmful_dists)
        else:
            # verifying everything is good
            assert (np.load(os.path.join(dir, 'helpful_ranks.npy')) == helpful_ranks).all()
            assert (np.load(os.path.join(dir, 'helpful_dists.npy')) == helpful_dists).all()
            assert (np.load(os.path.join(dir, 'harmful_ranks.npy')) == harmful_ranks).all()
            assert (np.load(os.path.join(dir, 'harmful_dists.npy')) == harmful_dists).all()

        fig, axes1 = plt.subplots(5, 10, figsize=(30, 10))
        target_idx = 0
        for j in range(5):
            for k in range(10):
                idx = helpful[target_idx]
                axes1[j][k].set_axis_off()
                axes1[j][k].imshow(X_train[idx])
                label_str = _classes[y_train_sparse[idx]]
                loc_in_knn = np.where(all_neighbor_indices[sub_val_index] == idx)[0][0]
                axes1[j][k].set_title('[{}]: {} #nn:{}'.format(idx, label_str, loc_in_knn))
                target_idx += 1
        plt.savefig(os.path.join(dir, 'helpful.png'), dpi=350)
        plt.close()

        fig, axes1 = plt.subplots(5, 10, figsize=(30, 10))
        target_idx = 0
        for j in range(5):
            for k in range(10):
                idx = harmful[target_idx]
                axes1[j][k].set_axis_off()
                axes1[j][k].imshow(X_train[idx])
                label_str = _classes[y_train_sparse[idx]]
                loc_in_knn = np.where(all_neighbor_indices[sub_val_index] == idx)[0][0]
                axes1[j][k].set_title('[{}]: {} #nn:{}'.format(idx, label_str, loc_in_knn))
                target_idx += 1
        plt.savefig(os.path.join(dir, 'harmful.png'), dpi=350)
        plt.close()

        # getting two ranks - one rank for the real label and another rank for the adv label.
        # what is a "rank"?
        # A rank is the average nearest neighbor location of all the helpful training indices.
        with open(os.path.join(dir, 'summary.txt'), 'w+') as f:
            f.write(harmful_summary_str)
            f.write(helpful_summary_str)
            f.write('label ({} -> {}) {} \nhelpful/harmful_rank mean: {}/{}\nhelpful/harmful_dist mean: {}/{}' \
                    .format(_classes[real_label], _classes[adv_label], case,
                            helpful_ranks.mean(), harmful_ranks.mean(), helpful_dists.mean(), harmful_dists.mean()))
