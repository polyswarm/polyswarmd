import logging
import os
import signal

from polyswarmd.utils.logger import init_logging, LoggerConfig, PolyswarmdJsonFormatter


def test_init_logging():
    # arrange
    logger = logging.getLogger()
    # act
    init_logging('text', logging.INFO)
    # assert
    assert logger.level == logging.INFO


def test_init_logging_json():
    # arrange
    logger = logging.getLogger()
    # act
    init_logging('json', logging.INFO)
    # assert
    assert logger.level == logging.INFO
    assert any([isinstance(handler.formatter, PolyswarmdJsonFormatter) for handler in logger.handlers])


def test_logger_config_configure():
    # arrange
    logger = logging.getLogger()
    config = LoggerConfig('text', logging.INFO)
    # act
    config.configure()
    # assert
    assert logger.level == logging.INFO


def test_set_level():
    # arrange
    logger = logging.getLogger()
    config = LoggerConfig('text', logging.INFO)
    config.configure()
    # act
    config.set_level(logging.ERROR)
    # assert
    assert logger.level == logging.ERROR


def test_signal_handler():
    # arrange
    logger = logging.getLogger()
    config = LoggerConfig('text', logging.INFO)
    config.configure()
    # act
    os.kill(os.getpid(), signal.SIGUSR1)
    # assert
    assert logger.level == logging.WARNING


def test_signal_handler_critical_to_debug():
    # arrange
    logger = logging.getLogger()
    config = LoggerConfig('text', logging.CRITICAL)
    config.configure()
    # act
    os.kill(os.getpid(), signal.SIGUSR1)
    # assert
    assert logger.level == logging.DEBUG

