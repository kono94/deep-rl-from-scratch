import numpy as np
from numpy import sin, cos, pi
from numpy import radians as rad
import pandas as pd
import plotly.express as px 
from geopy.distance import geodesic

from gym import core, spaces
from gym.envs.registration import register

# State boundaries
MIN_LON, MAX_LON = 8.4361, 8.5927
MIN_LAT, MAX_LAT = 53.4570, 53.6353
MIN_COG, MAX_COG = 0., 359.9
MIN_SOG, MAX_SOG = 3., 29.9
# Define inverse scales
DLON = MAX_LON - MIN_LON
DLAT = MAX_LAT - MIN_LAT
DCOG = MAX_COG - MIN_COG
DSOG = MAX_SOG - MIN_SOG

def update_lat(cog, sog, dt):
    return (dt / 60) * cos(rad(cog)) * sog

def update_lon(lat, cog, sog, dt):
    return (dt / 60) * sin(rad(cog)) * sog / cos(rad(lat))

def geo_distance(p1, p2):
    """ Distance between points p1 and p2 in Km"""
    lat1, lon1 = p1
    lat2, lon2 = p2
    R = 6378.137 
    hx = sin(0.5*rad(lat2-lat1))**2
    hy = sin(0.5*rad(lon2-lon1))**2
    h = hx + cos(rad(lat1))*cos(rad(lat2))* hy
    return 2*R* np.arcsin(np.sqrt(h))

class AISenv(core.Env):

    def __init__(self, dataset='trajectories_linear_interpolate.csv', time_interval=5):
        # Trajectory ID column 'traj_id'
        self.df = pd.read_csv(dataset)
        self.num_trajectories = self.df.groupby('traj_id').count().shape[0]
        self.time_interval_secs = time_interval
        
        # Observations: lon, lat, cog, sog, dt
        low = np.array([MIN_LON, MIN_LAT, MIN_COG, MIN_SOG], dtype=np.float32)
        high = np.array([MAX_LON, MAX_LAT, MAX_COG, MAX_SOG], dtype=np.float32)
        self.observation_space = spaces.Box(low=low, high=high, dtype=np.float32)
        # Actions: cog, sog
        low = np.array([MIN_COG, MIN_SOG], dtype=np.float32)
        high = np.array([MAX_COG, MAX_SOG], dtype=np.float32)
        self.action_space = spaces.Box(low=low, high=high)
        # Custom variables
        self.step_counter = 0
        self.scale = np.array([1/DLON, 1/DLAT, 1/DCOG, 1/DSOG])
        self.shift = np.array([MIN_LON, MIN_LAT, MIN_COG, MIN_SOG])
        self.training = True
        self.trajectory_index = 0
        
    def __getitem__(self, i):
        return self.episode_df.iloc[i,:].values

    def reset(self):
        self.episode_df = list(self.df.groupby('traj_id'))[self.trajectory_index][1]
        self.episode_df = self.episode_df[['lon', 'lat', 'cog', 'sog']]
        self.length_episode = self.episode_df.shape[0]
        self.state = self[0]
        self.pos_pred = np.expand_dims(self.state[:2],0)
        self.pos_true = np.expand_dims(self.state[:2],0)
        return self.scale * (self.state - self.shift)
    
    def step(self, action):
        if not self.the_end:
            # Read current environment state and agent's action
            lon = self.episode_df['lon']
            lat = self.episode_df['lat']
            cog_a, sog_a = map(lambda x: np.clip(x, 0, 1), action)
            # The agent's outputs need to be tranformed back to original scale
            sog_a = MIN_SOG + DSOG * sog_a
            cog_a = MIN_COG + DCOG * cog_a 
        
            # Agent's suggestion of state update according to last observation
            lat_pred = lat + update_lat(cog_a, sog_a, self.time_interval_secs / 3600)
            lon_pred = lon + update_lon(lat, cog_a, sog_a, self.time_interval_secs / 3600)
            print(lat_pred)
            # Ensure that predictions are within bounds
            lat_pred = np.clip(lat_pred, MIN_LAT, MAX_LAT)
            lon_pred = np.clip(lon_pred, MIN_LON, MAX_LON)
            cog_pred = np.clip(cog_a, MIN_COG, MAX_COG)
            # Compare with observation at next step
            self.step_counter += 1
            self.state = self[self.step_counter]
            lon_true, lat_true = self.state[:2]
            
            # If the agent is self-looping, modify the next state accordingly
            self.state = self.state if self.training else np.array([lon_pred, lat_pred, cog_pred])
            # Compute the error committed by the agent's state suggestion
            geo_dist = geo_distance((lat_pred, lon_pred), (lat_true, lon_true))
            reward = 0
            
            # curve the agent has to follow
            self.true_traj = None
            # curve that the agent
            self.agent_traj = None
            
            # Record predictions and observations of vessel location
            print(self.pos_pred)
            self.pos_pred = np.concatenate((self.pos_pred, [lon_pred, lat_pred]), axis=0)
            self.pos_true = np.concatenate((self.pos_true, [lon_true, lat_true]), axis=0)
        else: 
            reward = self.finish()
        # The agent's networks need normalized observations 
        observation = self.scale * (self.state - self.shift)
        return observation, reward, self.the_end, {}
    
    def render(self):
        pos_history = np.concatenate((self.pos_pred, self.pos_true), axis=0)
        hist_len = pos_history.shape[0] // 2
        df_pos = pd.DataFrame(pos_history, columns=['lon', 'lat'])
        df_pos['entity'] = ['prediction'] * hist_len + ['observation'] * hist_len
        fig = px.scatter_mapbox(df_pos, lon="lon", lat="lat", color="entity",
                            zoom=11, height=800, 
                            center={'lat': 53.53, 'lon':8.56})
        fig.update_layout(mapbox_style="open-street-map")
        fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
        fig.show()
    
    @property
    def the_end(self):
        return bool(self.step_counter == self.length_episode-1)
    
    def finish(self, reset_trajectory_index=False):
        self.step_counter = 0
        self.episode = 0 if reset_trajectory_index else self.trajectory_index + 1
        self.episode = self.trajectory_index % self.num_trajectories 
        self.state = self.shift + self.reset() / self.scale
        return 0

def run_agent_env_loop(env, agent, random_process, 
                       num_episodes=None, render=True, self_loop=False, in_sample=False):

    num_episodes = num_episodes if num_episodes else env.num_episodes
    # Since agent.fit trains on nb_steps, the last training episode may not be finished yet
    try:
        if not env.the_end: _ = env.finish(reset_episodes=in_sample) # reset_episodes -> test in-sample
    except: # when running before calling agent.fit
        pass
    # Tag env as non-trainable: states not read from dataset now but from agent predictions
    env.training = False if self_loop else True
    # Reset random_process
    random_process.reset_states()
    for episode in range(num_episodes):
        print(f"Episode {episode}/{num_episodes}")
        observation = env.reset()
        for t, _ in enumerate(env):
            action = agent.forward(observation) + random_process.sample()
            observation, _, done, _ = env.step(action)
            if done:
                print(f"Episode finished after {t+1} steps")
                break
        if render: env.render()
        
ais = AISenv()
ais.reset()
ais.step([0.3, 0.45])
ais.render()
    
register(
    id="ais-v0",
    entry_point="deeprl.envs.ais_env:AISenv",
)           
