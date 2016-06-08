'''The Lasagne NN module for Daya Bay data'''

import numpy as np
import theano
import theano.tensor as T
import lasagne as l
import logging
logging.getLogger().setLevel(logging.DEBUG)

from Network import AbstractNetwork

class IBDPairConvAe(AbstractNetwork):
    '''A convolutional autoencoder for interpreting candidate IBD pairs.'''

    def __init__(self):
        '''Initialize a ready-to-train convolutional autoencoder.'''
        super(IBDPairConvAe, self).__init__(self)
        # Shapes are given as (batch, depth, height, width)
        self.minibatch_shape = (128, 4, 8, 24)
        self.minibatch_size = self.minibatch_shape[0]
        self.image_shape = self.minibatch_shape[1:-1]
        self.epochs = 1
        self.learn_rate = 0.0001
        self.bottleneck_width = 10
        self.input_var = T.dtensor4('input')
        self.network = self._setup_network()
        self.train_prediction = self._setup_prediction(deterministic=False)
        self.test_prediction = self._setup_prediction(deterministic=True)
        self.train_cost = self._setup_cost(deterministic=False)
        self.test_cost = self._setup_cost(deterministic=True)
        self.optimizer = self._setup_optimizer()
        self.train_once = theano.function([self.input_var],
            self.train_cost, updates=self.optimizer)
        self.predict_fn = theano.function([self.input_var],
            [self.test_cost, self.test_prediction])

    def _setup_network(self):
        '''Construct the ConvAe architecture for Daya Bay IBDs.'''
        initial_weights = l.init.Normal(1, 0)
        # Input layer shape = (minibatch_size, 4, 8, 24)
        network = l.layers.InputLayer(
            input_var=self.input_var,
            shape=self.minibatch_shape)
        # post-conv shape = (minibatch_size, 16, 8, 24)
        network = l.layers.Conv2DLayer(
            network,
            num_filters=16,
            filter_size=(5, 5),
            pad=(2, 2),
            W=initial_weights,
            nonlinearity=l.nonlinearities.rectify)
        # post-pool shape = (minibatch_size, 16, 4, 12)
        network = l.layers.MaxPool2DLayer(
            network,
            pool_size=(2, 2))
        # post-conv shape = (minibatch_size, 16, 4, 10)
        network = l.layers.Conv2DLayer(
            network,
            num_filters=16,
            filter_size=(3, 3),
            pad=(1, 0),
            W=initial_weights,
            nonlinearity=l.nonlinearities.rectify)
        # post-pool shape = (minibatch_size, 16, 2, 5)
        network = l.layers.MaxPool2DLayer(
            network,
            pool_size=(2, 2))
        # post-conv shape = (minibatch_size, 10, 1, 1)
        network = l.layers.Conv2DLayer(
            network,
            name='bottleneck',
            num_filters=self.bottleneck_width,
            filter_size=(2, 5),
            pad=0,
            W=initial_weights,
            nonlinearity=l.nonlinearities.rectify)
        # post-deconv shape = (minibatch_size, 16, 2, 4)
        network = l.layers.Deconv2DLayer(
            network,
            num_filters=16,
            filter_size=(2, 4),
            stride=(2, 2),
            W=initial_weights)
        # post-deconv shape = (minibatch_size, 16, 4, 11)
        network = l.layers.TransposedConv2DLayer(
            network,
            num_filters=16,
            filter_size=(2, 5),
            stride=(2, 2),
            W=initial_weights)
        # post-deconv shape = (minibatch_size, input_depth, 8, 24)
        network = l.layers.TransposedConv2DLayer(
            network,
            num_filters=self.image_shape[0],
            filter_size=(2, 4),
            stride=(2, 2),
            W=initial_weights)
        return network

    def _setup_prediction(self, deterministic):
        '''Construct the Theano identifier that refers to the output of the
        autoencoder.'''
        return l.layers.get_output(self.network, deterministic=deterministic)

    def _setup_cost(self, deterministic):
        '''Construct the sum-squared loss between the input and the output.
        
        Must be called after self.network is defined.'''
        if deterministic:
            prediction = self.test_prediction
        else:
            prediction = self.train_prediction
        cost = l.objectives.squared_error(prediction, self.input_var)
        cost = l.objectives.aggregate(cost, mode='mean')
        return cost

    def _setup_optimizer(self):
        '''Construct the gradient descent optimizer.

        Must be called after self.train_cost is defined.'''
        weights = l.layers.get_all_params(self.network, trainable=True)
        updates = l.updates.momentum(
            self.train_cost,
            weights,
            learning_rate=self.learn_rate,
            momentum=0.9)
        return updates

    def minibatch_iterator(self, x, y=None):
        '''Return a generator that goes through the set in mini-batches.
        '''
        if y is not None:
            raise ValueError("We don't need labels here")
        # Enforce that the data set is an integer multiple of the mini-batch
        # size
        if x.shape[0] % self.minibatch_size != 0:
            raise ValueError('Not a multiple of minibatch size: %d' %
                self.minibatch_size)
        def minibatches():
            indices = np.arange(x.shape[0])
            np.random.shuffle(indices)
            for i in xrange(x.shape[0]/self.minibatch_size):
                low = i * self.minibatch_size
                up = low + self.minibatch_size
                yield x[indices[low:up]]
        return minibatches

    def fit(self, x_train, y_train=None):
        '''Fit and train the autoencoder to the x_train data.'''
        if y_train is not None:
            raise ValueError("We don't need labels here")
        minibatches = self.minibatch_iterator(x_train)
        logging.info("Training with %d training samples" % x_train.shape[0])
        for epoch in xrange(self.epochs):
            for inputs in minibatches():
                cost = self.train_once(inputs)
            logging.info("loss after epoch %d is %f", epoch, cost)

    def predict(self, x, y=None):
        '''Predict the autoencoded image without training.'''
        if y is not None:
            raise ValueError("We don't need labels here")
        return self.predict_fn(x)