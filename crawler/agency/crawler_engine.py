# Don't remove re package, this package used dynamically in code
import re  # pylint: disable=unused-import
import json
import time
import traceback
import redis
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.common.exceptions import SessionNotCreatedException, TimeoutException
from django.conf import settings
from django.utils import timezone
from celery.utils.log import get_task_logger
from selenium.webdriver.common.by import By

from . import models, utils
from reusable.browser import scroll


logger = get_task_logger(__name__)
redis_news = redis.StrictRedis(host="crawler-redis", port=6379, db=0)
redis_duplicate_checker = redis.StrictRedis(host="crawler-redis", port=6379, db=1)


class CrawlerEngine:
    def __init__(self, page: dict, repetitive: bool = False):
        """Initialize engine for getting data from a page.

        Args:
            page (page): Page object
            repetitive (bool, optional): If true we will get data from the \
                repetitive links in the page. Defaults to False.
        """
        self.before_initialize_driver(repetitive)
        success = self.initialize_driver(page["use_proxy"])
        if not success:
            return
        self.after_initialize_driver(page["id"])

        self.logging(
            f"Crawl **started** for page: {self.page} with repetitive: {self.repetitive}"
        )
        self.run()
        self.logging(
            f"Crawl **finished** for page: {self.page} with repetitive: {self.repetitive}"
        )

    def before_initialize_driver(self, repetitive):
        self.log_messages = ""
        self.fetched_links = []
        self.fetched_links_count = 0
        self.repetitive = repetitive

    def remove_some_images(self, driver):
        # JavaScript to find and remove images
        script = """
        var images = document.getElementsByTagName('img');
        for (var i = 0; i < images.length; i++) {
            images[i].remove();  // Remove the image
        }

        var divs = document.querySelectorAll('div.enamd');
        divs.forEach(function(div) {
            div.remove();
        });
        """

        # Execute the script
        driver.execute_script(script)
        return driver

    def initialize_driver(self, use_proxy: bool) -> bool:
        try:
            self.driver = webdriver.Remote(
                "http://crawler-selenium-hub:4444",
                options=utils.get_browser_options(use_proxy),
            )
        except SessionNotCreatedException:
            # TODO: Custom handling
            self.logging(traceback.format_exc(), "error")
            return False
        except Exception:
            self.logging(traceback.format_exc(), "error")
            return False
        self.driver.header_overrides = utils.DEFAULT_HEADER
        return True

    def after_initialize_driver(self, page_id):
        self.page = models.Page.objects.get(id=page_id)
        self.driver.set_page_load_timeout(self.page.agency.load_timeout)
        self.page.lock = True
        self.page.save()
        self.report = models.Report.objects.create(
            page=self.page, status=models.Report.PENDING
        )

    def register_log(self, desc, error, page, url):
        """Custom registering logs. Logs are stored into the db.

        Args:
            desc (str): extra desc of the error
            error (str): exception
            page (page): which page we have encountered error
            url (url): link of page
        """
        logger.error(
            "url: %s\ndesc: %s\ntraceback:%s", url, desc, traceback.format_exc()
        )
        models.Log.objects.create(
            page=page,
            description=desc,
            url=url,
            phase=models.Log.CRAWLING,
            error=error,
        )

    def land_page(self) -> bool:
        """
        Lands on the page with retry mechanism.
        """
        max_retries = 3
        initial_delay = 60  # seconds
        retry_delay = initial_delay

        for attempt in range(max_retries):
            try:
                self.driver.get(self.page.url)
                self.remove_some_images(self.driver)

                # Wait for page to be fully loaded
                time.sleep(self.page.load_sleep)

                # Check if page is loaded by looking for common elements
                if self.page.structure.news_links_structure:
                    structure = self.page.structure.news_links_structure

                    # First check if we have a tag to find elements
                    tag = structure.get("tag")
                    if tag:
                        elements = self.driver.find_elements(By.TAG_NAME, tag)
                        if elements:
                            return True

                    # If no tag or no elements found, check if there's custom code
                    if "code" in structure:
                        # If there's custom code, we assume the page structure is handled there
                        return True

                    # If no tag and no code, log a warning
                    self.logging(
                        "Warning: No tag or code found in news_links_structure. "
                        "This may cause issues with link extraction."
                    )

                # As a last resort, check if the page has loaded at all
                # by looking for basic HTML elements
                if self.driver.find_elements(By.TAG_NAME, "body"):
                    return True

                # probably failure to load the page
                return False

            except TimeoutException as error:
                error = (
                    f"Timeout while loading {self.page.url}: {traceback.format_exc()}"
                )
                self.logging(error, "warning")
                return False

        return True

    def taking_picture(self):
        if not self.page.take_picture:
            return
        # in debug mode static_root is none
        file_path = f"{settings.STATIC_ROOT or './static'}/{self.report.id}.png"
        self.driver.get_screenshot_as_file(file_path)
        self.report.picture = file_path
        self.report.save()

    def get_elements(self):
        doc = BeautifulSoup(self.driver.page_source, "html.parser")
        attribute = self.page.structure.news_links_structure
        tag = attribute.pop("tag")
        if "code" in attribute.keys():
            del attribute["code"]
        elements = doc.findAll(tag, attribute)
        self.logging(f"length of elements is: {len(elements)}", "debug")
        return elements

    def do_scroll(self):
        """
        Scroll the page based on the page.scroll value.
        """
        if not self.page.scroll:
            return
        self.logging(f"Scrolling {self.page.scroll} times", "debug")
        scroll(self.driver, self.page.scroll)

    def post_crawling(self, data):
        """
        Post crawling is the function that is called after the links are fetched.
        It is used to store the fetched links in the database and to update the report.
        It is also used to save the fetched links to the redis database.
        It is also used to save the fetched links to the duplicate checker.
        """
        self.fetched_links = data
        self.fetched_links_count = len(data)
        self.report.fetched_links = self.fetched_links_count
        self.report.save()
        self.logging(
            f"Fetched {len(data)} links for {self.page.url}, check them in {self.report.id} report."
        )

    def get_links(self, elements):
        """
        Get links from the page based on the structure.
        """
        data = []
        if self.page.structure.news_links_code != "":
            try:
                exec(self.page.structure.news_links_code)  # pylint: disable=exec-used
            except TimeoutException as e:
                error_trace = traceback.format_exc()
                self.logging(
                    f"Timeout while executing code: {error_trace} \n {self.page.structure.news_links_code}",
                    "warning",
                )
                return []
            except Exception as e:
                error_trace = traceback.format_exc()
                self.register_log(
                    f"Error executing code:\n{self.page.structure.news_links_code}\n{error_trace}",
                    str(e),
                    self.page,
                    self.page.url,
                )
                return []
        else:
            for element in elements:
                data.append({"link": element["href"]})
        return data

    def fetch_links(self):
        """Fetch links from a page.
        this function get links using the specified structure from a page
        """
        success = self.land_page()
        self.logging(f"land page success: {success}", "debug")
        if not success:
            return

        self.do_scroll()

        time.sleep(self.page.links_sleep)
        self.logging(f"sleep for {self.page.links_sleep} success", "debug")

        self.taking_picture()
        elements = self.get_elements()
        self.logging(f"get elements success and length is: {len(elements)}", "debug")
        data = self.get_links(elements)
        self.post_crawling(data)

    def crawl_one_page(self, data, fetch_content):
        """Get data from crawled link based on defined structure.

        Args:
            data (json): data containing the link to crawl.
            fetch_content (bool): whether we should open the link or not.
        """
        meta = self.page.structure.news_meta_structure
        article = data
        article["page_id"] = self.page.id

        doc = None
        if fetch_content:
            # Fetch the content from the URL
            try:
                self.driver.get(data["link"])
                time.sleep(self.page.load_sleep)
                doc = BeautifulSoup(self.driver.page_source, "html.parser")
            except TimeoutException:
                logger.error(f"Timeout while loading {data['link']}", exc_info=True)
                return

            if meta:
                self.extract_meta_data(meta, doc, article, data["link"])

        self.logging(f"crawl_one_page: {article}", "debug")
        self.save_to_redis(article)

    def extract_meta_data(self, meta, doc, article, link):
        """Extract meta data from the document with retry mechanism."""
        max_retries = 2
        retry_delay = 1  # seconds

        for key, attribute in meta.items():
            for attempt in range(max_retries):
                try:
                    attribute_copy = (
                        attribute.copy()
                    )  # Prevent mutation of original attribute
                    tag = attribute_copy.get("tag")
                    if tag is None:
                        raise KeyError(
                            f"Missing 'tag' key in meta structure for field '{key}'"
                        )
                    # Remove 'tag' from attributes dict before using it for element search
                    attrs_for_find = {
                        k: v for k, v in attribute_copy.items() if k != "tag"
                    }

                    if tag == "value":
                        article[key] = attribute_copy.get("value", "")
                        break
                    elif tag == "code":
                        self.execute_code(
                            attribute_copy.get("code"), article, key, link, doc
                        )
                        break

                    element = doc.find(tag, attrs_for_find)
                    if not element:
                        if attempt < max_retries - 1:
                            self.logging(
                                f"Element not found for {key}, retrying in {retry_delay} seconds...",
                                "warning",
                            )
                            time.sleep(retry_delay)
                            # Refresh the page source and try again
                            doc = BeautifulSoup(self.driver.page_source, "html.parser")
                            continue
                        else:
                            self.log_missing_element(tag, attrs_for_find, link)
                            article[key] = ""
                            break

                    code = attribute_copy.get("code")
                    if code:
                        self.execute_code(code, article, key, link, doc)
                    else:
                        article[key] = element.text.strip() if element.text else ""
                    break

                except Exception as e:
                    if attempt < max_retries - 1:
                        self.logging(
                            f"Error extracting {key} on attempt {attempt + 1}, retrying in {retry_delay} seconds...",
                            "error",
                        )
                        time.sleep(retry_delay)
                        # Refresh the page source and try again
                        doc = BeautifulSoup(self.driver.page_source, "html.parser")
                    else:
                        logger.error(f"Error extracting {key} from {link}: {str(e)}")
                        self.register_log(
                            f"Error extracting {key}", str(e), self.page, link
                        )
                        article[key] = ""
                    retry_delay *= 2

    def execute_code(self, code, article, key, link, doc):
        """Safely execute custom code and handle errors."""
        try:
            # Execute the code, making 'article', 'key', and 'doc' available within the code
            exec(code, {"article": article, "key": key, "doc": doc})
        except Exception as e:
            logger.error(
                f"Error executing code:\n{code}\nfor link {link}", exc_info=True
            )
            self.register_log(f"Error in code execution:\n{code}", e, self.page, link)

    def log_missing_element(self, tag, attribute, link):
        """Log when a tag or element is missing from the document."""
        logger.warning(
            f"Element with tag {tag} and attribute {attribute} not found in {link}"
        )
        self.register_log(
            f"Missing element: tag={tag}, attribute={attribute}",
            "element is null",
            self.page,
            link,
        )

    def save_to_redis(self, article):
        """We store each link information as a json into Redis
        We also store link into duplicate checker for avoiding duplicate links

        Args:
            article (json): information about link
        """
        redis_news.set(f'links_{article["link"]}', json.dumps(article))
        redis_duplicate_checker.set(
            article["link"], "", ex=self.page.days_to_keep * 60 * 60 * 24
        )

    def check_data(self):
        """Here we check each link that we crawled in the fetch-links function.
        We call crawl-one-page on each link.
        We only count not-duplicate links.
        """
        counter = self.fetched_links_count
        for data in self.fetched_links:
            if not self.repetitive and redis_duplicate_checker.exists(data["link"]):
                counter -= 1
                continue
            self.crawl_one_page(data, self.page.fetch_content)
        self.page.last_crawl = timezone.localtime()
        self.page.last_crawl_count = self.fetched_links_count
        self.page.last_crawl_new_count = counter
        self.page.lock = False
        self.page.save()
        self.finalize_report(counter)

    def finalize_report(self, counted: int):
        """Finalize the report after crawling the page."""
        self.report.new_links = counted
        self.report.status = models.Report.COMPLETED
        self.report.log = self.log_messages
        self.report.save()

    def logging(self, message, level: str = "info"):
        if level == "info":
            logger.info(message)
        elif level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "debug":
            logger.debug(message)
        self.log_messages += f"{message} \n\n"

    def run(self):
        """Run the crawler engine
        first: we get links from the specified page
        second: we get data from each page
        """
        self.logging(f"---> Fetching links from {self.page} started")
        self.fetch_links()
        self.logging(
            f"---> We've found {self.fetched_links_count} number of links for {self.page}"
        )
        self.check_data()
        self.driver.quit()
