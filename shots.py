#!/usr/bin/env python2

import os
import sys
import argparse
import threading
import atexit
from time import sleep
from Queue import Queue
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from httplib import BadStatusLine
from urllib2 import URLError

_colored = lambda s, *args: s
try:
    from termcolor import colored
except ImportError:
    colored = _colored


_WEBDRIVERS = []


def kill_webdrivers(): # selenium doesn't clean up driver instances
    for driver in _WEBDRIVERS:
        driver.quit()

atexit.register(kill_webdrivers)


def filename_from_url(url):
    return url.replace("/", "_")


def create_driver_instance(driver_type):
    try:
        return {
            "phantomjs": webdriver.PhantomJS,
            "firefox"  : webdriver.Firefox,
            "chrome"   : webdriver.Chrome,
            "ie"       : webdriver.Ie,
            "safari"   : webdriver.Safari,
            "opera"    : webdriver.Opera,
        }[driver_type]()
    except KeyError:
        raise ValueError("Invalid driver type")


def worker(queue, driver_type, timeout, outdir):
    driver = create_driver_instance(driver_type)
    driver.set_page_load_timeout(timeout)
    _WEBDRIVERS.append(driver)
    while True:
        url = queue.get()
        try:
            driver.get(url)
            filename = os.path.join(outdir, filename_from_url(url) + ".png")
            driver.save_screenshot(filename)
        except TimeoutException:
            msg = colored("timeout ", "red", attrs=["bold"]) + url
            sys.stderr.write(msg + "\n")
        except (URLError, BadStatusLine): # raised on sigint
            pass
        else:
            msg = colored("fetched ", "green", attrs=["bold"]) + "{0} -> {1}".format(url, filename)
            sys.stderr.write(msg + "\n")
        finally:
            queue.task_done()


def create_thread(target, args):
    t = threading.Thread(target=target, args=args)
    t.daemon = True
    t.start()


def fill_queue(queue, fileobj, finished=None):
    while True:
        url = fileobj.readline().rstrip("\n")
        if not url:
            if finished is not None:
                finished.set()
            break
        queue.put(url)


def wait_till_queue_finished(queue, finished):
    queue.join()
    finished.set()


def main(urlfile, outdir, driver, jobs, timeout):
    def wait_for_event(ev):
        while not ev.is_set():
            sleep(1)
    if not os.path.exists(outdir):
        os.mkdir(outdir)
    queue = Queue(jobs)
    for _ in xrange(jobs):
        create_thread(worker, (queue, driver, timeout, outdir))
    fileobj = sys.stdin if urlfile == "-" else open(urlfile)
    finished = threading.Event()
    # run blocking operations in threads, allowing keyboard interrupts etc.
    create_thread(fill_queue, args=(queue, fileobj, finished)) 
    wait_for_event(finished)
    finished.clear()
    create_thread(wait_till_queue_finished, (queue, finished))
    wait_for_event(finished)
    fileobj.close()


parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("urlfile", help="urlfile, use - to read URLs from stdin")
parser.add_argument("-j", "--jobs", type=int, default=5,
                    help="phantomjs instances", dest="jobs")
parser.add_argument("-o", "--out-dir", default=".",
                    help="output directory", dest="outdir")
parser.add_argument("-t", "--timeout", type=int, default=6,
                    help="page load timeout", dest="timeout")
parser.add_argument("--no-color", action="store_true", help="no colored output",
                    dest="no_color")
parser.add_argument("-d", "--driver", choices=\
                    ("phantomjs", "firefox", "chrome", "ie", "safari", "opera"),
                    default="phantomjs", dest="driver")

if __name__ == "__main__":
    args = parser.parse_args()
    if args.no_color:
        colored = _colored
    try:
        main(args.urlfile, args.outdir, args.driver, args.jobs, args.timeout)
    except KeyboardInterrupt:
        pass
