# -*- coding: utf-8 -*-
"""Colors Support on logging messages"""
#****************************************************************************
#Wrotte by Omar Andres Zapata Mesa  
from IPython.utils.coloransi import TermColors as Colors
from logging import DEBUG, FATAL, ERROR, WARNING, WARN, INFO, NOTSET
from logging import Filter, Formatter,LoggerAdapter, StreamHandler, Handler, PlaceHolder
from logging import Formatter, Logger, Manager, root
from logging import getLevelName, addLevelName
from logging import LogRecord, makeLogRecord
from logging import setLoggerClass, getLoggerClass
from logging import BASIC_FORMAT, basicConfig 


__author__  = "Omar Andres Zapata Mesa andresete.chaos@gmail.com"
__status__  = "production"
__date__    = "Nov/Dec 2010"


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
IPFORMAT = "%(name)s\n%(levelname)s\n%(process)s\n%(filename)s\n%(lineno)s\n%(message)s" 

class IpFormatter(Formatter):
    """Message Formatter for Logging Messages
        
        this class is for internal use only i IpLogger
        it works creating an StreamHandler, 
        setting a Formatter object like a formatter in  StreamHandler
        and adding this handler to logging.
        colors: enable or disable colors
        ipmde: display messages sort in ipython mode      
    """
    def __init__(self, fmt = None, datefmt=None,colors=False,ipmode = False):
        Formatter.__init__(self, fmt,datefmt)
        self._colors = colors
        self._ipmode = ipmode
        
    def format(self, record):
        """Overload method of Class loggin.Formatter
            that put colors and sort the message.
        """        
        levelname = record.levelname
        if self._ipmode :
            
            if self._colors and levelname in LEVEL_COLORS :
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
                record.name          = name_color          +  str(record.name)
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
                record.msg         = "MESSAGE: " + str(record.msg)
                record.name        = "LOGGER: " + str(record.name)
                record.module      = "MODULE: " + record.module
                record.pathname    = "PATH: " + record.pathname
                record.funcName    = "FUNCTION NAME: " + record.funcName
                record.process     = "PROCESS: " + str(record.process)
                record.processName = "PROCESS NAME: " + record.processName
                record.thread      = "THREAD: " + str(record.thread)
                record.threadName  = "THREAD NAME: " + record.threadName 
        else:
            if self._colors and levelname in LEVEL_COLORS :
                #setting message tag colors
                levelname_color   = LEVEL_COLORS[levelname] + record.levelname + RESET
                filename_color    = LEVEL_COLORS[levelname] + record.filename + RESET
                lineno_color      = LEVEL_COLORS[levelname] + str(record.lineno) + RESET
                msg_color         = LEVEL_COLORS[levelname] + str(record.msg) + RESET
                name_color        = LEVEL_COLORS[levelname] + str(record.name) + RESET
                module_color      = LEVEL_COLORS[levelname] + record.module + RESET
                pathname_color    = LEVEL_COLORS[levelname] + record.pathname + RESET
                funcName_color    = LEVEL_COLORS[levelname] + record.funcName + RESET
                process_color     = LEVEL_COLORS[levelname] + str(record.process)+ RESET
                processName_color = LEVEL_COLORS[levelname] + str(record.processName)+ RESET
                thread_color      = LEVEL_COLORS[levelname] + str(record.thread) + RESET
                threadName_color  = LEVEL_COLORS[levelname] + record.threadName + RESET
                
                
                #adding message  with color 
                record.levelname     = levelname_color     
                record.filename      = filename_color     
                record.lineno        = lineno_color       
                record.msg           = msg_color          
                record.name          = name_color         
                record.module        = module_color       
                record.pathname      = pathname_color     
                record.funcName      = funcName_color    
                record.process       = process_color     
                record.processName   = processName_color  
                record.thread        = thread_color       
                record.threadName    = threadName_color          
        return Formatter.format(self,record)


        
class IpLogger(Logger):
    """Class that provide an optional colored logger.
    default colors are False
    ex:
    mylogger=IpLogger("mymodule",colors=True)
    """
    def __init__(self, name = None,level = 0 ,colors = False, ipmode = False ):
        Logger.__init__(self, name,level)
        self._colors = colors
        self._ipmode = ipmode
    def addHandler(self, hdlr):
        """
        Add the specified handler to this logger.
        """
        #overloaded method to add optionals colors and ipython output mode to handlers
        if hdlr.formatter is  not None :
            ipformatter =  IpFormatter(hdlr.formatter._fmt,hdlr.formatter.datefmt,self._colors,self._ipmode)
        else:
            ipformatter =  IpFormatter(colors=self._colors,ipmode=self._ipmode)
        hdlr.formatter = ipformatter
        if not (hdlr in self.handlers):
            self.handlers.append(hdlr)

    def removeHandler(self, hdlr):
        """
        Remove the specified handler from this logger.
        """
        #writing handler as addHandler before to be removed
        if hdlr.formatter is  not None :
            ipformatter =  IpFormatter(hdlr.formatter._fmt,hdlr.formatter.datefmt,self._colors,self._ipmode)
        else:
            ipformatter =  IpFormatter(colors=self._colors,ipmode=self._ipmode)
        hdlr.formatter = ipformatter
        if hdlr in self.handlers:
            hdlr.acquire()
            try:
                self.handlers.remove(hdlr)
            finally:
                hdlr.release()

setLoggerClass(IpLogger)

def getLogger( name = None,colors = False, ipmode = False):
    """
    Return a logger with the specified name, creating it if necessary.

    If no name is specified, return the root logger.
    """
    if name:
        logger=Logger.manager.getLogger(name)
        logger._colors = colors
        logger._ipmode = ipmode
        return logger
    else:
        return root
        

   
