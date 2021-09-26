import logging

logging.config.dictconfig(
    {
        "version": "1",
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "stream": "ext://sys.stdout"
            }
        },
        'loggers': {
            'measure': {
                'handlers': ['console']
            }
        },
        "root": {
            "level": "DEBUG",
            "handlers": ["console"]
        },
    }
)