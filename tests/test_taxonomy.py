from src.match.taxonomy import family_of, normalize_skill, normalize_skills


def test_synonyms_map_to_canonical():
    assert normalize_skill("React.js") == "react"
    assert normalize_skill("nodejs") == "node"
    assert normalize_skill("Golang") == "go"
    assert normalize_skill("PostgreSQL") == "postgres"
    assert normalize_skill("K8s") == "kubernetes"


def test_unknown_skill_is_identity():
    assert normalize_skill("COBOL") == "cobol"


def test_normalize_skills_dedupes_preserving_order():
    out = normalize_skills(["React", "react.js", "AWS", "amazon web services"])
    assert out == ["react", "aws"]


def test_family_lookup():
    assert family_of("python") == "language"
    assert family_of("kubernetes") == "infra"
    assert family_of("cobol") == "other"
