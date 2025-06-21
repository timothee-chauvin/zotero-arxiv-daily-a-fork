from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from paper import ArxivPaper


def rank_papers(
    candidates: list[ArxivPaper],
    corpus: list[dict],
    model: str = "avsolatorio/GIST-small-Embedding-v0",
    nu: float = 0.1,
    gamma: str = "scale",
    min_score: float = -0.1,
) -> tuple[list[ArxivPaper], dict]:
    encoder = SentenceTransformer(model)
    corpus_features = encoder.encode([paper["data"]["abstractNote"] for paper in corpus])
    candidate_features = encoder.encode([paper.summary for paper in candidates])

    scaler = StandardScaler()
    corpus_features_scaled = scaler.fit_transform(corpus_features)
    candidate_features_scaled = scaler.transform(candidate_features)

    ocsvm = OneClassSVM(nu=nu, kernel="rbf", gamma=gamma)
    ocsvm.fit(corpus_features_scaled)
    scores = ocsvm.decision_function(candidate_features_scaled)

    debug_info = {
        "max_score": max(scores).item(),
        "min_score": min(scores).item(),
    }

    for score, candidate in zip(scores, candidates):
        candidate.score = score.item()
    matching_papers = [c for c in candidates if c.score >= min_score]
    matching_papers = sorted(matching_papers, key=lambda x: x.score, reverse=True)
    return matching_papers, debug_info
