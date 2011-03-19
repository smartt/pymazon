__author__ = "Erik Smartt"
__copyright__ = "Copyright 2011, Erik Smartt"
__license__ = "MIT"
__version__ = "0.2.2"
__usage__ = """Normal usage:
  ./booksearch.py --awskey=YOUR-AWS-KEY --awssec=YOUR-AWS-SECRET --term=SEARCH-TERM

  Options:
    --awskey       Your AWSAccessKeyId.  (*required)
    --awssec       Your AWSSecretKey.  (*required)
    --awstag       Your AssociateTag.
    --term         The search term to use.
    --help         Prints this Help message.
    --verbose      Output extra information about the query to help with debugging.
    --vv           Very Verbose. Ex., outputs the XML responses
    --version      Print the version number of booksearch being used.
"""

import urllib

import base64
import hashlib
import hmac
import time

from BeautifulSoup import BeautifulStoneSoup

class BookSearch(object):
    def __init__(self, AWSAccessKeyId, AssociateTag=None, AWSSecretKey=''):
        """
        @param  AWSAccessKeyId  The Amazon Web Services Access Key that you intend to use for this connection.
        """
        self.AWSAccessKeyId = AWSAccessKeyId
        self.AssociateTag = AssociateTag
        self.AWSSecretKey = AWSSecretKey # Required by the new API rules!
        self.query_string = None
        self.is_valid = None
        self.error_message = None
        self.verbose = False
        self.very_verbose = False

    def _get_signed_url(self, accessKey, secretKey, params):
        #Step 0: add accessKey, Service, Timestamp, and Version to params
        params['AWSAccessKeyId'] = accessKey
        params['Service'] = 'AWSECommerceService'

        #Amazon adds hundredths of a second to the timestamp (always .000), so we do too.
        #(see http://associates-amazon.s3.amazonaws.com/signed-requests/helper/index.html)
        params['Timestamp'] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        params['Version'] = '2009-03-31'

        #Step 1a: sort params
        paramsList = params.items()
        paramsList.sort()

        #Step 1b-d: create canonicalizedQueryString
        # This code comes from http://blog.umlungu.co.uk/blog/2009/jul/12/pyaws-adding-request-authentication/
        # and the resulting discussion
        canonicalizedQueryString = '&'.join(['%s=%s' % (k, urllib.quote(str(v))) for (k, v) in paramsList if v])

        #Step 2: create string to sign
        host = 'ecs.amazonaws.com'
        requestUri = '/onca/xml'
        stringToSign = 'GET\n'
        stringToSign += host + '\n'
        stringToSign += requestUri + '\n'
        stringToSign += canonicalizedQueryString.encode('utf-8')

        #Step 3: create HMAC
        digest = hmac.new(secretKey, stringToSign, hashlib.sha256).digest()

        #Step 4: base64 the hmac
        sig = base64.b64encode(digest)

        #Step 5: append signature to query
        url = 'http://' + host + requestUri + '?'
        url += canonicalizedQueryString + "&Signature=" + urllib.quote(sig)

        return url

    def _build_url(self, dict):
        query_dict = {}

        if self.AssociateTag:
            query_dict['AssociateTag'] = self.AssociateTag

        try:
            query_dict['Operation'] = dict['Operation']
        except KeyError:
            pass

        try:
            query_dict['SearchIndex'] = dict['SearchIndex']
        except KeyError:
            pass

        try:
            query_dict['Keywords'] = dict['keyword']
        except KeyError:
            pass

        try:
            query_dict['IdType'] = dict['IdType']
        except KeyError:
            pass

        try:
            query_dict['ItemId'] = dict['ItemId']
        except KeyError:
            pass

        try:
            query_dict['ResponseGroup'] = dict['ResponseGroup']
        except KeyError:
            pass

        self.query_url = self._get_signed_url(self.AWSAccessKeyId, self.AWSSecretKey, query_dict)

        return self.query_url

    def fetch_response(self, url):
        connection = urllib.urlopen(url)
        raw_xml = connection.read()
        connection.close()

        soup = BeautifulStoneSoup(markup=raw_xml)

        return soup.prettify()

    def search(self, query_url=None):
        """
        Execute the currently-setup search.
        """
        if query_url is not None:
            self.query_url = query_url

        if self.verbose:
            print("BookSearch::search(): query_url: {url}".format(url=self.query_url))

        if not self.query_url:
            return

        self.is_valid = False

        server_response_xml = self.fetch_response(self.query_url)

        if self.very_verbose:
            print("BookSearch::search(): server_response_xml:")
            print("### START ####")
            print("{xml}".format(xml=server_response_xml))
            print("### END ####")

        return self.parse_amazon_xml(amazon_xml=server_response_xml)

    def parse_amazon_xml(self, amazon_xml=None):
        #
        # Check for a valid response:
        #
        # <ItemSearchResponse>
        #  ...
        #  <Items>
        #  <Request>
        #    <IsValid>True</IsValid>
        #
        # Error messages are found like this:
        #
        # <ItemSearchResponse>
        #  ...
        #  <Items>
        #  <Request>
        #      <IsValid>False</IsValid>
        #      ...
        #      <Error>
        #        <Code>AWS.MissingParameters</Code>
        #        <Message>Your request is missing required parameters. Required parameters include ItemId.</Message>
        #      </Error>
        #
        self.search_results = []

        soup = BeautifulStoneSoup(markup=amazon_xml)

        try:
            is_valid_contents = str(soup.find("isvalid").contents[0]).strip()
            self.is_valid = (is_valid_contents == u'True')
        except AttributeError, e:
            self.is_valid = False

        try:
            self.error_message = soup.find("error").message[0].strip()
        except:
            self.error_message = None

        try:
            self.total_results = soup.find("totalresults").contents[0].strip()
        except:
            self.total_results = u'0'

        try:
            self.total_pages = soup.find("totalpages").contents[0].strip()
        except:
            self.total_pages = u'0'

        # Loop over the results
        for item in soup.findAll("item"):
            result = {}

            try:
                result['asin'] = item.asin.contents[0].strip()
            except:
                result['asin'] = None

            try:
                result['amazon_detail_url'] = item.detailpageurl.contents[0].strip()
            except:
                result['amazon_detail_url'] = None

            try:
                result['author'] = item.itemattributes.author.contents[0].strip()
            except:
                result['author'] = None

            try:
                result['binding'] = item.itemattributes.binding.contents[0].strip()
            except:
                result['binding'] = None

            try:
                result['dewey'] = item.itemattributes.deweydecimalnumber.contents[0].strip()
            except:
                result['dewey'] = None

            try:
                result['ean'] = item.itemattributes.ean.contents[0].strip()
            except:
                result['ean'] = None

            try:
                result['edition'] = item.itemattributes.edition.contents[0].strip()
            except:
                result['edition'] = None

            try:
                result['isbn'] = item.itemattributes.isbn.contents[0].strip()
            except:
                result['isbn'] = None

            try:
                result['manufacturer'] = item.itemattributes.manufacturer.contents[0].strip()
            except:
                result['manufacturer'] = None

            try:
                result['title'] = item.itemattributes.title.contents[0].strip()
            except:
                result['title'] = None

            try:
                result['product_group'] = item.itemattributes.productgroup.contents[0].strip()
            except:
                result['product_group'] = None

            try:
                result['publisher'] = item.itemattributes.publisher.contents[0].strip()
            except:
                result['publisher'] = None

            try:
                result['formatted_price'] = item.itemattributes.formattedprice.contents[0].strip()
            except:
                result['formatted_price'] = None

            try:
                result['number_of_pages'] = item.itemattributes.numberofpages.contents[0].strip()
            except:
                result['number_of_pages'] = None

            try:
                result['amazon_sm_img_url'] = item.smallimage.url.contents[0].strip()
            except:
                result['amazon_sm_img_url'] = None

            try:
                result['amazon_md_img_url'] = item.mediumimage.url.contents[0].strip()
            except:
                result['amazon_md_img_url'] = None

            try:
                result['amazon_lg_img_url'] = item.largeimage.url.contents[0].strip()
            except:
                result['amazon_lg_img_url'] = None

            self.search_results.append(result)

        return self.search_results

    def setup_book_search(self, keyword):
        # Save the keyword
        self.query_string = keyword

        # Build the search request URL
        self._build_url({
            'Operation': 'ItemSearch',
            'keyword': keyword,
            'SearchIndex': 'Books',
            'ResponseGroup': 'ItemAttributes,Images,EditorialReview',
        })

        return self.query_url

    def setup_detail_search(self, asin=None, isbn=None):
        """
        Lookup book detail by ASIN.
        """
        # Response types I'm not using currently:
        # Reviews
        # Subjects
        # OfferSummary

        d = {
            'Operation': 'ItemLookup',
            'ResponseGroup': 'ItemAttributes,Images,EditorialReview',
        }

        if asin:
            d['IdType'] = 'ASIN'
            d['ItemId'] = asin

            self.query_string = "ASIN:%s" % asin

        elif isbn:
            d['IdType'] = 'ISBN'
            d['ItemId'] = isbn
            d['SearchIndex'] = 'Books'

            self.query_string = "ISBN:%s" % isbn

        self._build_url(d)

        return self.query_url

    def setup_similar_items_search(self, asin=None, isbn=None):
        """
        Lookup similar books by ASIN.
        """
        d = {
            'Operation': 'SimilarityLookup',
            }

        if asin:
            d['IdType'] = 'ASIN'
            d['ItemId'] = asin

            self.query_string = "ASIN:%s" % asin

        elif isbn:
            d['IdType'] = 'ISBN'
            d['ItemId'] = isbn

            self.query_string = "ISBN:%s" % isbn

        self._build_url(d)

        return self.query_url


def test(search_term, AWSAccessKeyId, AssociateTag, AWSSecretKey, verbose=True, very_verbose=False):
    if verbose:
        print("test(search_term={term})...".format(term=search_term))

    if AWSAccessKeyId and AWSSecretKey:
        bs = BookSearch(AWSAccessKeyId, AWSSecretKey=AWSSecretKey, AssociateTag=AssociateTag)

        bs.verbose = verbose
        bs.very_verbose = very_verbose

        search_url = bs.setup_book_search(keyword=search_term)
        print("URL: {url}".format(url=search_url))

        results = bs.search(query_url=search_url)

        print("Valid: {bool}".format(bool=bs.is_valid))
        print("Total Results: {count}".format(count=bs.total_results))
        print("Total Pages: {count}".format(count=bs.total_pages))

        if results:
            if verbose:
                for item in results:
                    try:
                        print("{item[isbn]} Title: {item[title]}, by {item[author]}".format(item=item))
                    except KeyError, e:
                        print("KeyError while formatting string: {msg}".format(msg=e))
        else:
            print('ERR: {msg}'.format(msg=bs.error_message))

    else:
        print('ERR: AWSAccessKeyId and AWSSecretKey are required!')

    if verbose:
        print("Done.")


# --------------------------------------------------
#               MAIN
# --------------------------------------------------
if __name__ == "__main__":
    import sys
    import getopt

    try:
        opts, args = getopt.getopt(sys.argv[1:], ":",
                                   ["term=", "awskey=", "awssec=", "awstag=", "test", "verbose", "help", "version",
                                    "vv"])
    except getopt.GetoptError, err:
        print("{msg}".format(msg=str(err)))
        sys.exit(2)

    awskey = None
    awstag = None
    awssec = None
    search_term = 'Python'
    run_tests = False
    run_verbose = False
    run_very_verbose = False

    for o, a in opts:
        if o in ["--awskey"]:
            awskey = a

        if o in ["--awstag"]:
            awstag = a

        if o in ["--awssec"]:
            awssec = a

        if o in ["--term"]:
            search_term = a

        if o in ["--verbose"]:
            run_verbose = True

        if o in ["--vv"]:
            run_verbose = True
            run_very_verbose = True

        if o in ["--test"]:
            run_tests = True

        if o in ["--help"]:
            print(__usage__)
            sys.exit(2)

        if o in ["--version"]:
            print(__version__)
            sys.exit(2)

    if run_tests:
        import doctest

        print("Testing...")
        doctest.testmod()
        print("Done.")
        sys.exit(2)

    if awskey and awssec:
        test(search_term=search_term, AWSAccessKeyId=awskey, AssociateTag=awstag, AWSSecretKey=awssec,
             verbose=run_verbose, very_verbose=run_very_verbose)
    else:
        print(__usage__)

    sys.exit(2)

