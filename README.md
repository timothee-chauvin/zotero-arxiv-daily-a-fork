# zotero-arxiv-daily, a fork

This is a fork of [zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily), with the following changes:

* multiple domains can be tracked by supplying **a list of Zotero tags**, like so: `--zotero_tags 'tag1,tag2'`. The email contains one section per tag with the matching papers.
* **one-class SVM** is used to compute similarity between papers, instead of average cosine similarity between the embeddings. Instead of stars, the SVM score is shown.
* **only papers above a threshold** are included, instead of a fixed number of papers.
* this fork **doesn't call an LLM** to parse affiliations / presence of a codebase, or generate a one-sentence tldr (these steps are very slow).
* all Zotero papers (within a tag or the full corpus) are ranked equally, **without a time decay factor**.

(minor / dev)

* runs at 6am UTC, 2 hours after arxiv updates its RSS feed.
* pre-commit is used, code is formatted with [ruff](https://github.com/astral-sh/ruff)
* various improvements to the codebase
