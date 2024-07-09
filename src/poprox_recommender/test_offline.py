import csv
import json
import logging
import sys
from itertools import islice

from lenskit.metrics import topn
from tqdm import tqdm

from poprox_recommender.data.mind import TEST_REC_COUNT, MindData

sys.path.append("src")
from uuid import UUID

import numpy as np
import pandas as pd
import torch as th
from safetensors.torch import load_file

from poprox_concepts import ArticleSet
from poprox_concepts.api.recommendations import RecommendationRequest
from poprox_recommender.default import personalized_pipeline
from poprox_recommender.paths import model_file_path, project_root

logger = logging.getLogger("poprox_recommender.test_offline")


def load_model(device_name=None):
    if device_name is None:
        device_name = "cuda" if th.cuda.is_available() else "cpu"

    load_path = model_file_path("model.safetensors")
    checkpoint = load_file(load_path)

    return checkpoint, device_name


def custom_encoder(obj):
    if isinstance(obj, UUID):
        return str(obj)


def recsys_metric(mind_data: MindData, request: RecommendationRequest, recommendations: ArticleSet):
    # recommendations {account id (uuid): LIST[Article]}
    # use the url of Article

    recs = pd.DataFrame({"item": [a.article_id for a in recommendations.articles]})
    truth = mind_data.user_truth(request.interest_profile.profile_id)

    # RR should look for *clicked* articles, not just all impression articles
    single_rr = topn.recip_rank(recs, truth[truth["rating"] > 0])
    single_ndcg5 = topn.ndcg(recs, truth, k=5)
    single_ndcg10 = topn.ndcg(recs, truth, k=10)

    return single_ndcg5, single_ndcg10, single_rr


if __name__ == "__main__":
    """
    For offline evaluation, set theta in mmr_diversity = 1
    """
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    MODEL, DEVICE = load_model()
    TOKEN_MAPPING = "distilbert-base-uncased"  # can be modified

    mind_data = MindData()

    ngood = 0
    nbad = 0
    ndcg5 = []
    ndcg10 = []
    recip_rank = []

    pipeline = personalized_pipeline(TEST_REC_COUNT)

    logger.info("measuring recommendations")
    user_out_fn = project_root() / "outputs" / "user-metrics.csv"
    user_out_fn.parent.mkdir(exist_ok=True, parents=True)
    user_out = open(user_out_fn, "wt")
    user_csv = csv.writer(user_out)
    user_csv.writerow(["user_id", "NDCG@5", "NDCG@10", "RecipRank"])

    for request in tqdm(islice(mind_data.iter_users(), 25), total=mind_data.n_users, desc="recommend"):  # one by one
        logger.debug("recommending for user %s", request.interest_profile.profile_id)
        if request.num_recs != TEST_REC_COUNT:
            logger.warn(
                "request for %s had unexpected recommendation count %d",
                request.interest_profile.profile_id,
                request.num_recs,
            )
        try:
            recommendations = pipeline(
                {
                    "candidate": ArticleSet(articles=request.todays_articles),
                    "clicked": ArticleSet(articles=request.past_articles),
                    "profile": request.interest_profile,
                }
            )
        except Exception as e:
            logger.error("error recommending for user %s: %s", request.interest_profile.profile_id, e)
            user_csv.writerow([request.interest_profile.profile_id, None, None, None])
            nbad += 1
            continue

        logger.debug("measuring for user %s", request.interest_profile.profile_id)
        single_ndcg5, single_ndcg10, single_rr = recsys_metric(mind_data, request, recommendations)
        user_csv.writerow([request.interest_profile.profile_id, single_ndcg5, single_ndcg10, single_rr])
        # recommendations {account id (uuid): LIST[Article]}
        print(
            f"----------------evaluation for {request.interest_profile.profile_id} is NDCG@5 = {single_ndcg5}, NDCG@10 = {single_ndcg10}, RR = {single_rr}"  # noqa: E501
        )

        ndcg5.append(single_ndcg5)
        ndcg10.append(single_ndcg10)
        recip_rank.append(single_rr)
        ngood += 1

    user_out.close()

    logger.info("recommended for %d users", ngood)
    if nbad:
        logger.error("recommendation FAILED for %d users", nbad)
    agg_metrics = {
        "NDCG@5": np.mean(ndcg5),
        "NDCG@10": np.mean(ndcg10),
        "MRR": np.mean(recip_rank),
    }
    out_fn = project_root() / "outputs" / "metrics.json"
    out_fn.parent.mkdir(exist_ok=True, parents=True)
    out_fn.write_text(json.dumps(agg_metrics) + "\n")
    print(
        f"Offline evaluation metrics on MIND data: NDCG@5 = {np.mean(ndcg5)}, NDCG@10 = {np.mean(ndcg10)}, MRR = {np.mean(recip_rank)}"  # noqa: E501
    )

    # response = {"statusCode": 200, "body": json.dump(body, default=custom_encoder)}
