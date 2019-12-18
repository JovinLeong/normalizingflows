import autograd
import autograd.numpy as np
import autograd.scipy as sp
import autograd.misc.optimizers
from autograd import grad
import numpy
import time
import os
import sys
from tqdm import tqdm
from matplotlib import pyplot as plt
from autograd.misc.optimizers import adam
from flows import adam_solve, energy_bound

class Feedforward:
    def __init__(self, architecture, random=None, weights=None):
        self.params = {'H': architecture['width'],
                       'L': architecture['hidden_layers'],
                       'D_in': architecture['input_dim'],
                       'D_out': architecture['output_dim'],
                       'activation_type': architecture['activation_fn_type'],
                       'activation_params': architecture['activation_fn_params']}

        self.D = (  (architecture['input_dim'] * architecture['width'] + architecture['width'])
                  + (architecture['output_dim'] * architecture['width'] + architecture['output_dim'])
                  + (architecture['hidden_layers'] - 1) * (architecture['width']**2 + architecture['width'])
                 )

        if random is not None:
            self.random = random
        else:
            self.random = np.random.RandomState(0)

        self.h = architecture['activation_fn']

        if weights is None:
            self.weights = self.random.normal(0, 1, size=(1, self.D))
        else:
            self.weights = weights

        self.objective_trace = np.empty((1, 1))
        self.weight_trace = np.empty((1, self.D))


    def forward(self, weights, x):
        ''' Forward pass given weights and input '''
        H = self.params['H']
        D_in = self.params['D_in']
        D_out = self.params['D_out']

        assert weights.shape[1] == self.D

        if len(x.shape) == 2:
            assert x.shape[0] == D_in
            x = x.reshape((1, D_in, -1))
        else:
            assert x.shape[1] == D_in

        weights = weights.T


        #input to first hidden layer
        W = weights[:H * D_in].T.reshape((-1, H, D_in))
        b = weights[H * D_in:H * D_in + H].T.reshape((-1, H, 1))
        input = self.h(np.matmul(W, x) + b)
        index = H * D_in + H

        assert input.shape[1] == H

        #additional hidden layers
        for _ in range(self.params['L'] - 1):
            before = index
            W = weights[index:index + H * H].T.reshape((-1, H, H))
            index += H * H
            b = weights[index:index + H].T.reshape((-1, H, 1))
            index += H
            output = np.matmul(W, input) + b
            input = self.h(output)

            assert input.shape[1] == H

        #output layer
        W = weights[index:index + H * D_out].T.reshape((-1, D_out, H))
        b = weights[index + H * D_out:].T.reshape((-1, D_out, 1))
        output = np.matmul(W, input) + b
        assert output.shape[1] == self.params['D_out']

        return output

    def make_objective(self, x_train, y_train, reg_param=None):
        ''' Make objective functions: depending on whether or not you want to apply l2 regularization '''

        if reg_param is None:

            def objective(W, t):
                squared_error = np.linalg.norm(y_train - self.forward(W, x_train), axis=1)**2
                sum_error = np.sum(squared_error)
                return sum_error

            return objective, grad(objective)

        else:

            def objective(W, t):
                squared_error = np.linalg.norm(y_train - self.forward(W, x_train), axis=1)**2
                mean_error = np.mean(squared_error) + reg_param * np.linalg.norm(W)
                return mean_error

            return objective, grad(objective)

    def fit(self, x_train, y_train, params, reg_param=None):
        ''' Wrapper for MLE through gradient descent '''
        assert x_train.shape[0] == self.params['D_in']
        assert y_train.shape[0] == self.params['D_out']

        ### make objective function for training
        self.objective, self.gradient = self.make_objective(x_train, y_train, reg_param)

        ### set up optimization
        step_size = 0.01
        max_iteration = 5000
        check_point = 100
        weights_init = self.weights.reshape((1, -1))
        mass = None
        optimizer = 'adam'
        random_restarts = 5

        if 'step_size' in params.keys():
            step_size = params['step_size']
        if 'max_iteration' in params.keys():
            max_iteration = params['max_iteration']
        if 'check_point' in params.keys():
            self.check_point = params['check_point']
        if 'init' in params.keys():
            weights_init = params['init']
        if 'call_back' in params.keys():
            call_back = params['call_back']
        if 'mass' in params.keys():
            mass = params['mass']
        if 'optimizer' in params.keys():
            optimizer = params['optimizer']
        if 'random_restarts' in params.keys():
            random_restarts = params['random_restarts']

        def call_back(weights, iteration, g):
            ''' Actions per optimization step '''
            objective = self.objective(weights, iteration)
            self.objective_trace = np.vstack((self.objective_trace, objective))
            self.weight_trace = np.vstack((self.weight_trace, weights))
            if iteration % check_point == 0:
                print("Iteration {} lower bound {}; gradient mag: {}".format(iteration, objective, np.linalg.norm(self.gradient(weights, iteration))))

        ### train with random restarts
        optimal_obj = 1e16
        optimal_weights = self.weights

        for i in range(random_restarts):
            if optimizer == 'adam':
                adam(self.gradient, weights_init, step_size=step_size, num_iters=max_iteration, callback=call_back)
            local_opt = np.min(self.objective_trace[-100:])

            if local_opt < optimal_obj:
                opt_index = np.argmin(self.objective_trace[-100:])
                self.weights = self.weight_trace[-100:][opt_index].reshape((1, -1))
            weights_init = self.random.normal(0, 1, size=(1, self.D))

        self.objective_trace = self.objective_trace[1:]
        self.weight_trace = self.weight_trace[1:]


def log_joint(w, x, y, nn, mu=0, sig1=5., sig2=0.5, N=16):
    print(w[0].shape)
    print(x.shape)
    sig1_mat = sig1**2 * np.eye(N)
    mu = nn.forward(w[0], x[np.newaxis,])[0][0]
    prior = np.log(sp.stats.multivariate_normal.pdf(w, np.zeros(N), sig1_mat))
    likelihood = 0
    for i in range(len(y_train)):
        likelihood += np.log(sp.stats.norm.pdf(y_train[i], mu[i], sig2**2))

    return np.exp(-prior - likelihood)


if __name__ == '__main__':
    # Read in data
    data = np.loadtxt("./HW7_data.csv", delimiter=',')
    x = data[:,0]
    y = data[:,1]

    ###define rbf activation function
    alpha = 1
    c = 0
    h = lambda x: np.exp(-alpha * (x - c)**2)
    
    ###neural network model design choices
    width = 5
    hidden_layers = 1
    input_dim = 1
    output_dim = 1
    
    architecture = {'width': width,
                   'hidden_layers': hidden_layers,
                   'input_dim': input_dim,
                   'output_dim': output_dim,
                   'activation_fn_type': 'rbf',
                   'activation_fn_params': 'c=0, alpha=1',
                   'activation_fn': h}
    
    #set random state to make the experiments replicable
    rand_state = 0
    random = np.random.RandomState(rand_state)
    
    #instantiate a Feedforward neural network object
    bnn = Feedforward(architecture, random=random)

    num_flows = 10
    num_samples = 100
    h = np.tanh
    lambda_flows = np.array([np.array([0., 0., 0., 0., 0., 0., 0., 0., 
                                       0., 0., 0., 0., 0., 0., 0., 0.])]*num_flows)
    #samples = np.random.randn(num_samples)[:,np.newaxis]
    samples = np.random.multivariate_normal([0]*5, np.eye(5), num_samples)
    print(samples.shape)
    grad_energy_bound = autograd.grad(energy_bound)

    print("HERE: {}\n\n\n".format(y))
    joint_prob = lambda w: log_joint(w, x, y, bnn)
    output = adam_solve(lambda_flows, grad_energy_bound, samples, joint_prob, h)
    
# Joint = Likelihood of NN * normal prior
