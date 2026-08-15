import json

from src.extract.requirements import BedrockExtractor
from src.ingest.base import FitAnalysis, Posting, Requirements
from src.llm.bedrock import BedrockLLM, extract_json
from src.profile.candidate import CandidateProfile, MasterBullet
from src.tailor.build import build_materials


class FakeBedrockClient:
    """Stand-in for boto3 bedrock-runtime: returns a canned Converse reply."""

    def __init__(self, reply_text: str):
        self.reply_text = reply_text
        self.last_kwargs = None

    def converse(self, **kwargs):
        self.last_kwargs = kwargs
        return {"output": {"message": {"content": [{"text": self.reply_text}]}}}


def test_converse_builds_expected_request_and_parses_reply():
    fake = FakeBedrockClient("hello world")
    llm = BedrockLLM(model_id="amazon.nova-lite-v1:0", client=fake)
    out = llm.converse("SYS", "USER", max_tokens=50, temperature=0.1)
    assert out == "hello world"
    kw = fake.last_kwargs
    assert kw["modelId"] == "amazon.nova-lite-v1:0"
    assert kw["system"] == [{"text": "SYS"}]
    assert kw["messages"][0]["content"][0]["text"] == "USER"
    assert kw["inferenceConfig"] == {"maxTokens": 50, "temperature": 0.1}


def test_extract_json_tolerates_fenced_output():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def _posting():
    return Posting(source="greenhouse", source_url="https://x/jobs/1", company="Acme",
                   title="Senior Backend Engineer",
                   description="Requirements: Python and AWS. Must have 5 years.")


def test_llm_extractor_drops_fabricated_skills():
    # Model claims Rust with a quote that ISN'T in the JD -> must be dropped.
    reply = json.dumps({
        "must_have_skills": ["Python", "AWS", "Rust"],
        "nice_to_have_skills": [],
        "years_experience": 5,
        "work_authorization": None,
        "evidence": {
            "Python": "Requirements: Python and AWS.",
            "AWS": "Python and AWS.",
            "Rust": "We love Rust here.",          # NOT in the JD
            "years_experience": "Must have 5 years.",
        },
    })
    extractor = BedrockExtractor(BedrockLLM(client=FakeBedrockClient(reply)))
    reqs = extractor.extract(_posting())
    assert "python" in reqs.must_have_skills
    assert "aws" in reqs.must_have_skills
    assert "rust" not in reqs.must_have_skills          # fabrication rejected
    assert reqs.years_experience == 5
    # every surviving skill carries grounded evidence
    for s in reqs.must_have_skills:
        assert s in reqs.evidence


def test_llm_extractor_grounds_fields_and_hard_reqs():
    reply = json.dumps({
        "must_have_skills": ["Python"],
        "work_authorization": "Must be authorized to work in the US",
        "evidence": {
            "Python": "Python and AWS",
            "work_authorization": "hallucinated quote not present",
        },
    })
    # work_authorization quote isn't in the JD -> field dropped, no hard req
    reqs = BedrockExtractor(BedrockLLM(client=FakeBedrockClient(reply))).extract(_posting())
    assert reqs.work_authorization is None
    assert reqs.hard_requirements == []


def test_llm_cover_letter_uses_client_and_facts():
    cand = CandidateProfile(name="Alex", headline="Staff Engineer",
                            master_bullets=[MasterBullet("b1", "Built AWS pipelines.", ["aws"])])
    reqs = Requirements(must_have_skills=["aws"])
    fit = FitAnalysis(fit_score=0.8, matched_skills=["aws"], gaps=[], recommendation="apply")
    fake = FakeBedrockClient("Dear Acme, I'm a great fit. — Alex")
    m = build_materials(cand, _posting(), reqs, fit, llm=BedrockLLM(client=fake))
    assert m.cover_letter.startswith("Dear Acme")
    # the model was handed only real facts (never work authorization)
    facts = json.loads(fake.last_kwargs["messages"][0]["content"][0]["text"])
    assert facts["candidate_name"] == "Alex"
    assert facts["real_resume_bullets"] == ["Built AWS pipelines."]
    # provenance still holds for highlights
    from src.tailor.resume import verify_provenance
    assert verify_provenance(m, cand)
