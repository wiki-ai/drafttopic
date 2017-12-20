"""
    Fetches text for labelings using a MediaWiki API.
    Usage:
        fetch_text --api-host=<url> [--labelings=<path>] [--output=<path>]
                                    [--verbose]

    Options:
        -h --help           Show this documentation.
        --api-host=<url>    The hostname of a MediaWiki e.g.
                            "https://en.wikipedia.org"
        --labelings=<path>  Path to a containting observations with extracted
                            labels. [default: <stdin>]
        --output=<path>     Path to a file to write new observations
                            (with text) out to. [default: <stdout>]
        --verbose           Prints dots and stuff to stderr
"""
import re
import sys

import mwapi
from docopt import docopt
from revscoring.utilities.util import dump_observation, read_observations


def main(argv=None):
    args = docopt(__doc__, argv=argv)

    if args['--labelings'] == '<stdin>':
        labelings = read_observations(sys.stdin)
    else:
        labelings = read_observations(open(args['--labelings']))

    if args['--output'] == '<stdout>':
        output = sys.stdout
    else:
        output = open(args['--output'], 'w')

    session = mwapi.Session(args['--api-host'],
                            user_agent="Drafttopic fetch_text utility.")

    verbose = args['--verbose']

    run(labelings, output, session, verbose)


def run(labelings, output, session, verbose):

    for labeling in fetch_text(session, labelings, verbose=verbose):
        if labeling['text'] is not None:
            dump_observation(labeling, output)


def fetch_text(session, labelings, verbose=False):
    """
    Fetches article text for labelings from a MediaWiki API.
    :Parameters:
        session : :class:`mwapi.Session`
            An API session to use for querying
        labelings : `iterable`(`dict`)
            A collection of labeling events to add text to
        verbose : `bool`
            Print dots and stuff
    :Returns:
        An `iterator` of labelings augmented with 'text'.  Note that labelings
        of articles that aren't found will not be
        included.
    """

    for labeling in labelings:
        rev_doc = get_rev_from_title(session, labeling['page_title'])

        if rev_doc is None:
            if verbose:
                sys.stderr.write("?")
                sys.stderr.write(
                    labeling['page_title'])
                sys.stderr.flush()
        else:
            if verbose:
                sys.stderr.write(".")
                sys.stderr.flush()

            text = rev_doc.get("*")
            if not_an_article(text):
                labeling['text'] = None
            else:
                labeling['text'] = text

            yield labeling

    if verbose:
        sys.stderr.write("\n")
        sys.stderr.flush()


def get_rev_from_title(session, page_title):
    doc = session.get(action="query", prop="revisions", titles=page_title,
                      rvprop=["content"], redirects=True)

    try:
        page_doc = list(doc['query']['pages'].values())[0]
    except (KeyError, IndexError):
        # No pages found
        return None

    try:
        rev_doc = page_doc['revisions'][0]
        rev_doc['page'] = {k: v for k, v in page_doc.items()
                           if k != "revisions"}
    except (KeyError, IndexError):
        # No revisions matched
        return None

    return rev_doc


REDIRECT_RE = re.compile("#redirect", re.I)


def not_an_article(text):
    return (text is None or
            len(text) < 50 or
            REDIRECT_RE.match(text))
