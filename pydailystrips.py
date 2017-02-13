#!/home/pez/virtualenv/dailystrips/bin/python
# vim: set expandtab tabstop=4 shiftwidth=4:

import os
import re
import io
import sys
import jinja2
import datetime
import argparse
import requests
import http.client

from PIL import Image

class Pattern(object):
    """
    A pattern that we'll be retreiving from the HTML page.  Can
    be either an image (such as the main strip itself) or text
    (generally title text attached to the image).  If given a
    baseurl, and if the mode is M_IMG, the full result will have
    the baseurl prepended.  baseurl defaults to '' and must be
    set manually after object creation, generally through 
    Strip.finish().
    """

    M_IMG = 1
    M_TEXT = 2

    MODE_TXT = {
        1: 'Image',
        2: 'Text',
    }

    IMG_TO_EXT = {
        'PNG': 'png',
        'JPEG': 'jpg',
        'GIF': 'gif',
    }

    def __init__(self, title, pattern, mode=1):
        self.title = title
        self.pattern = pattern
        self.mode = mode
        self.baseurl = ''
        self.result = None
        self.error = None
        self.filename = None

    def search_page(self, pagedata, verbose=False):
        """
        Given pagedata (a list of strings), matches its contents
        using group 1 of our regex pattern.  We don't actually
        compile the regex until now, so that we don't accidentally
        waste time compiling on patterns we never attempt.  Returns
        True if we matched, and False otherwise.
        """
        if verbose:
            print('* Searching for "%s" pattern: %s' % (self.title, self.pattern))
        search_re = re.compile(self.pattern)
        for line in pagedata:
            match = search_re.search(line)
            if match:
                self.result = match.group(1)
                return True
        self.error = 'Could not find "%s" pattern in HTML' % (self.title)
        return False

    def get_result(self):
        """
        Returns our result, or None
        """
        if self.result is None:
            return None
        else:
            if self.mode == Pattern.M_IMG:
                return '%s%s' % (self.baseurl, self.result)
            else:
                return self.result

    def get_error(self):
        """
        Returns our error (or None)
        """
        return '[%s]' % (self.error)

    def download_to(self, basedir, linkdir, now, referer=None, verbose=False, useragent=None):
        """
        Downloads ourself to the given directory.
        """

        # Only download if we're an image
        if self.mode != Pattern.M_IMG:
            return

        # Also only download if we actually matched
        if self.error or not self.result:
            return

        # Set up our headers
        headers = {}
        if referer:
            headers['Referer'] = referer
        if useragent:
            headers['User-Agent'] = useragent

        # Grab the image
        try:
            if verbose:
                print(' * Fetching "%s" image at URL: %s' % (self.title, self.get_result()))
            resp = requests.get(self.get_result(), headers=headers)
            if resp.status_code == 200:
                new_image_data = resp.content
            else:
                self.error = 'ERROR: Received HTTP %d: %s' % (resp.status_code, resp.reason)
                if verbose:
                    print(self.error)
                    print('')
                return
        except Exception as e:
            self.error = 'ERROR: Unable to retreive "%s" image: %s' % (self.title, e)
            if verbose:
                print(self.error)
                print('')
            return

        # Load it into PIL to determine its file type (we can't trust extensions, and
        # some of our strips don't even have extensions on the file)
        try:
            im = Image.open(io.BytesIO(new_image_data))
            if im.format in Pattern.IMG_TO_EXT:
                ext = Pattern.IMG_TO_EXT[im.format]
            else:
                ext = im.format.lower()
        except Exception as e:
            self.error = 'ERROR: Unable to determine "%s" image type: %s' % (self.title, e)
            if verbose:
                print(self.error)
                print('')
            return

        # Normalize our title to something a filename can use
        image_suffix = re.sub('[^0-9a-z]', '_', self.title.lower())

        # Grab yesterday's date so we can check to see if that file exists, and if it's
        # the same file.
        yesterday = now - datetime.timedelta(days=1)

        # Format our base filenames
        img_filename_base = '%04d-%02d-%02d-%s.%s' % (now.year, now.month, now.day,
            image_suffix, ext)
        img_filename = os.path.join(basedir, img_filename_base)
        last_filename_base = '%04d-%02d-%02d-%s.%s' % (yesterday.year,
            yesterday.month, yesterday.day, image_suffix, ext)
        last_filename = os.path.join(basedir, last_filename_base)

        # Big ol' block here, various OS interactions.  Just try/except the whole thing.
        try:
            # Check for yesterday's file.
            write_file = True
            if os.path.exists(last_filename):
                if verbose:
                    print('    Previous file exists, checking contents.')
                with open(last_filename, 'rb') as df:
                    old_image_data = df.read()

                # Here's the comparison
                if old_image_data == new_image_data:
                    write_file = False
                    if verbose:
                        print('    Previous strip is the same, just symlinking')
                    if os.path.islink(last_filename):
                        # We *could*, if we were sufficiently motivated, ensure that
                        # we follow a potential symlink chain all the way back to a
                        # real file and then symlink to that.  Turns out I don't actually
                        # care enough to do that, for two reasons:
                        #   1) That'll never actually happen without manual intervention
                        #   2) Even if it did, there's no way we'd reach the kernel's
                        #      symlink chain limit since we're by definition chopping off
                        #      one level anyway.
                        real_file = os.readlink(last_filename)
                        os.symlink(real_file, img_filename)
                    else:
                        os.symlink(last_filename_base, img_filename)

            if write_file:
                # Write out our new file
                with open(img_filename, 'wb') as df:
                    df.write(new_image_data)
                if verbose:
                    print('    Saved at %s' % (img_filename))

            # Store our filename for later retrieval
            self.filename = os.path.join(linkdir, img_filename_base)

        except Exception as e:

            self.error = 'ERROR: Unable to save %s image: %s' % (self.title, e)
            if verbose:
                print(self.error)
                print('')
            return

class Strip(object):
    """
    Information about the strip itself
    """

    def __init__(self, strip_id, name=None, artist=None,
            homepage=None, searchpage=None,
            searchpattern=None, baseurl=''):
        self.strip_id = strip_id
        self.name = name
        self.artist = artist
        self.homepage = homepage
        if searchpage:
            self.searchpage = searchpage
        else:
            self.searchpage = homepage
        self.patterns = []
        self.patterns.append(Pattern(title='Main Strip',
            pattern=searchpattern, mode=Pattern.M_IMG))
        self.baseurl = baseurl
        self.error = None
        self.fetch_attempted = False

    def set_homepage(self, homepage):
        """
        Sets our homepage.  Will also set searchpage if that's not been defined
        yet.
        """
        self.homepage = homepage
        if self.searchpage is None:
            self.searchpage = homepage

    def set_searchpattern(self, searchpattern):
        """
        Sets our main comic search pattern.
        """
        self.patterns[0].pattern = searchpattern

    def add_extra(self, title, pattern, mode):
        """
        Adds a new "extra" pattern to match
        """
        pattern = Pattern(title=title, pattern=pattern, mode=mode)
        self.patterns.append(pattern)

    def finish(self):
        """
        Process any changes which need to be made once we're through loading
        our config file
        """

        # Special case for baseurl of "$homepage"
        if self.baseurl == '$homepage':
            self.baseurl = self.homepage

        # Set baseurl on all our Pattern objects
        for pattern in self.patterns:
            pattern.baseurl = self.baseurl

    def fetch_html(self, verbose=False, useragent=None):
        """
        Fetches the searchpage and populates our result URLs
        """

        self.fetch_attempted = True
        headers = {}
        if useragent:
            headers['User-Agent'] = useragent

        if verbose:
            print('------')
            print('Fetching HTML page for %s (%s)' % (self.name, self.strip_id))
            print('URL is: %s' % (self.searchpage))
        try:
            page_lines = requests.get(self.searchpage, headers=headers).text.splitlines()
        except Exception as e:
            self.error = 'ERROR: Unable to retrieve HTML for %s (%s) - %s: %s' % (
                self.name, self.strip_id, self.searchpage, e)
            if verbose:
                print(self.error)
                print('')
            return
        if verbose:
            print('HTML successfully retrieved, starting on matches')

        # Run our matches
        for pattern in self.patterns:
            if pattern.search_page(page_lines, verbose):
                if verbose:
                    print('    Found result: %s' % (pattern.result))
                    if pattern.mode == Pattern.M_IMG:
                        print('    Full result URL: %s' % (pattern.get_result()))
            else:
                print('ERROR: %s (%s): %s' % (self.name, self.strip_id,
                    pattern.get_error()))
                if verbose:
                    print('')

        # A bit of space inbetween strips
        if verbose:
            print('')

    def download(self, basedir, now, verbose=False, useragent=None):
        """
        Downloads the strip (and all extras) into the given `basedir`.
        """

        # First make sure our base directory exists
        real_basedir = os.path.join(basedir, self.name)
        if not os.path.exists(real_basedir):
            if verbose:
                print('Creating directory: %s' % (real_basedir))
            os.mkdir(real_basedir)

        # Now loop through all our patterns
        for pattern in self.patterns:
            pattern.download_to(real_basedir, self.name, now,
                referer=self.searchpage,
                verbose=verbose,
                useragent=useragent)

    def valid(self):
        """
        Returns True if we have all necessary information to be a valid strip,
        and False otherwise.
        """
        if (self.name is None or self.homepage is None or
                self.patterns[0].pattern is None):
            return False
        else:
            return True

    def invalid_reason(self):
        """
        Returns a string detailing why the strip is invalid, if it's not.
        """
        if self.valid():
            return ''
        else:
            if self.name is None:
                return 'No name defined'
            elif self.homepage is None:
                return 'No homepage defined'
            elif self.patterns[0].pattern is None:
                return 'No searchpattern defined'
            else:
                return 'Unknown error'

    def print_strip_info(self):
        """
        Prints out our strip information
        """
        print('%s: %s' % (self.strip_id, self.name))
        if self.artist is not None:
            print("\tArtist: %s" % (self.artist))
        print("\tHomepage: %s" % (self.homepage))
        print("\tSearch Page: %s" % (self.searchpage))
        print("\tBase URL: %s" % (self.baseurl))
        for pattern in self.patterns:
            print("\t%s pattern (%s): %s" % (pattern.title, Pattern.MODE_TXT[pattern.mode],
                pattern.pattern))
        if self.fetch_attempted:
            print("\t------")
            if self.error is None:
                for pattern in self.patterns:
                    if pattern.result is not None:
                        print("\t%s: %s" % (pattern.title, pattern.get_result()))
                    else:
                        print("\t%s: %s" % (pattern.title, pattern.get_error()))
            else:
                print("\tError: %s" % (self.error))
        print('')

class Group(object):
    """
    A group of strips to retrieve at once.
    """

    def __init__(self, group_id):
        self.group_id = group_id
        self.strip_ids = []
        self.strips = []

    def add_strip(self, strip_id):
        """
        Adds a new strip ID to this group
        """
        self.strip_ids.append(strip_id)

    def finish(self, collection):
        """
        Given a collection of strips, populate our `strips` array with
        the actual objects, rather than just strip IDs
        """
        for strip_id in self.strip_ids:
            try:
                strip = collection.get_strip(strip_id)
                self.strips.append(strip)
            except KeyError as e:
                raise Exception('Group "%s" - strip "%s" is unknown' % (self.group_id, strip_id))

    def print_group_info(self):
        """
        Prints out our group information
        """
        print('Group %s:' % (self.group_id))
        for strip in self.strips:
            print(' * %s - %s' % (strip.strip_id, strip.name))
        print('')

    def __len__(self):
        return len(self.strip_ids)

class Collection(object):
    """
    Our complete collection of strips
    """

    def __init__(self, args):
        """
        Constructor.  This is a bit lazy, but 'args' should be the parsed
        arguments from ConfigParser, or at least something which defines
        `verbose`, `useragent`, `basedir`, and `config` options.
        """
        self.verbose = args.verbose
        self.useragent = args.useragent
        self.basedir = args.basedir
        self.strips = {}
        self.groups = {}
        self.now = datetime.date.today()
        self.load_from_filename(args.config)

        # Load in our Jinja2 template
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))
        self.template_main = env.get_template('dailystrips-main.html')

    def load_error(self, filename, idx, line, error):
        """
        Displays an error enountered while processing config file
        """
        if line is None:
            raise Exception('%s: line %d: %s' % (filename, idx, error))
        else:
            raise Exception('%s: line %d: %s - Full line: %s' % (
                filename, idx, error, line))

    def load_from_filename(self, filename):
        """
        Loads ourselves from a file
        """
        if self.verbose:
            print('Opening config filename "%s"' % (filename))
        with open(filename, 'r') as df:
            cur_strip = None
            cur_group = None
            for (idx, line) in enumerate(df.readlines()):
                idx += 1
                line = line.lstrip().rstrip("\r\n")
                if line == '':
                    continue
                if line[0] == '#':
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) == 0:
                    continue
                if cur_strip is None and cur_group is None:
                    if parts[0] == 'strip':
                        if len(parts) == 2:
                            strip_id = parts[1].rstrip().lower()
                            if strip_id in self.strips:
                                self.load_error(filename, idx, line, 'Duplicate strip "%s" found' % (strip_id))
                            cur_strip = Strip(strip_id)
                        else:
                            self.load_error(filename, idx, line, 'Found "strip" without ID')
                    elif parts[0] == 'group':
                        if len(parts) == 2:
                            group_id = parts[1].rstrip().lower()
                            if group_id in self.groups:
                                self.load_error(filename, idx, line, 'Duplicate group "%s" found' % (group_id))
                            cur_group = Group(group_id)
                        else:
                            self.load_error(filename, idx, line, 'Found "group" without ID')
                    else:
                        self.load_error(filename, idx, line, 'Expecting "strip" or "group"')
                elif cur_strip is not None:
                    if parts[0] == 'end':
                        if cur_strip.valid():
                            cur_strip.finish()
                            self.strips[cur_strip.strip_id] = cur_strip
                            if self.verbose:
                                print('Parsed strip "%s (%s)"' % (cur_strip.name, cur_strip.strip_id))
                            cur_strip = None
                        else:
                            self.load_error(filename, idx, None, 'Invalid strip "%s": %s' % (
                                cur_strip.strip_id, 
                                cur_strip.invalid_reason()))
                    else:
                        if len(parts) == 1:
                            self.load_error(filename, idx, line, 'Missing option data')
                        else:
                            if parts[0] == 'name':
                                cur_strip.name = parts[1].rstrip()
                            elif parts[0] == 'artist':
                                cur_strip.artist = parts[1].rstrip()
                            elif parts[0] == 'homepage':
                                cur_strip.set_homepage(parts[1].rstrip())
                            elif parts[0] == 'searchpage':
                                cur_strip.searchpage = parts[1].rstrip()
                            elif parts[0] == 'searchpattern':
                                cur_strip.set_searchpattern(parts[1])
                            elif parts[0] == 'baseurl':
                                cur_strip.baseurl = parts[1].rstrip()
                            elif parts[0] == 'extra_txt' or parts[0] == 'extra_img':
                                if parts[0] == 'extra_txt':
                                    mode = Pattern.M_TEXT
                                else:
                                    mode = Pattern.M_IMG
                                extra_parts = parts[1].split('|', maxsplit=1)
                                if len(extra_parts) != 2:
                                    self.load_error(filename, idx, line, 'Incomplete extra_txt stanza')
                                cur_strip.add_extra(extra_parts[0], extra_parts[1], mode)
                            else:
                                self.load_error(filename, idx, line, 'Unknown option "%s"' % (parts[0]))
                elif cur_group is not None:
                    if len(parts) > 1:
                        self.load_error(filename, idx, line, 'Unknown group line')
                    if parts[0] == 'end':
                        self.groups[cur_group.group_id] = cur_group
                        if self.verbose:
                            print('Parsed group "%s": %d strips' % (cur_group.group_id, len(cur_group)))
                        cur_group = None
                    else:
                        cur_group.add_strip(parts[0].rstrip().lower())
                else:
                    self.load_error(filename, idx, line, 'Something went super wrong, how are we here?')

        # Make sure our last strip was closed properly
        if cur_strip is not None:
            self.load_error(filename, idx, None, 'Strip "%s" was never closed' % (cur_strip.strip_id))
        if cur_group is not None:
            self.load_error(filename, idx, None, 'Group "%s" was never closed' % (cur_group.group_id))

        # Finish our groups
        if self.verbose:
            print('Validating group definitions')
        for group in self.groups.values():
            group.finish(self)

        if self.verbose:
            print('Finished parsing config file')

    def get_strip(self, strip_id):
        """
        Get the given script.  Raises KeyError if it's not found.
        """
        return self.strips[strip_id]

    def list_strips(self):
        """
        Print out a list of all the strips we have.
        """
        for strip_id in sorted(self.strips.keys()):
            self.strips[strip_id].print_strip_info()

    def list_groups(self):
        """
        Print out a list of all the groups we have.
        """
        for group_id in sorted(self.groups.keys()):
            self.groups[group_id].print_group_info()

    def list_all(self):
        """
        Outputs both our strips and groups.
        """
        self.list_strips()
        self.list_groups()

    def process_strips(self, strips, download=False):
        """
        Fetches and prints the strips
        """
        for strip in strips:
            strip.fetch_html(verbose=self.verbose, useragent=self.useragent)
            if download:
                if not strip.error:
                    strip.download(verbose=self.verbose, useragent=self.useragent,
                        basedir=self.basedir, now=self.now)
            else:
                strip.print_strip_info()

        # Finally, if we've been told to download, generate our HTML
        if download:
            cur_filename = 'dailystrips-%04d.%02d.%02d.html' % (self.now.year, self.now.month, self.now.day)
            yesterday = self.now - datetime.timedelta(days=1)
            prev_filename = 'dailystrips-%04d.%02d.%02d.html' % (yesterday.year, yesterday.month, yesterday.day)
            prev_filename_full = os.path.join(self.basedir, prev_filename)
            if not os.path.exists(prev_filename_full):
                prev_filename = None

            try:
                page_content = self.template_main.render({
                        'humandate': self.now.strftime('%A, %B %d, %Y'),
                        'yesterday': prev_filename,
                        'strips': strips,
                    })
            except Exception as e:
                page_content = 'ERROR: Could not render dailystrips template: %s' % (e)
                if self.verbose:
                    print(page_content)

            # Just let the Exception bubble up here, if we get one.
            # For some reason, if the file already exists, we sometimes get a BlockingIOError
            # when trying to write to it.  To try and avoid that, unlink it first if need
            # be.
            if self.verbose:
                print('Writing current dailystrips index to: %s' % (cur_filename))
            full_filename = os.path.join(self.basedir, cur_filename)
            if os.path.exists(full_filename):
                os.unlink(full_filename)
            with open(full_filename, 'w') as df:
                df.write(page_content)

            # Symlink a new index.html
            index_filename = os.path.join(self.basedir, 'index.html')
            if os.path.exists(index_filename):
                os.unlink(index_filename)
            os.symlink(cur_filename, index_filename)

            # And finally update our previous day's "nextday" tag, if we have a previous day.
            if prev_filename:
                if self.verbose:
                    print('Updating "next day" link in %s' % (prev_filename))
                with open(prev_filename_full, 'r') as df:
                    prev_content = df.read()
                os.unlink(prev_filename_full)
                with open(prev_filename_full, 'w') as df:
                    df.write(prev_content.replace('<!--nextday-->', ' | <a href="%s">Next day</a>' % (cur_filename)))

    def process_strip_id(self, strip_id, download=False):
        """
        Prints the specified strip ID
        """
        if strip_id not in self.strips:
            raise Exception('Strip "%s" is not known' % (strip_id))
        self.process_strips([self.strips[strip_id]], download)

    def process_group_id(self, group_id, download=False):
        """
        Prints the specified group
        """
        if group_id not in self.groups:
            raise Exception('Group "%s" is not known' % (group_id))
        self.process_strips(self.groups[group_id].strips, download)

if __name__ == '__main__':

    # Parse some arguments!

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog='One of -s, -g, or -l is required.',
    )

    stripgroup = parser.add_mutually_exclusive_group(required=True)
    
    stripgroup.add_argument('-s', '--strip',
        type=str,
        help='Strip to process')

    stripgroup.add_argument('-g', '--group',
        type=str,
        help='Group to process')

    stripgroup.add_argument('-l', '--list',
        action='store_true',
        help='List available strips/groups')

    parser.add_argument('-d', '--download',
        action='store_true',
        help='Download the specified strips rather than showing on STDOUT')

    parser.add_argument('-b', '--basedir',
        type=str,
        help='Base directory to use while saving (required if --download specified)')

    parser.add_argument('-v', '--verbose',
        action='store_true',
        help='Verbose output (for debugging purposes)')

    parser.add_argument('-c', '--config',
        type=str,
        default=os.path.join(os.path.dirname(__file__), 'strips.def'),
        help='Configuration file')

    parser.add_argument('-u', '--useragent',
        type=str,
        default='Mozilla/5.0 (X11; Linux x86_64; rv:51.0) Gecko/20100101 Firefox/51.0',
        help='User-Agent to use in HTTP headers when requesting pages')

    args = parser.parse_args()

    if args.download and not args.basedir:
        parser.error('--basedir is required when --download is specified')

    if not os.path.exists(args.config):
        parser.error('Config file "%s" does not exist' % (args.config))

    if args.download and args.basedir and not os.path.exists(args.basedir):
        parser.error('Base directory "%s" does not exist' % (args.basedir))

    # Now launch the app

    collection = Collection(args)
    if args.list:
        collection.list_all()
    elif args.strip:
        collection.process_strip_id(args.strip, args.download)
    elif args.group:
        collection.process_group_id(args.group, args.download)
