"""
Generates a machine readable WikiProjects directory as:
{
'culture': {
    'name': 'Culture',
    'url':
        'https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Council/Directory/Culture',
    'root_url': <root_url>
    'index': <index>
    'topics': {
        'arts': {'name':..., 'url': culture_url+'#arts',
            topics:{
                'Architecture': {'name':
                    'Wikipedia:WikiProject_Architecture','url':...}
            }
        }
    }
}
}
Here:
* root_url: Url of page from which this entry was parsed
* index: sections index to which this entry belongs to
* name: name of entry
All the above mentioned fields will be absent from the base entry
which contain actual WikiProjects name and has only three fields:
    name, shortname, active

Usage:
    fetch_wikiprojects [--output=<path>] [--debug]

Options:
    --output=<path>       Path to an file to write output to
                          [default: <stdout>]
    --debug               Print debug logging
"""
import mwapi
import json
import re
import logging
import docopt
import sys


wpd_page = 'Wikipedia:WikiProject_Council/Directory'
wp_main_heading_regex =\
        r'\[\[Wikipedia:WikiProject Council/Directory/([A-Za-z_, ]+)\|([A-Za-z_, ]+)\]\]='  # noqa: E501
wp_listing_regex =\
        r'See the full listing \[\[Wikipedia:WikiProject Council/Directory/([A-Za-z_,/ ]+)'  # noqa: E501

wp_section_nextheading_regex = r'(.+)[=]{2,}'

wp_section_regex =\
        r'{{Wikipedia:WikiProject Council/Directory/WikiProject\n'\
        '\|project = ([a-zA-Z_: -]+)\n'\
        '\|shortname = ([a-zA-Z\(\) -]+)\n'\
        '\|active = (yes|no)\n([^}]*)}}'
# To check listing in other wikiprojects
wp_section_regex_listed =\
        r'listed-in = ([A-Za-z#/:_ ]+)'


def main(argv=None):
    args = docopt.docopt(__doc__, argv=argv)

    logging.basicConfig(
        level=logging.DEBUG if args['--debug'] else logging.WARNING,
        format='%(asctime)s %(levelname)s:%(name)s -- %(message)s'
    )

    if args['--output'] == "<stdout>":
        output_f = sys.stdout
    else:
        output_f = open(args['--output'], "w")

    run(output_f)


def run(output):
    logger = logging.getLogger(__name__)
    parser = WikiProjectsParser(wpd_page, logger)
    wps = parser.parse_wp_directory()
    output.write(json.dumps(wps, indent=4))


class WikiProjectsParser:
    def __init__(self, wpd_page, logger=None):
        self.root_dir = wpd_page
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
        self.session = mwapi.Session('https://en.wikipedia.org',
                                     user_agent='WP-dev')

    def parse_wp_directory(self):
        """
        Parses the top level WikiProjects directory
        Entry point for WikiProjects parsing
        """
        dirname = self.root_dir
        self.logger.info("Starting WikiProjects parsing")
        wp = {}
        sections = None
        try:
            sections = self.get_sections(dirname)
        except IOError as e:
            self.logger.warn(
                "Failed to get sections in root ,directory, exiting...")
            return None
        projects_started = False
        for sec in sections:
            # Ignore starting sections
            if sec['toclevel'] == 1:
                if projects_started:
                    break
                else:
                    continue
            projects_started = True
            name = sec['line'].replace('&nbsp;', '')
            wp[sec['line']] = {'name': name,
                               'root_url': sec['fromtitle'],
                               'index': sec['index']}
            section = self.get_section_text(dirname, sec['index'])
            main_heading = None
            if section:
                main_heading = re.search(wp_main_heading_regex, section)
            if section and main_heading:
                try:
                    wp[sec['line']]['url'] = wpd_page + '/' +\
                        main_heading.group(1)
                    # Get entries in this section
                    self.logger.info(
                        "Fetching entries for section: {}".format(name))
                    sub_page_sections =\
                        self.get_sections(wp[sec['line']]['url'])
                    wp[sec['line']]['topics'], _ = self.get_sub_categories(
                                                      wp[sec['line']]['url'],
                                                      sub_page_sections,
                                                      0, 0)
                except IOError as e:
                    self.logger.warn("Skipping: {}".
                                     format(wp[sec['line']]['url']))
                    pass
                except:
                    self.logger.warn("Unexpected error: ", sys.exc_info()[0])
                    pass
        self.logger.info("Ended WikiProjects parsing")
        return wp

    def get_sub_categories(self, page, sections, index, level):
        wp = {}
        prev_topic = None
        self.logger.info("Index:{}, Level:{}".format(index, level))
        idx = index
        while idx < len(sections):
            if sections[idx]['toclevel'] - 1 > level:
                sub_categories, new_idx = self.get_sub_categories(
                            page, sections, idx, level+1)
                idx = new_idx
                if sub_categories:
                    wp[prev_topic]['topics'] = {**wp[prev_topic]['topics'],
                                                **sub_categories}
                continue
            elif sections[idx]['toclevel'] - 1 < level:
                return wp, idx
            else:
                entry = {}
                entry['name'] = sections[idx]['line']
                entry['root_url'] = sections[idx]['fromtitle']
                entry['index'] = sections[idx]['index']
                entry['topics'] = {}
                intro_projects = self.get_wikiprojects_from_section_intro(
                                                    page, idx + 1)
                if intro_projects:
                    entry['topics'] = intro_projects
                wp[entry['name']] = entry
            prev_topic = sections[idx]['line']
            idx += 1
        return wp, len(sections)

    def get_wikiprojects_from_section_intro(self, page, index):
        """
        Only gets wikiprojects in intro part of sections, or if this is the
        leaf section, WikiProjects in subsequent subsections not handled here
        """
        wikitext = self.get_section_text(page, index)
        return self.get_wikiprojects_from_section_intro_text(wikitext)

    def get_wikiprojects_from_section_intro_text(self, wikitext):
        wp = {}
        # remove first heading
        wikitext = wikitext.split('\n')
        wikitext = '\n'.join(wikitext[1:])
        match = re.search(wp_section_nextheading_regex, wikitext,
                          re.MULTILINE)
        if match:
            wikitext = wikitext[:match.start()]
            wp = self.get_wikiprojects_from_table(wikitext)
        else:
            wp = self.get_wikiprojects_from_table(wikitext)
        if not wp:
            # Try to match a 'See full listing here' entry
            match = re.search(wp_listing_regex, wikitext)
            if match:
                page_url = wpd_page + '/' + match.group(1)
                sections = self.get_sections(page_url)
                wp, _ = self.get_sub_categories(page_url, sections, 0, 0)
        return wp

    def get_section_text(self, page, section):
        self.logger.info("Fetching section {} from page {}".format(section,
                                                                   page))
        try:
            section = self.session.get(action='parse', page=page,
                                       prop='wikitext', section=section)
            return section['parse']['wikitext']['*']
        except IOError as e:
            self.logger.warn("Failed to request section: {} from {}".
                             format(section, page))
            self.logger.warn(e)
        return None

    def get_sections(self, page):
        """
        Takes an api session and a page title and returns the sections on a
        page
        """
        self.logger.info("Fetching sections of {}".format(page))
        try:
            sections = self.session.get(action='parse', page=page,
                                        prop='sections')
            return sections['parse']['sections']
        except IOError as e:
            self.logger.warn("Failed to fetch sections for {}".format(page))
            self.logger.warn(e)
            raise IOError

    def get_wikiprojects_from_table(self, wikitext):
        """
        Takes a WikiProjects table listing, and returns individual WikiProjects
        """
        wp = {}
        matches = re.findall(wp_section_regex, wikitext)
        for match in matches:
            remaining = match[3]
            listed_in = re.search(wp_section_regex_listed, remaining)
            # Listed somewhere else, so skip
            if listed_in:
                continue
            wp[match[1]] = {'name': match[0], 'shortname': match[1], 'active':
                            match[2]}
        return wp
