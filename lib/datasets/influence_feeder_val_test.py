from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import numpy as np
import darkon.darkon as darkon
from tensorflow_TB.utils.misc import one_hot
from sklearn.model_selection import train_test_split
from copy import copy, deepcopy
import tensorflow as tf
import scipy.io
import os

SVHN_PATH = '/data/dataset/SVHN_MINI'

class MyFeederValTest(darkon.InfluenceFeeder):
    def __init__(self, dataset, rand_gen, as_one_hot, val_inds=None, test_val_set=False, mini_train_inds=None):

        self.dataset = dataset
        self.test_val_set = test_val_set
        self.use_mini_train = mini_train_inds is not None

        # load train data
        if dataset == 'cifar10':
            (data, label), (_, _) = tf.keras.datasets.cifar10.load_data()
            data = data.astype(np.float32)
            self.num_classes = 10
            self.num_val_set = 1000
        elif dataset == 'cifar100':
            (data, label), (_, _) = tf.keras.datasets.cifar100.load_data()
            data = data.astype(np.float32)
            self.num_classes = 100
            self.num_val_set = 1000
        elif dataset == 'svhn':
            data  = np.load(os.path.join(SVHN_PATH, 'X_train.npy'))
            label = np.load(os.path.join(SVHN_PATH, 'y_train.npy'))
            data = data.astype(np.float32)
            self.num_classes = 10
            self.num_val_set = 1000
        else:
            raise AssertionError('dataset {} not supported'.format(dataset))
        data /= 255.
        label = np.squeeze(label, axis=1)

        if val_inds is None:
            # here we split the data set to train and validation
            print('Feeder {} did not get val indices, therefore splitting trainset'.format(str(self)))
            indices = np.arange(data.shape[0])
            train_inds, val_inds = \
                train_test_split(indices, test_size=self.num_val_set, random_state=rand_gen, shuffle=True, stratify=label)
        else:
            # val_inds were provided, so we need to infer all other indices
            train_inds = []
            # here we split the data set to train, validation, and test
            for ind in range(data.shape[0]):
                if ind not in val_inds:
                    train_inds.append(ind)
            train_inds = np.asarray(train_inds, dtype=np.int32)

        train_inds.sort()
        val_inds.sort()
        # # save entire train data just for corner usage
        # self.complete_data = data
        # if as_one_hot:
        #     self.complete_label = one_hot(label.astype(np.int32), 10).astype(np.float32)
        # else:
        #     self.complete_label = label

        # train data
        self.train_inds        = train_inds
        self.train_origin_data = data[train_inds]
        self.train_data        = data[train_inds]
        if as_one_hot:
            self.train_label = one_hot(label[train_inds].astype(np.int32), self.num_classes).astype(np.float32)
        else:
            self.train_label = label[train_inds]

        if mini_train_inds is not None:
            self.mini_train_inds        = mini_train_inds
            self.mini_train_origin_data = data[mini_train_inds]
            self.mini_train_data        = data[mini_train_inds]
            if as_one_hot:
                self.mini_train_label = one_hot(label[mini_train_inds].astype(np.int32), self.num_classes).astype(np.float32)
            else:
                self.mini_train_label = label[mini_train_inds]

        # validation data
        self.val_inds          = val_inds
        self.val_origin_data   = data[val_inds]
        self.val_data          = data[val_inds]
        if as_one_hot:
            self.val_label = one_hot(label[val_inds].astype(np.int32), self.num_classes).astype(np.float32)
        else:
            self.val_label = label[val_inds]

        if dataset == 'cifar10':
            (_, _), (data, label) = tf.keras.datasets.cifar10.load_data()
            data = data.astype(np.float32)
        elif dataset == 'cifar100':
            (_, _), (data, label) = tf.keras.datasets.cifar100.load_data()
            data = data.astype(np.float32)
        elif dataset == 'svhn':
            data  = np.load(os.path.join(SVHN_PATH, 'X_test.npy'))
            label = np.load(os.path.join(SVHN_PATH, 'y_test.npy'))
            data = data.astype(np.float32)
        else:
            raise AssertionError('dataset {} not supported'.format(dataset))
        data /= 255.
        label = np.squeeze(label, axis=1)

        self.test_inds        = np.arange(label.shape[0])
        self.test_origin_data = data
        self.test_data        = data
        if as_one_hot:
            self.test_label = one_hot(label.astype(np.int32), self.num_classes).astype(np.float32)
        else:
            self.test_label = label

        self.train_batch_offset = 0

    # def indices(self, indices):
    #     return self.complete_data[indices], self.complete_label[indices]

    def get_global_index(self, set, idx):
        if set == 'train':
            if self.use_mini_train:
                global_index =  self.mini_train_inds[idx]
            else:
                global_index = self.train_inds[idx]
        elif set == 'val':
            global_index = self.val_inds[idx]
        elif set == 'test':
            global_index = self.test_inds[idx]
        else:
            raise AssertionError('set {} is invalid'.format(set))
        return global_index

    def train_indices(self, indices):
        if self.use_mini_train:
            return self.mini_train_data[indices], self.mini_train_label[indices]
        else:
            return self.train_data[indices], self.train_label[indices]

    def val_indices(self, indices):
        return self.val_data[indices], self.val_label[indices]

    def test_indices(self, indices):
        if self.test_val_set:
            return self.val_indices(indices)
        else:
            return self.test_data[indices], self.test_label[indices]

    def train_batch(self, batch_size):
        # calculate offset
        start = self.train_batch_offset
        end = start + batch_size
        self.train_batch_offset += batch_size

        if self.use_mini_train:
            return self.mini_train_data[start:end, ...], self.mini_train_label[start:end, ...]
        else:
            return self.train_data[start:end, ...], self.train_label[start:end, ...]

    def train_one(self, idx):
        if self.use_mini_train:
            return self.mini_train_data[idx, ...], self.mini_train_label[idx, ...]
        else:
            return self.train_data[idx, ...], self.train_label[idx, ...]

    def reset(self):
        self.train_batch_offset = 0

    def get_train_size(self):
        if self.use_mini_train:
            return len(self.mini_train_inds)
        else:
            return len(self.train_inds)

    def get_val_size(self):
        return len(self.val_inds)

    def get_test_size(self):
        if self.test_val_set:
            return self.get_val_size()
        else:
            return len(self.test_inds)

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if k == 'train_batch_offset':
                setattr(result, k, deepcopy(v, memo))
            else:
                setattr(result, k, v)
        return result


############################################## optional for test mini ###############################################
# instead of using the entire training samples, use only 5000 (500 samples from each class).
# if not os.path.isfile(os.path.join(model_dir, 'test_mini_indices.npy')):
#     random_indices = []
#     for cls in range(len(_classes)):
#         cls_train_indices = []
#         got_so_far = 0
#         while got_so_far < 500:
#             cls_train_index = rand_gen.choice(np.where(y_train_sparse == cls)[0])
#             if (cls_train_index not in cls_train_indices) and (cls_train_index in feeder.train_inds):
#                 cls_train_indices.append(cls_train_index)
#                 got_so_far += 1
#         print('len = {}'.format(len(cls_train_indices)))
#         random_indices.extend(cls_train_indices)
#     random_indices = np.asarray(random_indices, dtype=np.int32)
#     random_indices.sort()
#     np.save(os.path.join(model_dir, 'train_mini_indices.npy'), random_indices)
# else:
#     print('re-using test_mini_indices from file {}'.format(os.path.join(model_dir, 'train_mini_indices.npy')))
#     random_indices = np.load(os.path.join(model_dir, 'train_mini_indices.npy'))
#
# # updating feeders
# sub_train_indices = [i for i, ti in enumerate(feeder.train_inds) if ti in random_indices]
# sub_train_indices = np.asarray(sub_train_indices, dtype=np.int32)
# feeder.train_inds        = feeder.train_inds[sub_train_indices]  # same as feeder.train_inds = random_indices
# feeder.train_origin_data = feeder.train_origin_data[sub_train_indices]
# feeder.train_data        = feeder.train_data[sub_train_indices]
# feeder.train_label       = feeder.train_label[sub_train_indices]
############################################## optional for test mini ###############################################
