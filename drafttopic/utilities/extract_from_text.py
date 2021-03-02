"""
``drafttopic extract_from_text -h``::

    Extracts dependents from a labeling doc containing text label and
    writes a new set of labeling docs that is compatible as observations
    for revscoring's cv_train and tune utilities.
    Input: ``{ ... "mid-level-categories": ...,"text": ..., ... }``
    Output: ``{ ... "mid-level-categories": ..., "cache": ..., ... }``

    Usage:
        extract_from_text <dependent>...
                          [--input=<path>]
                          [--output=<path>]
                          [--extractors=<num>]
                          [--tok_strategy=<str>]
                          [--verbose]
                          [--debug]

    Options:
        -h --help               Print this documentation
        <dependent>             Classpath to a single dependent or list of
                                dependent values to solve
        --input=<path>          Path to a file containing observations
                                [default: <stdin>]
        --output=<path>         Path to a file to write new observations to
                                [default: <stdout>]
        --extractors=<num>      The number of parallel extractors to
                                start [default: <cpu count>]
        --tok_strategy=<str>    tokenization strategy
        --verbose               Print dots and stuff to stderr
        --debug                 Print debug logs
"""
import logging
import sys
from multiprocessing import Pool, cpu_count

import docopt
import yamlconf
from revscoring import Dependent
from revscoring.datasources import revision_oriented
from revscoring.dependencies import solve
from revscoring.utilities.util import dump_observation, read_observations

from mwtext.content_transformers import Wikitext2Words
forbidden_link_prefixes = [
    'category', 'image', 'file']

def main(argv=None):
    args = docopt.docopt(__doc__, argv=argv)

    logging.basicConfig(
        level=logging.WARNING if not args['--debug'] else logging.DEBUG,
        format='%(asctime)s %(levelname)s:%(name)s -- %(message)s'
    )

    dependents = []
    for dependent_path in args['<dependent>']:
        dependent_or_list = yamlconf.import_path(dependent_path)
        if isinstance(dependent_or_list, Dependent):
            dependents.append(dependent_or_list)
        else:
            dependents.extend(dependent_or_list)

    if args['--input'] == "<stdin>":
        observations = read_observations(sys.stdin)
    else:
        observations = read_observations(open(args['--input']))

    if args['--output'] == "<stdout>":
        output = sys.stdout
    else:
        output = open(args['--output'], 'w')

    if args['--extractors'] == "<cpu count>":
        extractors = cpu_count()
    else:
        extractors = int(args['--extractors'])

    verbose = args['--verbose']
    tok_strategy = str(args['--tok_strategy']) if args['--tok_strategy'] is not None else None
    wtpp = Wikitext2Words(forbidden_link_prefixes, tok_strategy=tok_strategy)
    sys.stderr.write("tokenization strategy is: " + tok_strategy)
    sys.stderr.write("\nnumber of processes: " + str(extractors) + "\n")
    run(observations, dependents, output, extractors, wtpp, verbose)


def run(labelings, dependents, output, extractors, wtpp, verbose=False):
    extractor_pool = Pool(processes=extractors)

    extractor = LabelingDependentExtractor(dependents, wtpp)

    for observation in extractor_pool.imap(
            extractor.extract_and_cache, labelings):
        if observation is not None:
            if verbose:
                sys.stderr.write(".")
                sys.stderr.flush()

            dump_observation(observation, output)
        else:
            if verbose:
                sys.stderr.write("-")
                sys.stderr.flush()

    if verbose:
        sys.stderr.write("\n")


class LabelingDependentExtractor:

    def __init__(self, dependents, wtpp):
        self.dependents = dependents
        self.wtpp = wtpp

    def extract_and_cache(self, observation):
        if observation['text'] is None:
            return None

        values = extract_from_text(
            self.dependents, self.wtpp, observation['text'],
            cache=observation.get('cache'))
        dependent_cache = {str(d): val
                           for d, val in zip(self.dependents, values)}

        del observation['text']
        updated_cache = observation.get('cache', {})
        updated_cache.update(dependent_cache)
        observation['cache'] = updated_cache

        return observation


def extract_from_text(dependents, wtpp, text, cache=None, context=None):
    """
    Extracts a set of values from a text an returns a cache containing just
    those values.

    :Parameters:
        dependents : `list`( :class:`revscoring.Dependent` )
            A list of dependents to extract values for
        text : `str`
            A text from which to extract features
    :Returns:
        A list of extracted feature values
    """
    cache = cache if cache is not None else {}
    cache[revision_oriented.revision.text] = ' '.join(wtpp.transform(text))

    return list(solve(dependents, cache=cache, context=context))
