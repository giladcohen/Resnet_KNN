from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from abc import ABCMeta, abstractmethod

import tensorflow as tf

from lib.trainers.hooks import LearningRateSetterHook
from lib.trainers.train_base import TrainBase


class ClassificationTrainer(TrainBase):
    __metaclass__ = ABCMeta

    def __init__(self, *args, **kwargs):
        super(ClassificationTrainer, self).__init__(*args, **kwargs)
        self.best_precision = 0.0
        self.global_step    = 0
        self._activate_eval = True

    def train(self):
        super(ClassificationTrainer, self).train()
        truth          = self.model.labels
        predictions    = tf.argmax(self.model.predictions, axis=1)
        precision      = tf.reduce_mean(tf.to_float(tf.equal(predictions, truth)))

        images_summary = tf.summary.image('images', self.model.images)
        self.summary_writer_train = tf.summary.FileWriter(self.train_dir)  # for training
        self.summary_writer_eval  = tf.summary.FileWriter(self.eval_dir)   # for evaluation

        summary_hook = tf.train.SummarySaverHook(
            save_steps=self.summary_steps,
            summary_writer=self.summary_writer_train,
            summary_op=tf.summary.merge([self.model.summaries,
                                         images_summary,
                                         tf.summary.scalar('Precision', precision)]))

        logging_hook = tf.train.LoggingTensorHook(
            tensors={'step': self.model.global_step,
                     'loss_xent': self.model.xent_cost,
                     'loss_wd': self.model.wd_cost,
                     'loss': self.model.cost,
                     'precision': precision},
            every_n_iter=self.logger_steps)

        learning_rate_hook = LearningRateSetterHook(self.prm, self.model, self._logger)

        self.sess = tf.train.MonitoredTrainingSession(
            checkpoint_dir=self.checkpoint_dir,
            hooks=[logging_hook, learning_rate_hook],
            chief_only_hooks=[summary_hook],
            save_checkpoint_secs=self.checkpoint_secs,
            config=tf.ConfigProto(allow_soft_placement=True))

        while not self.sess.should_stop():
            if self.global_step % self.eval_steps == 0 and self._activate_eval:
                self.eval_step()
                self._activate_eval = False
            else:
                self.train_step()
                self._activate_eval = True

    @abstractmethod
    def train_step(self):
        '''Implementing one training step. This function must update self.global_step'''
        pass

    @abstractmethod
    def eval_step(self):
        '''Implementing one evaluation step.'''
        pass




