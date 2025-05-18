from sentence_transformers import SentenceTransformer

from paper import ArxivPaper


def rerank_paper(
    candidate: list[ArxivPaper], corpus: list[dict], model: str = "avsolatorio/GIST-small-Embedding-v0"
) -> list[ArxivPaper]:
    encoder = SentenceTransformer(model)
    corpus_feature = encoder.encode([paper["data"]["abstractNote"] for paper in corpus])
    candidate_feature = encoder.encode([paper.summary for paper in candidate])
    sim = encoder.similarity(candidate_feature, corpus_feature)  # [n_candidate, n_corpus]
    scores = sim.sum(axis=1) * 10  # [n_candidate]
    for s, c in zip(scores, candidate):
        c.score = s.item()
    candidate = sorted(candidate, key=lambda x: x.score, reverse=True)
    return candidate
