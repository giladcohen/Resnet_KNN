from abc import ABCMeta
from lib.models.model_base import ModelBase
import tensorflow as tf

class ClassifierModel(ModelBase):
    __metaclass__ = ABCMeta
    '''Implementing an image classifier'''

    def __init__(self, *args, **kwargs):
        super(ClassifierModel, self).__init__(*args, **kwargs)
        self.predictions  = None    # predictions of the classifier
        self.xent_cost    = None    # contribution of cross entropy to loss
        self.num_classes  = self.prm.network.NUM_CLASSES
        self.image_height = self.prm.network.IMAGE_HEIGHT
        self.image_width  = self.prm.network.IMAGE_WIDTH

    def _set_placeholders(self):
        self.images = tf.placeholder(tf.float32, [None, self.image_height, self.image_width, 3])
        self.labels = tf.placeholder(tf.int32, [None])
        self.is_training = tf.placeholder(tf.bool)

    def _build_interpretation(self):
        '''Interprets the logits'''
        self.predictions = tf.nn.softmax(self.logits)

    def add_fidelity_loss(self):
        with tf.variable_scope('xent_cost'):
            xent_cost = tf.nn.sparse_softmax_cross_entropy_with_logits(logits=self.logits, labels=self.labels)
            xent_cost = tf.reduce_mean(xent_cost, name='cross_entropy_mean')
            self.xent_cost = tf.multiply(self.xent_rate, xent_cost)
            xent_assert_op = tf.verify_tensor_all_finite(self.xent_cost, 'xent_cost contains NaN or Inf')
            tf.add_to_collection('losses', self.xent_cost)
            tf.add_to_collection('assertions', xent_assert_op)












