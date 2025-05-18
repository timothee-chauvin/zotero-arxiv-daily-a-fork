from loguru import logger
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
) -> list[ArxivPaper]:
    encoder = SentenceTransformer(model)
    corpus_features = encoder.encode([paper["data"]["abstractNote"] for paper in corpus])
    candidate_features = encoder.encode([paper.summary for paper in candidates])

    scaler = StandardScaler()
    corpus_features_scaled = scaler.fit_transform(corpus_features)
    candidate_features_scaled = scaler.transform(candidate_features)

    ocsvm = OneClassSVM(nu=nu, kernel="rbf", gamma=gamma)
    ocsvm.fit(corpus_features_scaled)
    scores = ocsvm.decision_function(candidate_features_scaled)
    logger.debug(f"min score: {min(scores).item():.3f}")
    logger.debug(f"max score: {max(scores).item():.3f}")
    for score, candidate in zip(scores, candidates):
        candidate.score = score.item()
    candidates = [c for c in candidates if c.score >= min_score]
    candidates = sorted(candidates, key=lambda x: x.score, reverse=True)
    return candidates
