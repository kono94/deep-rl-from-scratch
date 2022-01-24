import numpy as np
from scipy.io import savemat
import deeprl.common.util as util
import matplotlib.pyplot as plt
from tkinter import *
import threading
from copy import deepcopy

class Evaluator(object):

    def __init__(self, num_episodes, save_path='', max_episode_length=None):
        self.num_episodes = num_episodes
        self.max_episode_length = max_episode_length
        self.save_path = save_path
        self.results = np.array([]).reshape(num_episodes,0)

    def __call__(self, env, agent, visualize=False, save=True):
        observation = None
        result = []

        for episode in range(self.num_episodes):
            # reset at the start of episode
            observation = env.reset()
            episode_steps = 0
            episode_reward = 0.
            
            assert observation is not None

            # start episode
            done = False
            while not done:
                # basic operation, action ,reward, blablabla ...
                action = agent.select_action(util.preprocess_state(observation, env), pure=True)
                #print(f'before: {observation} and after: {util.preprocess_state(observation)} action: {action}')
                next_state, reward, done, info = env.step(action)
                #if self.max_episode_length and episode_steps >= self.max_episode_length -1:
                 #   done = True
                
                if visualize:
                    env.render()

                # update
                episode_reward += reward
                episode_steps += 1
                observation = deepcopy(next_state)

            util.prYellow('[Evaluate] #Episode{}: episode_reward:{}'.format(episode,episode_reward))
            result.append(episode_reward)

        result = np.array(result).reshape(-1,1)
        self.results = np.hstack([self.results, result])

        return np.mean(result)

