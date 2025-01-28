# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# developer: Eric (Ørpheus A.I.)
# Copyright © 2025 Ørpheus A.I.

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

from typing import List
from functools import partial
import time
import bittensor as bt
import wandb
import numpy as np
import torch

from zeus.data.sample import Era5Sample
from zeus.data.era5.era5_cds import Era5CDSLoader
from zeus.utils.coordinates import get_bbox
from zeus.validator.reward import get_rewards
from zeus.utils.uids import get_random_uids
from zeus.validator.constants import LIVE_DATA_PROB


async def forward(self):
    """
    The forward function is called by the validator every time step.

    It is responsible for querying the network and scoring the responses.

    Args:
        self (:obj:`bittensor.neuron.Neuron`): The neuron object which contains all the necessary state for the validator.

    """
    # based on the block, we decide if we should score old stored predictions. 
    if self.database.should_score(self.block):
        bt.logging.info(f"Scoring all stored predictions for live ERA5 data.")
        self.database.score_and_prune(score_func=partial(complete_challenge, self))
        return

    # Let's sample some data
    data_loader: Era5CDSLoader = self.cds_loader
    bt.logging.info(f"Sampling data...")
    sample = data_loader.get_sample() # does not need data loader to be ready yet - we only select a box and time area.
    bt.logging.success(f"Data sampled. Input shape: {sample.input_data.shape} | Asked to predict {sample.predict_hours} hours ahead.")	

    # get some miners
    miner_uids = get_random_uids(self, k=self.config.neuron.sample_size)
    axons = [self.metagraph.axons[uid] for uid in miner_uids]
    miner_hotkeys: List[str] =list([axon.hotkey for axon in axons])

    # The dendrite client queries the network.
    bt.logging.info(f"Querying {len(miner_uids)} miners..")
    start = time.time()
    responses = await self.dendrite(
        axons=axons,
        synapse=sample.get_synapse(),
        deserialize=True,
        timeout=self.config.neuron.timeout,
    )

    bt.logging.success(f"Responses received in {time.time() - start}s")

    good_hotkeys, good_responses = zip(*[(hk, res) for hk, res in zip(miner_hotkeys, responses) if len(res) > 0])
    # filter out miners that did not respond so we can 'score' those right away.
    bad_uids = [uid for uid, response in zip(miner_uids, responses) if len(response) == 0]

    if len(bad_uids) > 0:
        bt.logging.success(f"Punishing miners that did not respond immediately.")
        self.update_scores(np.zeros(len(bad_uids)), bad_uids)
    
    if len(good_hotkeys) > 0:
        bt.logging.success("Storing challenge and miner responses in SQLite database")
        self.database.insert(sample, good_hotkeys, good_responses)
    # Introduce a delay to prevent spamming requests
    time.sleep(60)


def complete_challenge(self, sample: Era5Sample, hotkeys: List[str], predictions: List[torch.Tensor]):
    lookup = {axon.hotkey: uid for uid, axon in enumerate(self.metagraph.axons)}
    # Get the uids of the miners that responded and are still alive
    miner_uids = []
    responses = []
    for hotkey, prediction in zip(hotkeys, predictions):
        uid = lookup.get(hotkey, None)
        if uid is not None:
            miner_uids.append(uid)
            responses.append(prediction)

    # score and reward just those miners
    rewards, metrics = get_rewards(
        output_data=sample.output_data,
        responses=responses, # miner responses
        difficulty_grid=self.difficulty_loader.get_difficulty_grid(sample),
        )
    self.update_scores(rewards, miner_uids)

    miners_scores = {}
    for uid, response, reward in zip(miner_uids, responses, rewards):
        if len(response) != 0:
            miners_scores[uid] = reward
            bt.logging.success(f"UID: {uid} | Predicted shape: {response.shape} | Reward: {reward}")
    # store best miners for the Proxy
    self.last_responding_miner_uids = sorted(miners_scores, key=miners_scores.get, reverse=True)

    if not self.config.wandb.off:
        for miner_uid, metric_dict in zip(miner_uids, metrics):
            wandb.log(
                {
                    f"miner_{miner_uid}_{key}": val 
                    for key, val in metric_dict.items()
                },
                commit=False # All logging should be the same commit
            )

        wandb.log(
            {
                "start_timestamp": sample.start_timestamp,
                "end_timestamp": sample.end_timestamp,
                "predict_hours": sample.predict_hours,
                "lat_lon_bbox": sample.get_bbox(),
            },
        )