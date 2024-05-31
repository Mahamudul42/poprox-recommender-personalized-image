import json

import torch as th
from safetensors.torch import load_file

from poprox_recommender.default import select_articles
from poprox_recommender.paths import project_root


def load_model(device_name=None):
    checkpoint = None

    if device_name is None:
        device_name = "cuda" if th.cuda.is_available() else "cpu"

    load_path = f"{project_root()}/models/model.safetensors"

    checkpoint = load_file(load_path)
    return checkpoint, device_name

MODEL, DEVICE = load_model()
TOKEN_MAPPING = 'distilbert-base-uncased' # can be modified


def generate_recs(event, context):
    request_body = json.loads(event["body"])

    todays_articles = request_body["todays_articles"]
    past_articles = request_body["past_articles"]
    click_data = request_body["click_data"]
    num_recs = request_body["num_recs"]

    recommendations = select_articles(
        todays_articles,
        past_articles,
        click_data,
        MODEL,
        DEVICE,
        TOKEN_MAPPING,
        num_recs,
    )
    body = {
        "recommendations": recommendations,
    }

    response = {"statusCode": 200, "body": json.dumps(body)}

    return response
