# Copyright 2018 DeepMind Technologies Limited. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Wraps an OpenAI Gym environment to be used as a dm_env environment."""

from typing import Any, Dict, List, Optional

import os
import tree
import dm_env
import numpy as np
os.sys.path.insert(0, os.path.abspath('../../'))
import gym
from   gym                    import spaces
from   configs.algos          import rl_config
from   arch_gym.envs.FARSIEnv import FARSISimEnv
from   envHelpers             import helpers
from   acme                   import specs
from   acme                   import types
from   acme                   import wrappers

class FARSISimEnvWrapper(dm_env.Environment):
  """Environment wrapper for OpenAI Gym environments."""

  # Note: we don't inherit from base.EnvironmentWrapper because that class
  # assumes that the wrapped environment is a dm_env.Environment.

  def __init__(self, environment: gym.Env):

    self._environment = environment
    self._reset_next_step = True
    self._last_info = None
    self.helper = helpers()

    # Convert action and observation specs.
    obs_space = self._environment.observation_space
    act_space = self._environment.action_space
    self._observation_spec = _convert_to_spec(obs_space, name='observation')
    self._action_spec = _convert_to_spec(act_space, name='action')

  def reset(self) -> dm_env.TimeStep:
    """Resets the episode."""
    self._reset_next_step = False
    observation = self._environment.reset()
    # Reset the diagnostic information.
    self._last_info = None
    return dm_env.restart(observation)

  def check_action_ranges(self, action: types.NestedArray):
    """Checks that the action is within the action space."""
    dummy_reward = 0
    if(action[0]<0 or action[0]>3):
      dummy_reward += -100
    elif(action[1]<0 or action[1]>2):
      dummy_reward += -100
    elif(action[2]<0 or action[2]>2):
      dummy_reward += -100
    elif(action[3]<2 or action[3]>128):
      dummy_reward += -100
    elif(action[4]<0 or action[4]>1):
      dummy_reward += -100
    elif(action[5]<0 or action[5]>1):
      dummy_reward += -100
    elif(action[6]<2 or action[6]>128):
      dummy_reward += -100
    elif(action[7]<2 or action[7]>128):
      dummy_reward += -100
    elif(action[8]<0 or action[8]>2):
      dummy_reward += -100
    elif(action[9]<2 or action[9]>128):
      dummy_reward += -100
    return dummy_reward

  def step(self, action): # types.NestedArray) -> dm_env.TimeStep:
    """Steps the environment."""
    if self._reset_next_step:
      return self.reset()
    
    observation, reward, done, info = self._environment.step(action)
    self._reset_next_step = done
    self._last_info = info

    # Convert the type of the reward based on the spec, respecting the scalar or
    # array property.
    reward = tree.map_structure(
        lambda x, t: (  # pylint: disable=g-long-lambda
            t.dtype.type(x)
            if np.isscalar(x) else np.asarray(x, dtype=t.dtype)),
        reward,
        self.reward_spec())

    if done:
      truncated = info.get('TimeLimit.truncated', False)
      if truncated:
        return dm_env.truncation(reward, observation)
      return dm_env.termination(reward, observation)
    return dm_env.transition(reward, observation)

  def observation_spec(self) -> types.NestedSpec:
    return self._observation_spec

  def action_spec(self) -> types.NestedSpec:
    return self._action_spec

  def reward_spec(self):
    return specs.Array(shape=(), dtype=float, name='reward')

  def get_info(self) -> Optional[Dict[str, Any]]:
    """Returns the last info returned from env.step(action).
    Returns:
      info: dictionary of diagnostic information from the last environment step
    """
    return self._last_info

  @property
  def environment(self) -> gym.Env:
    """Returns the wrapped environment."""
    return self._environment

  def __getattr__(self, name: str):
    if name.startswith('__'):
      raise AttributeError(
          "attempted to get missing private attribute '{}'".format(name))
    return getattr(self._environment, name)

  def close(self):
    self._environment.close()


def _convert_to_spec(space: gym.Space,
                     name: Optional[str] = None) -> types.NestedSpec:
  """Converts an OpenAI Gym space to a dm_env spec or nested structure of specs.
  Box, MultiBinary and MultiDiscrete Gym spaces are converted to BoundedArray
  specs. Discrete OpenAI spaces are converted to DiscreteArray specs. Tuple and
  Dict spaces are recursively converted to tuples and dictionaries of specs.
  Args:
    space: The Gym space to convert.
    name: Optional name to apply to all return spec(s).
  Returns:
    A dm_env spec or nested structure of specs, corresponding to the input
    space.
  """
  if isinstance(space, spaces.Discrete):
    return specs.DiscreteArray(num_values=space.n, dtype=space.dtype, name=name)

  elif isinstance(space, spaces.Box):
    return specs.BoundedArray(
        shape=space.shape,
        dtype=space.dtype,
        minimum=space.low,
        maximum=space.high,
        name=name)

  elif isinstance(space, spaces.MultiBinary):
    return specs.BoundedArray(
        shape=space.shape,
        dtype=space.dtype,
        minimum=0.0,
        maximum=1.0,
        name=name)

  elif isinstance(space, spaces.MultiDiscrete):
    return specs.BoundedArray(
        shape=space.shape,
        dtype=space.dtype,
        minimum=np.zeros(space.shape),
        maximum=space.nvec - 1,
        name=name)

  elif isinstance(space, spaces.Tuple):
    return tuple(_convert_to_spec(s, name) for s in space.spaces)

  elif isinstance(space, spaces.Dict):
    return {
        key: _convert_to_spec(value, key)
        for key, value in space.spaces.items()
    }

  else:
    raise ValueError('Unexpected gym space: {}'.format(space))

def make_FARSI_sim_env(seed: int = 12234,
                     reward_formulation: str = 'power',
                     workload: str = 'audio_decoder',
                     rl_form = None,
                     rl_algo = None,
                     max_steps = 2,
                     num_agents = 1,
                     reward_scaling = 'false'
                     ) -> dm_env.Environment:

  """Returns FARSI environment."""
  environment = FARSISimEnvWrapper(FARSISimEnv(
    reward_formulation = reward_formulation, workload = workload, rl_form=rl_form, rl_algo=rl_algo, max_steps=max_steps, num_agents=num_agents, reward_scaling=reward_scaling))
  environment = wrappers.SinglePrecisionWrapper(environment)
  if(rl_config.rl_agent):
    environment = wrappers.CanonicalSpecWrapper(environment, clip=True)
  return environment
