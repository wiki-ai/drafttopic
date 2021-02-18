"""
``$ drafttopic fetch_article_text -h``
::

    Fetches most recent text for observations using a MediaWiki API.

    Usage:
        fetch_article_text --api-host=<url>
                           [--input=<path>] [--output=<path>]
                           [--threads=<num>] [--tok_strategy=<str>] [--debug]

    Options:
        -h --help           Show this documentation.
        --api-host=<url>    The hostname of a MediaWiki e.g.
                            "https://en.wikipedia.org"
        --input=<path>      Path to a containting observations with extracted
                            labels. [default: <stdin>]
        --output=<path>     Path to a file to write new observations
                            (with text) out to. [default: <stdout>]
        --threads=<num>     The number of parallel query threads to run
                            [default: 4]
        --tok_strategy=<str>Tokenization strategy supported by python-mwtext,
                            None is default
        --debug             Print debug logging
"""
import logging
import sys
from concurrent.futures import ThreadPoolExecutor

import mwapi
from docopt import docopt
from revscoring.utilities.util import dump_observation, read_observations

from mwtext.content_transformers import Wikitext2Words
forbidden_link_prefixes = [
    'category', 'image', 'file']

from .fetch_draft_text import DRAFTTOPIC_UA, build_fetch_text

logger = logging.getLogger(__name__)


def main(argv=None):
    args = docopt(__doc__, argv=argv)

    logging.basicConfig(
        level=logging.INFO if not args['--debug'] else logging.DEBUG,
        format='%(asctime)s %(levelname)s:%(name)s -- %(message)s')
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

    if args['--input'] == '<stdin>':
        observations = read_observations(sys.stdin)
    else:
        observations = read_observations(open(args['--input']))

    if args['--output'] == '<stdout>':
        output = sys.stdout
    else:
        output = open(args['--output'], 'w')

    threads = int(args['--threads'])

    tok_strategy = None if not args['--tok_strategy'] else str(args['--tok_strategy'])
    wtpp = Wikitext2Words(forbidden_link_prefixes, tok_strategy=tok_strategy)

    session = mwapi.Session(args['--api-host'],
                            user_agent=DRAFTTOPIC_UA)

    run(observations, session, threads, output, wtpp)


def run(observations, session, threads, output, wtpp):
    for obs in fetch_article_texts(observations, session, threads, wtpp):
        dump_observation(obs, output)


def fetch_article_texts(observations, session, threads, wtpp):
    """
    Fetches article (recent revision) text for observations from a
    MediaWiki API.
    """

    executor = ThreadPoolExecutor(max_workers=threads)
    _fetch_article_text = build_fetch_text(build_get_recent_revision(session), wtpp)

    for obs in executor.map(_fetch_article_text, observations):
        if obs is not None:
            yield obs
            logger.debug("Write {0} with {1} chars of text."
                         .format(obs['title'], len(obs['text'])))


def build_get_recent_revision(session):
    def get_recent_revision(title):
        return session.get(
            action="query",
            prop="revisions",
            rvprop=["content", "ids"],
            titles=title,
            redirects=True,
            rvlimit=1,
            rvdir="older",
            formatversion=2,
            rvslots=["main"]
        )
    return get_recent_revision
