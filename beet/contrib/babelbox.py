"""Plugin that loads translations from csv files.

Adapted from https://github.com/OrangeUtan/babelbox
Credit: Oran9eUtan <Oran9eUtan@gmail.com>
"""


__all__ = [
    "BabelboxOptions",
    "babelbox",
    "load_languages",
]


import logging
from csv import Dialect, DictReader, Sniffer
from typing import Dict, List, Optional, Type, Union

from pydantic import BaseModel

from beet import Context, Language, configurable
from beet.core.utils import FileSystemPath

DialectLike = Union[str, Dialect, Type[Dialect]]


logger = logging.getLogger(__name__)


class BabelboxOptions(BaseModel):
    load: List[str] = []
    dialect: Optional[str] = None
    filename_prefix: bool = False


def beet_default(ctx: Context):
    ctx.require(babelbox)


@configurable(validator=BabelboxOptions)
def babelbox(ctx: Context, opts: BabelboxOptions):
    """Plugin that loads translations from csv files."""
    minecraft = ctx.assets["minecraft"]

    for pattern in opts.load:
        for path in ctx.directory.glob(pattern):
            minecraft.languages.merge(
                load_languages(
                    path=path,
                    dialect=opts.dialect,
                    prefix=path.stem + "." if opts.filename_prefix else "",
                )
            )


def load_languages(
    path: FileSystemPath,
    dialect: Optional[DialectLike] = None,
    prefix: str = "",
) -> Dict[str, Language]:
    """Return a dictionnary mapping each column to a language file."""
    with open(path, newline="") as csv_file:
        if not dialect:
            dialect = Sniffer().sniff(csv_file.read(1024))
            csv_file.seek(0)

        reader: DictReader[str] = DictReader(csv_file, dialect=dialect)

        key, *language_codes = reader.fieldnames or [""]
        languages = {code: Language() for code in language_codes}

        for row in reader:
            if not (identifier := row[key]):
                continue

            identifier = prefix + identifier

            for code in language_codes:
                if value := row[code]:
                    languages[code].data[identifier] = value
                else:
                    msg = f"Locale {code!r} has no translation for {identifier!r}."
                    logger.warning(msg)

        return languages
