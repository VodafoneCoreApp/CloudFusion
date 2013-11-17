'''
Created on May 7, 2013

@author: joe
'''
import logging

class NullHandler(logging.Handler):
    '''
    Logging handler doing nothing (if python 2.6 is used this handler is not available by default).
    '''
    lock = None
    def emit(self, *args, **kwargs):
        pass
    
    def handle(self, record):
        pass
    
    def createLock(self):
        return None
