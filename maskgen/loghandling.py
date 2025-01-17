# =============================================================================
# Authors: PAR Government
# Organization: DARPA
#
# Copyright (c) 2016 PAR Government
# All rights reserved.
# ==============================================================================

from __future__ import print_function
import time
import logging
from logging import handlers, config
from logging import FileHandler
import os


class MaskGenTimedRotatingFileHandler(handlers.TimedRotatingFileHandler):
    """
    Always roll-over if it is a new day, not just when the process is active
    """
    forceRotate = False

    def __init__(self, filename):
        if os.path.exists(filename):
            yesterday = time.strftime("%Y-%m-%d", time.gmtime(int(os.stat(filename).st_ctime)))
            today = time.strftime("%Y-%m-%d", time.gmtime(time.time()))
            self.forceRotate = (yesterday != today)
        handlers.TimedRotatingFileHandler.__init__(self, filename, when='D', interval=1, utc=True)

    def shouldRollover(self, record):
        """
                Determine if rollover should occur

                record is not used, as we are just comparing times, but it is needed so
                the method siguratures are the same
                """
        t = int(time.time())
        if t >= self.rolloverAt or self.forceRotate:
            self.forceRotate = False
            return 1
        return 0


def set_logging_level(level):
    logging.getLogger('maskgen').setLevel(level)
    for handler in logging.getLogger('maskgen').handlers:
        handler.setLevel(level)


def unset_logging(directory=None,logger_name = 'maskgen'):
    logger = logging.getLogger(logger_name)
    for handler in logger.handlers:
        if isinstance(handler, FileHandler):
            if directory is None or os.path.abspath(directory) in os.path.abspath(handler.baseFilename):
                logger.removeHandler(handler)
                handler.close()

def set_logging(directory=None, filename='maskgen.log',skip_config=False,logger_name = 'maskgen'):
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    for handler in logger.handlers:
        logger.removeHandler(handler)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    # create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s[%(threadName)s:%(process)d]- %(levelname)s - %(message)s')

    # add formatter to ch
    ch.setFormatter(formatter)

    # add ch to logger
    logger.addHandler(ch)

    dir = directory if directory is not None and os.path.isdir(directory) else '.'
    logfile = os.path.join(os.getenv("HOME"), filename) if not os.access(dir, os.W_OK) else os.path.join(dir, filename)

    fh = MaskGenTimedRotatingFileHandler(logfile)

    fh.setLevel(logging.INFO)
    # add formatter to ch
    fh.setFormatter(formatter)

    # add ch to logger
    logger.addHandler(fh)

    if not skip_config and os.path.exists('logging.config'):
        print('Establishing logging configuration from file')
        config.fileConfig('logging.config')


def flush_logging():
    logger = logging.getLogger('maskgen')
    for handler in logger.handlers:
        handler.flush()
