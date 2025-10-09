pydailystrips
=============

ABOUT
-----

This is a simple little script whose primary purpose is to aggregate various
webcomics onto a single page, for ease of browsing.  It's intended to be
run via cron on a daily basis.  Given a strip definition file, it will
grab a page from the web and find the comic URLs using regex, in defiance
of all common wisdom about parsing HTML using regex.

pydailystrips is written in Python and only tested on Python 3.4+.  I've
coded this without a safety net (ie: there are no unit tests).  It's meant
as a personal replacement for an ancient Perl-based project called
dailystrips, found here: http://dailystrips.sourceforge.net/

The original Perl project has various features not replicated here, such as
the ability to define strip "classes" which individual strips inherit from,
some different methods of finding comic URLs, and the ability to use some
arbitrary code in the strip definition file itself.  The `strips.def` file
packaged here is also far smaller than that provided by dailystrips, since
I've only included the strips I actually use myself.  (Though in fairness,
I suspect very few of the dailystrips definitions still work, since it was
last updated in 2003.)

pydailystrips *does* have one major feature which dailystrips does not: the
ability to capture more information from the comic's webpage than just the
comic image itself.  The most common thing to look for is "title text" attached
to the comic image, but it also supports pulling down secondary images, such
as the "Votey" image from SMBC Comics.

REQUIREMENTS
------------

In addition to Python 3, pydailystrips requires the following Python modules:
* Jinja2
* Pillow
* requests
* python-dateutil *(technically optional)*

pydailystrips assumes that you're running it on a system which supports symlinks.

USAGE
-----

Complete `--help` output:

    usage: pydailystrips.py [-h] (-s STRIP | -g GROUP | -l) [-d DOWNLOAD_DIR]
                            [--css CSS_FILENAME] [-v] [-c CONFIG] [-u USERAGENT]
                            [--ca-certs CA_CERTS] [--date DATE]

    optional arguments:
      -h, --help            show this help message and exit
      -s STRIP, --strip STRIP
                            Strip to process (default: None)
      -g GROUP, --group GROUP
                            Group to process (default: None)
      -l, --list            List available strips/groups (default: False)
      -d DOWNLOAD_DIR, --download DOWNLOAD_DIR
                            Download the specified strips into this directory,
                            rather than showing on STDOUT (default: None)
      --css CSS_FILENAME    Use the specified CSS filename in generated HTML (only
                            has an effect with --download). Will copy the CSS file
                            from this directory to the project directory if it
                            doesn't already exist, but will NOT overwrite an
                            existing CSS file. (default: dailystrips-style.css)
      -v, --verbose         Verbose output (for debugging purposes) (default:
                            False)
      -c CONFIG, --config CONFIG
                            Configuration file (default: ./strips.def)
      -u USERAGENT, --useragent USERAGENT
                            User-Agent to use in HTTP headers when requesting
                            pages (default: Mozilla/5.0 (X11; Linux x86_64;
                            rv:51.0) Gecko/20100101 Firefox/51.0)
      --ca-certs CA_CERTS   Use the specified CA bundle instead of python-
                            requests' own bundle (default: None)
      --date DATE           Use the specified date as the base for saved strip
                            filenames, "index" HTML filenames, and for strips
                            whose search page includes date information. By
                            default, pydailystrips will use today's date. Dates
                            will be parsed using the dateutil library (default:
                            None)

    One of -s, -g, or -l is required.

To get a list of all supported strips and groups, use `-l` or `--list`
*(output truncated here)*:

    $ ./pydailystrips.py -l
    achewood: Achewood
            Artist: Chris Onstad
            Homepage: http://www.achewood.com
            Search Page: http://www.achewood.com
            Base URL: http://www.achewood.com
            Main Strip pattern (Image): (?P<result>/comic.php\?date=\d+)"
            Title Text pattern (Text): <img src.*title="(?P<result>.*?)"

    ...

    Group cj:
     * achewood - Achewood
     * alicegrove - Alice Grove
     * basicinstructions - Basic Instructions
     ...

To retreive all the information for a strip or group of strips, specify them
as an option - you'll get the results of the regex searches at the bottom:

    $ ./pydailystrips.py -s smbc
    smbc: SMBC Comics
            Artist: Zach Weinersmith
            Homepage: http://www.smbc-comics.com/
            Search Page: http://www.smbc-comics.com/
            Base URL: http://www.smbc-comics.com/
            Main Strip pattern (Image): (?P<result>comics/[0-9-]+( \(\d+\))?\.(gif|jpg|png))"
            Title Text pattern (Text): img title="(?P<result>.*?)"
            Votey pattern (Image): (?P<result>comics/[0-9-]+( \(\d+\))?after\.(gif|jpg|png))'
            ------
            Main Strip: http://www.smbc-comics.com/comics/1487000736-20170213.png
            Title Text: I really can&#39;t tell if this one will get hatemail or lovemail.
            Votey: http://www.smbc-comics.com/comics/1487000752-20170213after.png

To download all specified scripts into a directory (which also creates an
HTML page inlining all the strips, and symlinks `index.html` to the new
page), specify `-d` or `--download`:

    $ ./pydailystrips.py -g cj -d /var/www/htdocs/dailystrips

When saving strips to disk, the current date is used as part of the filename, and as
part of the filename of the main "index" file.  Additionally, some strips might include
the date in the URL to retrieve the strip.  To use a specific date instead of today's
date, for those cases, you can use the `--date` argument.  If the `python-dateutil`
library is available, that will be used to parse the date, which will allow many
different ways of specifying the date:

    $ ./pydailystrips.py -s garfield --date 'june 21, 2025'

If `python-dateutil` is *not* available, then the date format may only be specified
in the form `YYYY-MM-DD`:

    $ ./pydailystrips.py -s garfield --date '2025-05-21'

Note that the vast majority of strips in the default set do *not* use dates in their
search URLs, so even if you specify a date in the past, most strips will still always
return the most recent strip.  (The only strip at time of writing which takes advantage
of dates in its URLs is Garfield.)

CSS Styling
-----------

The HTML output of pydailystrips sets CSS IDs and classnames on basically all
attributes, and it should be possible to style the page however you like.  By default
it will copy the file `dailystrips-style.css` into the output directory, if it doesn't
already exist, and use that for CSS.  You can specify any arbitrary filename (or URL)
for the `--css` option and the outputted HTML will use that, instead.  The CSS you use
need not be present in the same directory as `pydailystrips.py` itself.  pydailystrips
will *not* overwrite CSS in the destination directory, so the CSS file in the download
directory can be modified without fear of having it overwritten.

A quick perusal of the generated HTML source and/or the bundled CSS file should give
you an idea of what elements are available.  I believe I've got just about everything
you'd care about in there, but let me know if I've missed anything that would be useful.
For instance, the main strip image will have a CSS ID of `strip-img-<stripname>-main_strip`,
and classes of `strip-img`, `strip-img-<stripname>`, and `strip-img-main_strip`.

CA Certificates
---------------

By default, pydailystrips will use the CA bundle which comes with Python's "requests"
module.  In the event that you need to talk to a server whose SSL issuer is not found,
you can use the `--ca-certs` option to specify your own CA bundle to use.  As of
June 15, 2019, this seems to be required to talk to www.comicskingdom.com (which hosts
Zits), which is currently signed by `Go Daddy Secure Certificate Authority - G2`.

TODO
----

* Some kind of "archive" page would be nice - dailystrips had been linking to
  one which doesn't seem to have ever been updated...
* Move "groups" definitions to their own file
* Proper pypi-compatible packaging/versioning would be nice, wouldn't it?

CHANGELOG
---------

*(Note: I've never kept an actual changelog for this, but with some added functionality
in June 2025, it seemed like well past the time to do so.)*

**October 9, 2025**
 - **Functional Changes**:
   - Updated default Useragent to something more recent
 - **Strip Definition Updates:**
   - Removed Calvin and Hobbes for now.  gocomics.com has introduced a WAF product which
     wil probably be effective in blocking casual scrapers like this one, and I don't
     feel like trying to figure out workarounds.

**June 22, 2025**
 - **Functional Changes**:
   - Added support for strips whose URLs contain dates, courtesy Lars Kotthoff (PR #3)
   - Added support for specifying which date to use in those URLs with the `--date` arg
   - Added optional `python-dateutil` dependency for parsing dates specified in `--date`
 - **Strip Definition Updates:**
   - Added Garfield, courtesy Lars Kotthoff (PR #3)
   - Fixed Calvin and Hobbes, which had been returning the same strip for some time now
   - Fixed Poorly Drawn Lines

