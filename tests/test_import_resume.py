import json

from src.llm.bedrock import BedrockLLM
from src.profile.candidate import CandidateProfile
from src.profile.import_resume import (
    build_profile_dict,
    profile_from_text_heuristic,
    profile_from_text_llm,
    read_resume_text,
    to_yaml,
)

RESUME = """\
Marcio Yoshida
Staff Software Engineer

Experience
- Built a serverless data pipeline on AWS Lambda processing 10M events/day using Python.
- Designed PostgreSQL schemas for a fintech ledger handling BRL settlements.
- Led migration to Kubernetes, cutting deploy time 60%.

Skills: Python, AWS, PostgreSQL, Docker, Kubernetes
"""


class FakeClient:
    def __init__(self, reply):
        self.reply = reply

    def converse(self, **kw):
        return {"output": {"message": {"content": [{"text": self.reply}]}}}


def test_read_txt(tmp_path):
    p = tmp_path / "cv.txt"
    p.write_text(RESUME)
    assert "Staff Software Engineer" in read_resume_text(p)


def test_heuristic_extracts_skills_and_bullets():
    raw = profile_from_text_heuristic(RESUME)
    assert raw["name"] == "Marcio Yoshida"
    assert "python" in raw["skills"] and "kubernetes" in raw["skills"]
    texts = " ".join(b["text"] for b in raw["master_bullets"])
    assert "serverless data pipeline" in texts
    # a bullet mentioning AWS/Lambda gets those skills tagged
    aws_bullet = next(b for b in raw["master_bullets"] if "Lambda" in b["text"])
    assert "aws" in aws_bullet["skills"] and "lambda" in aws_bullet["skills"]


def test_build_profile_assigns_ids_and_parses():
    raw = profile_from_text_heuristic(RESUME)
    profile = build_profile_dict(raw)
    assert profile["master_bullets"][0]["id"] == "b1"
    # round-trips into a usable CandidateProfile
    cand = CandidateProfile.from_dict(profile)
    assert "python" in cand.normalized_skills()
    assert cand.master_bullets[0].id == "b1"


def test_llm_path_structures_from_reply():
    reply = json.dumps({
        "name": "Marcio Yoshida", "headline": "Staff Software Engineer",
        "skills": ["Python", "AWS", "Kubernetes"],
        "master_bullets": [
            {"text": "Built AWS Lambda pipelines in Python.", "skills": ["python", "aws", "lambda"]},
            {"text": "", "skills": []},   # empty -> dropped by build
        ],
    })
    raw = profile_from_text_llm(RESUME, BedrockLLM(client=FakeClient(reply)))
    profile = build_profile_dict(raw)
    assert profile["headline"] == "Staff Software Engineer"
    assert len(profile["master_bullets"]) == 1          # empty bullet dropped
    assert profile["master_bullets"][0]["id"] == "b1"


def test_to_yaml_roundtrips(tmp_path):
    import yaml

    profile = build_profile_dict(profile_from_text_heuristic(RESUME))
    text = to_yaml(profile)
    loaded = yaml.safe_load(text)
    assert CandidateProfile.from_dict(loaded).name == "Marcio Yoshida"
