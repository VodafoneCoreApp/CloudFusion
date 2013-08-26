'''
Created on 12.05.2011

'''
from cloudfusion.pyfusebox.configurable_pyfusebox import ConfigurablePyFuseBox
from cloudfusion.fuse import FUSE
import os, sys
import logging.config
from mylogging import db_logging_thread
from cloudfusion.mylogging.nullhandler import NullHandler
import cloudfusion

def check_arguments(args):
    if not len(args) in [2,3,4]:
        print 'usage: %s mountpoint [foreground] [log]' % args[0]
        exit(1)

def main():
    check_arguments(sys.argv)
    foreground  = False 
    if "foreground" in sys.argv:
        foreground = True
    if not "log" in sys.argv:
        logging.getLogger().addHandler(NullHandler())
    else:
        if not os.path.exists(".cloudfusion/logs"):
            os.makedirs(".cloudfusion/logs")
        logging.config.fileConfig(os.path.dirname(cloudfusion.__file__)+'/config/logging.conf')
        db_logging_thread.start()
        db_handler = db_logging_thread.create_dbhandler()
        logging.getLogger().addHandler(db_handler)

    if not os.path.exists(sys.argv[1]):
        os.makedirs(sys.argv[1])
    fuse_operations = ConfigurablePyFuseBox(sys.argv[1])
    FUSE(fuse_operations, sys.argv[1], foreground=foreground, nothreads=True)
    
if __name__ == '__main__':
    main()