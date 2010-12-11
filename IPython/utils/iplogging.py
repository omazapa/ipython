# -*- coding: utf-8 -*-
"""Colors Support on logging messages"""
#****************************************************************************
#Wrotte by Omar Andres Zapata Mesa  
from IPython.utils.coloransi import TermColors
import logging


#****************************************************************************
# Builtin color schemes

Colors = TermColors  # just a shorthand

#****************************************************************************
#needed to get colored output
RESET = "\033[0m"
COLOR = "\033[1;%dm"
BOLD = "\033[1m"
#color associated with level 
LEVEL_COLORS = {
        'WARNING': Colors.Yellow,
        'INFO': Colors.Blue,
        'DEBUG': Colors.LightGray,
        'CRITICAL': Colors.Green,
        'ERROR': Colors.Red
        }
#****************************************************************************
#format to output
FORMAT = "%(name)s\n%(levelname)s\n%(process)s\n%(filename)s\n%(lineno)s\n%(message)s"



class ColorFormatter(logging.Formatter):
    """Message Formatter for Logging Messages
        
        
        it works creating an StreamHandler, 
        setting a ColorFormatter object like a formatter in  StreamHandler
        and adding this handler to logging.
        Example:
        console = logging.StreamHandler()
        console.setFormatter(ColorFormatter(FORMAT))
        logging.getLogger().addHandler(console)        
    """
    def __init__(self, message, use_color=False):
        logging.Formatter.__init__(self, message)
        self.use_color = use_color
 
    def format(self, record):
        """Overload method of Class loggin.Formatter
            that put colors and sort the message.
        """        
        levelname = record.levelname
        if self.use_color and levelname in LEVEL_COLORS :
            #setting message tag colors
            levelname_color   = LEVEL_COLORS[levelname] + "LEVEL: "+ RESET
            filename_color    = LEVEL_COLORS[levelname] + "FILE: " + RESET
            lineno_color      = LEVEL_COLORS[levelname] + "LINE: " + RESET
            msg_color         = LEVEL_COLORS[levelname] + "MESSAGE: " + RESET
            name_color        = LEVEL_COLORS[levelname] + "LOGGER: "+ RESET
            module_color      = LEVEL_COLORS[levelname] + "MODULE: "+ RESET
            pathname_color    = LEVEL_COLORS[levelname] + "PATH: "+ RESET
            funcName_color    = LEVEL_COLORS[levelname] + "FUNCTION NAME: "+ RESET
            process_color     = LEVEL_COLORS[levelname] + "PROCESS: "+ RESET
            processName_color = LEVEL_COLORS[levelname] + "PROCESS NAME: "+ RESET
            thread_color      = LEVEL_COLORS[levelname] + "THREAD: "+ RESET
            threadName_color  = LEVEL_COLORS[levelname] + "THREAD NAME: "+ RESET
            
            
            #adding message tag with color and original data
            record.levelname     = levelname_color     +  record.levelname
            record.filename      = filename_color      +  record.filename
            record.lineno        = lineno_color        +  str(record.lineno)
            record.msg           = msg_color           +  str(record.msg)
            record.name          = name_color          +  record.name
            record.module        = module_color        +  record.module
            record.pathname      = pathname_color      +  record.pathname
            record.funcName      = funcName_color      +  record.funcName
            record.process       = process_color       +  str(record.process)
            record.processName   = processName_color   +  str(record.processName)
            record.thread        = thread_color        +  str(record.thread)
        else:
            record.levelname   = "LEVEL: " + record.levelname
            record.filename    = "FILE: " + record.filename 
            record.lineno      = "LINE: " + str(record.lineno)
            record.msg         = "MESSAGE: " + record.msg
            record.name        = "LOGGER: " + record.name
            record.module      = "MODULE: " + record.module
            record.pathname    = "PATH: " + record.pathname
            record.funcName    = "FUNCTION NAME: " + record.funcName
            record.process     = "PROCESS: " + str(record.process)
            record.processName = "PROCESS NAME: " + record.processName
            record.thread      = "THREAD: " + str(record.thread)
            record.threadName  = "THREAD NAME: " + record.threadName 
        return logging.Formatter.format(self, record)
        
IpStreamHandler = logging.StreamHandler()
IpLogger = logging.getLogger()        
##Return a Logguer 
def get_logger(name=None,format=FORMAT,use_color = False):
    IpStreamHandler.setFormatter(ColorFormatter(format,use_color))
    IpLogger.addHandler(IpStreamHandler)
    IpLogger.setLevel(logging.DEBUG)
    return logging.getLogger(name)
