"""
util.ansi_color_formatter - Color Formatter for Logging package

Rf: https://medium.com/@kamilmatejuk/inside-python-colorful-logging-ad3a74442cc6
"""
import logging

class AnsiColorFormatter(logging.Formatter):
    STYLES = {
        'no_style': '\033[0m',
        'bold': '\033[91m',
        'red': '\033[31m',
        'green': '\033[32m',
        'yellow': '\033[33m',
        'blue': '\033[34m',
        'purple': '\033[35m',
        'cyan': '\033[36m',
        'white': '\033[37m',
        'black_light': '\033[90m',
        'red_light': '\033[91m',
        'green_light': '\033[92m',
        'yellow_light': '\033[93m',
        'blue_light': '\033[94m',
        'purple_light': '\033[95m',
        'cyan_light': '\033[96m',
        'white_light': '\033[97m'
    }
    def format(self, record: logging.LogRecord):
        level_style = {
            'DEBUG': self.STYLES['black_light'],
            'INFO': self.STYLES['cyan'],
            'WARNING': self.STYLES['yellow'],
            'ERROR': self.STYLES['red'],
            'CRITICAL': self.STYLES['red_light'] + self.STYLES['bold'],
        }.get(record.levelname, self.STYLES['no_style'])
        end_style = self.STYLES['no_style']

        if isinstance(record.msg, str):
            try:
                record.msg = record.msg.format(**self.STYLES)
            except Exception:
                pass
        formatted_msg = super().format(record=record)
        return f'{level_style}{formatted_msg}{end_style}'
