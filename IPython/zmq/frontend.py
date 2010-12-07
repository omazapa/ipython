# -*- coding: utf-8 -*-
"""Frontend of ipython working with python-zmq

Ipython's frontend, is a ipython interface that send request to kernel and proccess the kernel's outputs.

For more details, see the ipython-zmq design
"""
#-----------------------------------------------------------------------------
# Copyright (C) 2010 The IPython Development Team
#
# Distributed under the terms of the BSD License. The full license is in
# the file COPYING, distributed as part of this software.
#-----------------------------------------------------------------------------

#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

import __builtin__
from contextlib import nested
import time
import sys
import os
import signal
import uuid
import cPickle as pickle
import code
import zmq
import rlcompleter
import time


# our own
import zmq
import session
import completer
from IPython.utils.localinterfaces import LOCALHOST


#-----------------------------------------------------------------------------
# Imports from ipython
#-----------------------------------------------------------------------------
from IPython.utils.traitlets import (
Int, Str, CBool, CaselessStrEnum, Enum, List, Unicode
)
from IPython.core.iplib import get_default_colors
from IPython.core.excolors import exception_colors
from IPython.utils import PyColorize
from IPython.core.blockbreaker import BlockBreaker
from kernelmanager import KernelManager
from IPython.zmq.session import Session
from IPython.zmq import completer

class Frontend(object):
   """ this class is a simple frontend to ipython-zmq 
       
      NOTE: this class use kernelmanager to manipulate sockets
      
      Parameters:
      -----------
      kernelmanager : object
        instantiated object from class KernelManager in module kernelmanager
        
   """
   
   def __init__(self,kernelmanager):
       self.km = kernelmanager
       self.km.start_channels()
       time.sleep(0.5)
       self.session = kernelmanager.session
       self.km.xreq_channel.ioloop.stop()
       self.km.sub_channel.ioloop.stop()
       self.km.rep_channel.ioloop.stop()
       self.request_socket = self.km.xreq_channel.socket
       self.sub_socket = self.km.sub_channel.socket
       self.reply_socket = self.km.rep_channel.socket
       
       
       self.colors = CaselessStrEnum(('NoColor','LightBG','Linux'),
                                      default_value=get_default_colors(), config=True)
       self.pyformat = PyColorize.Parser().format
       self.pycolorize = lambda src: self.pyformat(src,'str',self.colors)
       self.ec = exception_colors()
       self.ec.set_active_scheme('Linux')
       self.ec.active_colors.keys()
       
       
       self.completer = completer.ClientCompleter(self,self.session,self.request_socket)
       rlcompleter.readline.parse_and_bind("tab: complete")
       rlcompleter.readline.parse_and_bind('set show-all-if-ambiguous on')
       rlcompleter.Completer = self.completer.complete
       
       history_path = os.path.expanduser('~/.ipython/history')
       if os.path.isfile(history_path):
           rlcompleter.readline.read_history_file(history_path)
       else:
           print("history file can not be readed.")   
       self.handlers = {}
       for msg_type in ['pyin', 'pyout', 'pyerr', 'stream']:
           self.handlers[msg_type] = getattr(self, 'handle_%s' % msg_type)
       self.messages = {}
       self.kernel_pid = None
       self.get_kernel_pid()
       self.prompt_count = 0
       self.prompt_count = self.get_prompt()
       self.backgrounded = 0
        
   def interact(self):
       """ let you get input from console using inputsplitter, then
       while you enter code it can indent and set index id to any input

       """    
       try:
           bb = BlockBreaker()
           bb.push(raw_input('In[%i]:'%self.prompt_count))
           while not bb.interactive_block_ready():
               code = raw_input('....:'+' '*bb.indent_spaces)    
               more=bb.push(' '*bb.indent_spaces+code)
               if not more:
                   bb.indent_spaces = bb.indent_spaces-4
           self.runcode(bb.source)
           bb.reset()
           self.prompt_count = self.get_prompt() 
       except  KeyboardInterrupt:
           print('\nKeyboardInterrupt\n')    
           pass
   def kernel_stop(self):
       self.send_kernel_signal(signal.SIGQUIT)
   
   def interrupt(self):
       self.send_kernel_signal(signal.SIGINT)
       
   def send_kernel_signal(self,signal_type):
       os.kill(self.kernel_pid,signal_type)    
       
   def start(self):
       """ init a bucle that call interact method to get code.
       
       """
       while True:
           try:
               self.interact()    
           except EOFError:
               answer = ''    
               while True:
                   answer = raw_input('\nDo you really want to exit ([y]/n)?')
                   if answer == 'y' or answer == '' :
                       sys.exit()
                   elif answer == 'n':
                       break
   
   def handle_pyin(self, omsg):
       """ handler that print inputs of other users in the kernel_pid
       
       Explanation: if two users are working in a kernel, when user one send someting to kernel
       the user two see in terminal the input from user one.
       
       Parameters:
       -----------
       
       omsg : dict
           message that content session information like user and ids, and input
           from other users.
       
       """
       
       if omsg.parent_header.session == self.session.session:
            return
       c = omsg.content.code.rstrip()
       if c:
           print '[IN from %s]' % omsg.parent_header.username
           print c
           
   def handle_pyout(self, omsg):
       """ handler that print stdout ouputs captured in kernel and index of outputs
       generate by ipython
       
  
       
       Parameters:
       -----------
       
       omsg : dict
           message that content session information like user and ids, index of output
           and data to print in stdout
       
       """
       if omsg.parent_header.session == self.session.session:
           print "%s%s" % ("Out[%i]: "%omsg.content.index, omsg.content.data)
       else:
           print '[Out[%i] from %s]' %(omsg.content.index,omsg.parent_header.username)
           print omsg.content.data
   
   def print_pyerr(self, err):
       """ handler that print traceback captured in kernel and it show tracebacks in frontend
        
       
       Parameters:
       -----------
       
       err : dict
           message that content information about traceback
       
       """
       print(err.etype+'\n'+err.evalue+'\n'+''.join(err.traceback))
       
   def handle_pyerr(self, omsg):
       """ handler that print errors in stderr captured in kernel and show the user that generate the error
        
       
       Parameters:
       -----------
       
       omsg : dict
           message that content session information like user and ids, and data to print in stderr
       
       """           
       if omsg.parent_header.session == self.session.session:
           return
       print >> sys.stderr, '[ERR from %s]' % omsg.parent_header.username
       self.print_pyerr(omsg.content)
       
   def handle_stream(self, omsg):
       """ handler that print errors in stderr, outputs in stdout, and get a raw_input's request from kernel
       to activate a local raw_input in frontend to send the reply to kernel again.
        
       
       Parameters:
       -----------
       
       omsg : dict
           message that content session information like user and ids, and data to print in stderr or stdout.
       
       """           
       
       try:
           if omsg.content.name == 'stdout':
               outstream = sys.stdout
               print >> outstream, omsg.content.data
           elif omsg.content.name == 'stderr':
               outstream = sys.stderr
               print >> outstream, omsg.content.data
           else:  
               promt_msg = self.reply_socket.recv_json()    
               raw_output=raw_input(promt_msg)    
               self.reply_socket.send_json(raw_output)
       except KeyboardInterrupt:
               os.kill(self.kernel_pid,signal.SIGINT)
       
   def handle_output(self, omsg):
       """ handler that call the other handlers depending of it type.
       
       Parameters:
       -----------
       
       omsg : dict
           message that content session information like user and ids, and msg_type       
       """                 
       handler = self.handlers.get(omsg.msg_type, None)
       if handler is not None:
           handler(omsg)    

   def recv_output(self):
       """ Method that wait a output after to send a request to kernel, and when it have a
       response call to handle_output to proccess the message.
       
       """                            
       while True:
           try:    
               omsg = self.session.recv(self.sub_socket)
               if omsg is None:
                   break
               self.handle_output(omsg)
           except KeyboardInterrupt:
                self.interrupt()
                break
                       
       
   def handle_reply(self, rep):
        """ handler that have the status of the response and call the other handlers depending of it type to show the outputs.
       
           Parameters:
           -----------
       
           rep : dict
               message that content the status of reply, the status can be ok, error or aborted       
        """                 
   
        # Handle any side effects on output channels
        self.recv_output()
        # Now, dispatch on the possible reply types we must handle
        if rep is None:
            return
        
        if rep['content']['status'] == 'error':
            self.print_pyerr(rep.content)            
        elif rep['content']['status'] == 'aborted':
            print >> sys.stderr, "ERROR: ABORTED"
            ab = self.messages[rep.parent_header.msg_id].content
            if 'code' in ab:
                print >> sys.stderr, ab.code
            else:
                print >> sys.stderr, ab

   def recv_reply(self):
        """  wait for reply in request socket to process the messages using the hendlers.
        
        """                   
        rep = self.session.recv(self.request_socket)
        self.handle_reply(rep)
        return rep
   
   def get_kernel_pid(self):
        """ let you get kernel's pid (proccess id) sending a pid_request message.
        
        Returns:
        --------
        kernel_pid : int
             pid gotten from kernel
        """
        omsg = self.session.send(self.request_socket,'pid_request')
        while True:
           rep = self.session.recv(self.request_socket)
           
           if rep is not None:
               self.kernel_pid=rep['content']['pid']
               break
           time.sleep(0.05)
        return self.kernel_pid
        
   def get_prompt(self):
       """ let you get prompt index from ipython's kernel, to index de inputs and outputs synchronized
       between kernel and frontend
       
       Returns:
       --------
       prompt_count : int
            current prompt number in kernel
       
       """
       prompt_msg = {'current':self.prompt_count }
       omsg = self.session.send(self.request_socket,'prompt_request',prompt_msg)
       while True:
           rep = self.session.recv(self.request_socket)
           
           if rep is not None:
               self.prompt_count=int(rep['content']['prompt'])
               break
           time.sleep(0.05)
       return self.prompt_count

        

   def runcode(self, src):
       """ send execute_request`s message to kernel and let you run code in src parameter into ipython kernel.
       
       Parameters:
       ----------
       src : str
           python or ipython's code to run
       """
       code=dict(code=src)
       code['prompt'] = self.prompt_count
       omsg = self.session.send(self.request_socket,
                                 'execute_request', code)
       self.messages[omsg.header.msg_id] = omsg
       
        # Fake asynchronicity by letting the user put ';' at the end of the line
       if src.endswith(';'):
           self.backgrounded += 1
           return

<<<<<<< HEAD
        # For foreground jobs, wait for reply
       while True:
           rep = self.recv_reply()
           
           if rep is not None:
               break
           self.recv_output()
           time.sleep(0.05)
       else:
           # We exited without hearing back from the kernel!
           print >> sys.stderr, 'ERROR!!! kernel never got back to us!!!'
=======
def main():
    # Defaults
    #ip = '192.168.2.109'
    ip = LOCALHOST
    #ip = '99.146.222.252'
    port_base = 5575
    connection = ('tcp://%s' % ip) + ':%i'
    req_conn = connection % port_base
    sub_conn = connection % (port_base+1)
>>>>>>> f0963426817946b1409d15532340f6f3effa0f17
    
   def send_noninteractive_request(self,code):
       """ this method was designed to send request code in non interactive mode.
       code content python or ipython code to run and the reply status was recived 
       here.
       to get all others outputs see the method recv_request_output 
       
       Parameters:
       code : str
           python or ipython's code to run in kernel in mode noninteractive
       
       Returns:
       --------
       rep_msg : dict
           dictionary that content the status of execution (ok, error, aborted)
       """
       code=dict(code=code)
       code['prompt'] = self.prompt_count
       omsg = self.session.send(self.request_socket,'execute_request', code)
       self.messages[omsg.header.msg_id] = omsg
       while True:
           rep_msg = self.request_socket.recv_json()
           if rep_msg is not None:
               break    
       return rep_msg
       
   def recv_noninteractive_reply(self):
       """method that recv output from kernels when you send a request in non interactive mode
       outputs can be pyin, pyerr or stream.
       
       Returns:
       --------
       
       output_msg : dict
           message that content outputs like stdout or stderr gotten in kernel from 
           last noninteractive request
       
       """
       output_msg = self.session.recv(self.sub_socket)
       return output_msg
       
def start_frontend():
    """ function that start a kernel with default parameters 
    """
    # Defaults
    xreq_addr = ('127.0.0.1',5555)
    sub_addr = ('127.0.0.1', 5556)
    rep_addr = ('127.0.0.1', 5557)
    context = zmq.Context()
    session = Session()
 
    km = KernelManager(xreq_addr, sub_addr, rep_addr,context,None)
    
    # Make session and user-facing client
    frontend=Frontend(km)
    frontend.start()

if __name__ == "__main__" :
     start_frontend()   
