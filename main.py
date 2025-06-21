import argparse
import os
import sys
from tempfile import mkstemp

import arxiv
import feedparser
from dotenv import load_dotenv
from gitignore_parser import parse_gitignore
from loguru import logger
from pyzotero import zotero
from tqdm import tqdm

from construct_email import render_email, send_email
from llm import set_global_llm
from paper import ArxivPaper
from recommender import rank_papers

load_dotenv(override=True)
os.environ["TOKENIZERS_PARALLELISM"] = "false"


def get_zotero_corpus(id: str, key: str) -> list[dict]:
    zot = zotero.Zotero(id, "user", key)
    collections = zot.everything(zot.collections())
    collections = {c["key"]: c for c in collections}
    corpus = zot.everything(zot.items(itemType="conferencePaper || journalArticle || preprint"))
    corpus = [c for c in corpus if c["data"]["abstractNote"] != ""]

    def get_collection_path(col_key: str) -> str:
        if p := collections[col_key]["data"]["parentCollection"]:
            return get_collection_path(p) + "/" + collections[col_key]["data"]["name"]
        else:
            return collections[col_key]["data"]["name"]

    for c in corpus:
        paths = [get_collection_path(col) for col in c["data"]["collections"]]
        c["paths"] = paths
    return corpus


def filter_corpus(corpus: list[dict], pattern: str) -> list[dict]:
    _, filename = mkstemp()
    with open(filename, "w") as file:
        file.write(pattern)
    matcher = parse_gitignore(filename, base_dir="./")
    new_corpus = []
    for c in corpus:
        match_results = [matcher(p) for p in c["paths"]]
        if not any(match_results):
            new_corpus.append(c)
    os.remove(filename)
    return new_corpus


def filter_corpus_by_tag(corpus: list[dict], tag: str) -> list[dict]:
    """Filter corpus to only include papers with the specified tag."""
    return [c for c in corpus if any(t["tag"] == tag for t in c["data"]["tags"])]


def get_arxiv_paper(query: str, debug: bool = False) -> list[ArxivPaper]:
    client = arxiv.Client(num_retries=10, delay_seconds=10)
    feed = feedparser.parse(f"https://rss.arxiv.org/atom/{query}")
    if "Feed error for query" in feed.feed.title:
        raise Exception(f"Invalid ARXIV_QUERY: {query}.")
    if not debug:
        papers = []
        all_paper_ids = [i.id.removeprefix("oai:arXiv.org:") for i in feed.entries if i.arxiv_announce_type == "new"]
        bar = tqdm(total=len(all_paper_ids), desc="Retrieving Arxiv papers")
        for i in range(0, len(all_paper_ids), 50):
            search = arxiv.Search(id_list=all_paper_ids[i : i + 50])
            batch = [ArxivPaper(p) for p in client.results(search)]
            bar.update(len(batch))
            papers.extend(batch)
        bar.close()

    else:
        logger.debug("Retrieve 5 arxiv papers regardless of the date.")
        search = arxiv.Search(query="cat:cs.AI", sort_by=arxiv.SortCriterion.SubmittedDate)
        papers = []
        for i in client.results(search):
            papers.append(ArxivPaper(i))
            if len(papers) == 5:
                break

    return papers


parser = argparse.ArgumentParser(description="Recommender system for academic papers")


def add_argument(*args, **kwargs):
    def get_env(key: str, default=None):
        # handle environment variables generated at Workflow runtime
        # Unset environment variables are passed as '', we should treat them as None
        v = os.environ.get(key)
        if v == "" or v is None:
            return default
        return v

    parser.add_argument(*args, **kwargs)
    arg_full_name = kwargs.get("dest", args[-1][2:])
    env_name = arg_full_name.upper()
    env_value = get_env(env_name)
    if env_value is not None:
        # convert env_value to the specified type
        if kwargs.get("type") is bool:
            env_value = env_value.lower() in ["true", "1"]
        else:
            env_value = kwargs.get("type")(env_value)
        parser.set_defaults(**{arg_full_name: env_value})


if __name__ == "__main__":
    add_argument("--zotero_id", type=str, help="Zotero user ID", required=True)
    add_argument("--zotero_key", type=str, help="Zotero API key", required=True)
    add_argument(
        "--zotero_ignore",
        type=str,
        help="Zotero collection to ignore, using gitignore-style pattern.",
    )
    add_argument(
        "--send_empty",
        type=bool,
        help="If get no arxiv paper, send empty email",
        default=False,
    )
    add_argument(
        "--min_score",
        type=float,
        help="Minimum score of papers to recommend",
        default=-0.1,
    )
    add_argument("--arxiv_query", type=str, help="Arxiv search query", required=True)
    add_argument(
        "--zotero_tags",
        type=str,
        help="Comma-separated list of Zotero tags. Each tag will result in a separate list of papers. If not provided, the full Zotero corpus is considered.",
        default=None,
    )
    add_argument("--smtp_server", type=str, help="SMTP server", required=True)
    add_argument("--smtp_port", type=int, help="SMTP port", required=True)
    add_argument("--sender", type=str, help="Sender email address", required=True)
    add_argument("--receiver", type=str, help="Receiver email address", required=True)
    add_argument("--sender_password", type=str, help="Sender email password", required=True)
    add_argument(
        "--use_llm_api",
        type=bool,
        help="Use OpenAI API to generate TLDR",
        default=False,
    )
    add_argument(
        "--openai_api_key",
        type=str,
        help="OpenAI API key",
        default=None,
    )
    add_argument(
        "--openai_api_base",
        type=str,
        help="OpenAI API base URL",
        default="https://api.openai.com/v1",
    )
    add_argument(
        "--model_name",
        type=str,
        help="LLM Model Name",
        default="gpt-4o",
    )
    add_argument(
        "--language",
        type=str,
        help="Language of TLDR",
        default="English",
    )
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()
    assert (
        not args.use_llm_api or args.openai_api_key is not None
    )  # If use_llm_api is True, openai_api_key must be provided
    if args.debug:
        logger.remove()
        logger.add(sys.stdout, level="DEBUG")
        logger.debug("Debug mode is on.")
    else:
        logger.remove()
        logger.add(sys.stdout, level="INFO")

    logger.info("Retrieving Zotero corpus...")
    corpus = get_zotero_corpus(args.zotero_id, args.zotero_key)
    logger.info(f"Retrieved {len(corpus)} papers from Zotero.")
    if args.zotero_ignore:
        logger.info(f"Ignoring papers in:\n {args.zotero_ignore}...")
        corpus = filter_corpus(corpus, args.zotero_ignore)
        logger.info(f"Remaining {len(corpus)} papers after filtering.")
    logger.info("Retrieving Arxiv papers...")
    papers = get_arxiv_paper(args.arxiv_query, args.debug)
    n_papers_init = len(papers)

    if args.zotero_tags:
        tags = [tag.strip() for tag in args.zotero_tags.split(",")]
        logger.info(f"Processing papers for tags: {tags}")

        tag_papers = {}
        tag_debug_info = {}
        for tag in tags:
            logger.info(f"Ranking papers for tag: {tag}")
            tag_corpus = filter_corpus_by_tag(corpus, tag)
            if not tag_corpus:
                logger.warning(f"No papers found in Zotero corpus with tag '{tag}'. Skipping.")
                continue
            logger.info(f"Found {len(tag_corpus)} papers with tag '{tag}' in Zotero corpus.")

            ranked_papers, debug_info = rank_papers(papers.copy(), tag_corpus, min_score=args.min_score)

            tag_debug_info[tag] = debug_info
            tag_papers[tag] = ranked_papers
            if ranked_papers:
                logger.info(f"Found {len(ranked_papers)} papers above threshold for tag '{tag}'.")
            else:
                logger.info(f"No papers found above threshold {args.min_score} for tag '{tag}'.")

        if not any(tag_papers.values()) and not args.send_empty:
            logger.info(
                f"No papers found above the threshold {args.min_score} for any tag (out of {n_papers_init} papers). Exit."
            )
            exit(0)

        all_papers = tag_papers
        debug_info = tag_debug_info
        use_sections = True
    else:
        logger.info("Ranking papers against full corpus...")
        papers, debug_info = rank_papers(papers, corpus, min_score=args.min_score)
        if len(papers) == 0 and not args.send_empty:
            logger.info(f"No papers found above the threshold {args.min_score} (out of {n_papers_init} papers). Exit.")
            exit(0)
        all_papers = {None: papers}
        debug_info = {None: debug_info}
        use_sections = False

    if args.use_llm_api:
        logger.info("Using OpenAI API as global LLM.")
        set_global_llm(
            api_key=args.openai_api_key,
            base_url=args.openai_api_base,
            model=args.model_name,
            lang=args.language,
        )
    else:
        logger.info("Using Local LLM as global LLM.")
        set_global_llm(lang=args.language)

    global_debug_info = {
        "threshold": args.min_score,
        "papers_considered": n_papers_init,
        "use_sections": use_sections,
    }

    html = render_email(all_papers, debug_info, global_debug_info)
    logger.info("Sending email...")
    send_email(
        args.sender,
        args.receiver,
        args.sender_password,
        args.smtp_server,
        args.smtp_port,
        html,
    )
    logger.success(
        "Email sent successfully! If you don't receive the email, please check the configuration and the junk box."
    )
