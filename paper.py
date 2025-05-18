import re
import tarfile
from contextlib import ExitStack
from functools import cached_property
from tempfile import TemporaryDirectory

import arxiv
from loguru import logger


class ArxivPaper:
    def __init__(self, paper: arxiv.Result):
        self._paper = paper
        self.score = None

    @property
    def title(self) -> str:
        return self._paper.title

    @property
    def summary(self) -> str:
        return self._paper.summary

    @property
    def authors(self) -> list[str]:
        return self._paper.authors

    @cached_property
    def arxiv_id(self) -> str:
        return re.sub(r"v\d+$", "", self._paper.get_short_id())

    @property
    def pdf_url(self) -> str:
        return self._paper.pdf_url

    @cached_property
    def tex(self) -> dict[str, str]:
        with ExitStack() as stack:
            tmpdirname = stack.enter_context(TemporaryDirectory())
            file = self._paper.download_source(dirpath=tmpdirname)
            try:
                tar = stack.enter_context(tarfile.open(file))
            except tarfile.ReadError:
                logger.debug(f"Failed to find main tex file of {self.arxiv_id}: Not a tar file.")
                return None

            tex_files = [f for f in tar.getnames() if f.endswith(".tex")]
            if len(tex_files) == 0:
                logger.debug(f"Failed to find main tex file of {self.arxiv_id}: No tex file.")
                return None

            bbl_file = [f for f in tar.getnames() if f.endswith(".bbl")]
            match len(bbl_file):
                case 0:
                    if len(tex_files) > 1:
                        logger.debug(
                            f"Cannot find main tex file of {self.arxiv_id} from bbl: There are multiple tex files while no bbl file."
                        )
                        main_tex = None
                    else:
                        main_tex = tex_files[0]
                case 1:
                    main_name = bbl_file[0].replace(".bbl", "")
                    main_tex = f"{main_name}.tex"
                    if main_tex not in tex_files:
                        logger.debug(
                            f"Cannot find main tex file of {self.arxiv_id} from bbl: The bbl file does not match any tex file."
                        )
                        main_tex = None
                case _:
                    logger.debug(
                        f"Cannot find main tex file of {self.arxiv_id} from bbl: There are multiple bbl files."
                    )
                    main_tex = None
            if main_tex is None:
                logger.debug(
                    f"Trying to choose tex file containing the document block as main tex file of {self.arxiv_id}"
                )
            # read all tex files
            file_contents = {}
            for t in tex_files:
                f = tar.extractfile(t)
                content = f.read().decode("utf-8", errors="ignore")
                # remove comments
                content = re.sub(r"%.*\n", "\n", content)
                content = re.sub(r"\\begin{comment}.*?\\end{comment}", "", content, flags=re.DOTALL)
                content = re.sub(r"\\iffalse.*?\\fi", "", content, flags=re.DOTALL)
                # remove redundant \n
                content = re.sub(r"\n+", "\n", content)
                content = re.sub(r"\\\\", "", content)
                # remove consecutive spaces
                content = re.sub(r"[ \t\r\f]{3,}", " ", content)
                if main_tex is None and re.search(r"\\begin\{document\}", content):
                    main_tex = t
                    logger.debug(f"Choose {t} as main tex file of {self.arxiv_id}")
                file_contents[t] = content

            if main_tex is not None:
                main_source: str = file_contents[main_tex]
                # find and replace all included sub-files
                include_files = re.findall(r"\\input\{(.+?)\}", main_source) + re.findall(
                    r"\\include\{(.+?)\}", main_source
                )
                for f in include_files:
                    if not f.endswith(".tex"):
                        file_name = f + ".tex"
                    else:
                        file_name = f
                    main_source = main_source.replace(f"\\input{{{f}}}", file_contents.get(file_name, ""))
                file_contents["all"] = main_source
            else:
                logger.debug(
                    f"Failed to find main tex file of {self.arxiv_id}: No tex file containing the document block."
                )
                file_contents["all"] = None
        return file_contents
