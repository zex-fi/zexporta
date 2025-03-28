import logging


def get_logger_config(logger_path: str):
    return {
        "version": 1,
        "formatters": {"standard": {"format": "%(levelname)s | %(asctime)s | %(module)s  | %(message)s"}},
        "handlers": {
            "console": {
                "level": "WARNING",
                "class": "logging.StreamHandler",
                "formatter": "standard",
            },
            "file": {
                "level": "DEBUG",
                "class": "logging.handlers.TimedRotatingFileHandler",
                "filename": logger_path,
                "when": "midnight",
                "interval": 1,
                "backupCount": 7,
                "formatter": "standard",
            },
        },
        "loggers": {
            "": {
                "handlers": ["console", "file"],
                "level": "DEBUG",
                "propagate": False,
            },
        },
    }


class ChainLoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger, chain_symbol: str):
        super().__init__(logger, {"chain": chain_symbol})

    def process(self, msg, kwargs):
        msg = f"{self.extra['chain']:<10} | {msg}"  # type:  ignore
        return msg, kwargs
