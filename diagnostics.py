"""Bounded local logs and an optional redacted diagnostic export."""
import copy
import logging
from logging.handlers import RotatingFileHandler
import sys
import threading


def configure_logging(directory):
    logger=logging.getLogger('lumaflow');logger.setLevel(logging.INFO)
    try:
        directory.mkdir(parents=True,exist_ok=True)
        handler=RotatingFileHandler(directory/'lumaflow.log',maxBytes=1024*1024,backupCount=3,encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    previous=sys.excepthook
    def exception(kind,value,traceback):
        logger.critical('Unhandled application exception',exc_info=(kind,value,traceback))
        previous(kind,value,traceback)
    sys.excepthook=exception
    def thread_exception(args):
        logger.critical('Unhandled worker exception',exc_info=(args.exc_type,args.exc_value,args.exc_traceback))
    threading.excepthook=thread_exception
    return logger


def export_payload(settings,status,reports,logs,build,redact=True):
    payload=copy.deepcopy({'app':'LumaFlow '+build['version'],'build':build,'settings':settings,
        'status':status,'gatt':reports,'logs':logs,'redacted':redact})
    if not redact:return payload
    replacements={}
    for i,device in enumerate(payload['settings'].get('devices',[]),1):
        for key in ('address','name','id'):
            value=device.get(key)
            if isinstance(value,str) and value:replacements[value]=f'device-{i}' if key=='id' else f'[device-{i}-{key}]'
    def scrub(value):
        if isinstance(value,dict):return {scrub(k):scrub(v) for k,v in value.items()}
        if isinstance(value,list):return [scrub(v) for v in value]
        if isinstance(value,tuple):return tuple(scrub(v) for v in value)
        if isinstance(value,str):
            if value in replacements:return replacements[value]
            for private,replacement in replacements.items():
                if len(private)>=4:value=value.replace(private,replacement)
        return value
    return scrub(payload)
