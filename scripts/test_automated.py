import argparse
import os
import sys
import warnings

cwd = os.getcwd() # tensorflow-TB
sys.path.insert(0, cwd)

from lib.logger.logging_config import logging_config
from utils.parameters import Parameters
from utils.factories import Factories
import tensorflow as tf
from utils.misc import query_yes_no

def get_params(test_config, parser=None):
    """get params and save them to root dir"""
    prm = Parameters()

    # get giles paths
    prm.override(test_config)
    if parser is not None:
        # overriding some parameters manually from parser:
        prm.train.train_control.ROOT_DIR           = parser.ROOT_DIR
        prm.test.test_control.KNN_WEIGHTS          = parser.KNN_WEIGHTS
        prm.test.test_control.KNN_NORM             = parser.KNN_NORM
        prm.train.train_control.PCA_REDUCTION      = (parser.PCA_REDUCTION == 'True')
        prm.train.train_control.PCA_EMBEDDING_DIMS = int(parser.PCA_EMBEDDING_DIMS)
        prm.test.test_control.KNN_NEIGHBORS        = int(parser.KNN_NEIGHBORS)
        prm.test.test_control.DUMP_NET             = (parser.DUMP_NET == 'True')
        prm.test.test_control.LOAD_FROM_DISK       = (parser.LOAD_FROM_DISK == 'True')

    parameter_file      = os.path.join(prm.train.train_control.ROOT_DIR, 'parameters.ini')
    test_parameter_file = os.path.join(prm.train.train_control.ROOT_DIR, 'test_parameters.ini')
    all_parameter_file  = os.path.join(prm.train.train_control.ROOT_DIR, 'all_parameters.ini')
    log_file            = os.path.join(prm.train.train_control.ROOT_DIR, 'test.log')
    logging = logging_config(log_file)
    logging.disable(logging.DEBUG)

    if not os.path.isfile(parameter_file):
        raise AssertionError('Can not find file: {}'.format(parameter_file))

    ret = True
    if os.path.isfile(test_parameter_file):
        warnings.warn('Test parameter file {} already exists'.format(test_parameter_file))
        ret = query_yes_no('Overwrite parameter file?')

    if ret:
        dir = os.path.dirname(test_parameter_file)
        if not os.path.exists(dir):
            os.makedirs(dir)
        prm.save(test_parameter_file)

    # Done saving test parameters. Now doing the integration:
    prm = Parameters()
    prm.override(parameter_file)
    prm.override(test_parameter_file)

    ret = True
    if os.path.isfile(all_parameter_file):
        warnings.warn('All parameter file {} already exists'.format(all_parameter_file))
        ret = query_yes_no('Overwrite parameter file?')

    if ret:
        dir = os.path.dirname(all_parameter_file)
        if not os.path.exists(dir):
            os.makedirs(dir)
        prm.save(all_parameter_file)

    return prm

def test(prm):
    tf.set_random_seed(prm.SUPERSEED)
    factories = Factories(prm)

    model        = factories.get_model()
    model.print_stats() #debug

    dataset = factories.get_dataset()
    dataset.print_stats() #debug

    tester      = factories.get_tester(model, dataset)
    tester.print_stats() #debug

    tester.test()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    # for automating KNN testing
    parser.add_argument('--ROOT_DIR'          , action='store')
    parser.add_argument('--KNN_WEIGHTS'       , action='store')
    parser.add_argument('--KNN_NORM'          , action='store')
    parser.add_argument('--PCA_REDUCTION'     , action='store')
    parser.add_argument('--PCA_EMBEDDING_DIMS', action='store')
    parser.add_argument('--KNN_NEIGHBORS'     , action='store')
    parser.add_argument('--DUMP_NET'          , action='store')
    parser.add_argument('--LOAD_FROM_DISK'    , action='store')

    parser.add_argument('-c', help='Test configuration file', action='store')
    args = parser.parse_args()

    test_config = args.c
    if not os.path.isfile(test_config):
        raise AssertionError('Can not find file: {}'.format(test_config))

    prm = get_params(test_config, parser=parser)

    dev = prm.network.DEVICE
    with tf.device(dev):
        test(prm)
