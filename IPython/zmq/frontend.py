#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyrigth 2010 Omar Andres Zapata Mesa
# Copyrigth 2010 Fernando Perez
# Copyrigth 2010 Brian Granger

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
from IPython.core.blockbreaker import BlockBreaker
from kernelmanager import KernelManager

from  IPython.zmq.session import Session
import completer
import rlcompleter
import time
#class IpXReqSocketChannel(XReqSocketChannel):
   #def __init__(self, context, session, address):
       #super(XReqSocketChannel, self).__init__(context, session, address)



class Frontend(object):
   """ this class is a simple frontend to ipython-zmq 
   """
   
   def __init__(self,kernelmanager):
       self.km = kernelmanager
       self.km.start_channels()
       time.sleep(0.05)
       self.session = kernelmanager.session
       self.km.xreq_channel.ioloop.stop()
       self.km.sub_channel.ioloop.stop()
       self.km.rep_channel.ioloop.stop()
       self.request_socket = self.km.xreq_channel.socket
       self.sub_socket = self.km.sub_channel.socket
       self.reply_socket = self.km.rep_channel.socket
       
       
       self.completer = completer.ClientCompleter(self,self.session,self.request_socket)
       rlcompleter.readline.parse_and_bind("tab: complete")
       rlcompleter.readline.parse_and_bind('set show-all-if-ambiguous on')
       rlcompleter.Completer=self.completer.complete
       
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
       #this is a experimental code to trap KeyboardInterrupt in bucles
       #self.prompt_count = 1
        
   def interact(self):
       try:
           bb = BlockBreaker()
           bb.push(raw_input('In[%i]:'%self.prompt_count))
           while not bb.interactive_block_ready():
               code = raw_input('....:'+' '*bb.indent_spaces)    
               more=bb.push(' '*bb.indent_spaces+code)
               if not more:
                   bb.indent_spaces = bb.indent_spaces-4
           self.runcode(bb.source)
           #self.km.xreq_channel.execute(bb.source)
           bb.reset()
           self.prompt_count = self.get_prompt() 
       except  KeyboardInterrupt:
           print('\nKeyboardInterrupt\n')    
           pass
   def start(self):
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
       #print "handle_pyin:\n",omsg
       if omsg.parent_header.session == self.session.session:
            return
       c = omsg.content.code.rstrip()
       if c:
           print '[IN from %s]' % omsg.parent_header.username
           print c
           
   def handle_pyout(self, omsg):
       #print "handle_pyout:\n",omsg # dbg
       if omsg.parent_header.session == self.session.session:
           print "%s%s" % ("Out[%i]: "%omsg.content.index, omsg.content.data)
       else:
           print '[Out[%i] from %s]' %(omsg.content.index,omsg.parent_header.username)
           print omsg.content.data
   
   def print_pyerr(self, err):
       #I am studing how print a beautyfull message with IPyhton.core.utratb
       print(err.etype+'\n'+err.evalue+'\n'+''.join(err.traceback))
       
   def handle_pyerr(self, omsg):
       #print "handle_pyerr:\n",omsg
       if omsg.parent_header.session == self.session.session:
           return
       print >> sys.stderr, '[ERR from %s]' % omsg.parent_header.username
       self.print_pyerr(omsg.content)
       
   def handle_stream(self, omsg):
       #print "handle_stream:\n",omsg
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
               #self.write('\nKeyboardInterrupt\n')
       
   def handle_output(self, omsg):
       #print "handle_output:\n",omsg
       handler = self.handlers.get(omsg.msg_type, None)
       if handler is not None:
           handler(omsg)    

   def recv_output(self):
       #print "recv_output:"
       while True:
           try:    
               omsg = self.session.recv(self.sub_socket)
               if omsg is None:
                   break
               self.handle_output(omsg)
           except KeyboardInterrupt:
                os.kill(self.kernel_pid,int(signal.SIGINT))
                #self.write('\nKeyboardInterrupt\n')
                break
                       
       
   def handle_reply(self, rep):
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
        rep = self.session.recv(self.request_socket)
        self.handle_reply(rep)
        return rep
   
   def get_kernel_pid(self):
        omsg = self.session.send(self.request_socket,'pid_request')
        while True:
           #print "waiting recieve"
           rep = self.session.recv(self.request_socket)
           
           if rep is not None:
               self.kernel_pid=rep['content']['pid']
               break
           time.sleep(0.05)
        return self.kernel_pid
        
   def get_prompt(self):
       prompt_msg = {'current':self.prompt_count }
       omsg = self.session.send(self.request_socket,'prompt_request',prompt_msg)
       while True:
           #print "waiting recieve"
           rep = self.session.recv(self.request_socket)
           
           if rep is not None:
               #print(rep)    
               self.prompt_count=int(rep['content']['prompt'])
               break
           time.sleep(0.05)
       return self.prompt_count

        

   def runcode(self, src):
       code=dict(code=src)
       code['prompt'] = self.prompt_count
       omsg = self.session.send(self.request_socket,
                                 'execute_request', code)
       self.messages[omsg.header.msg_id] = omsg
       
        # Fake asynchronicity by letting the user put ';' at the end of the line
       if src.endswith(';'):
           self.backgrounded += 1
           return

        # For foreground jobs, wait for reply
       while True:
           #print "waiting recieve"
           rep = self.recv_reply()
           
           if rep is not None:
               break
           self.recv_output()
           time.sleep(0.05)
       else:
           # We exited without hearing back from the kernel!
           print >> sys.stderr, 'ERROR!!! kernel never got back to us!!!'
    
   def send_noninteractive_request(self,code):
       """ this method was designed to send request code in non interactive mode.
       code content python or ipython code to run and the reply status was recived 
       here.
       to get all others outputs see the method recv_request_output 
       """
       omsg = self.session.send(self.request_socket,'execute_request', dict(code=code))
       self.messages[omsg.header.msg_id] = omsg
       rep_msg = self.request_socket.recv_json()
       return rep_msg
       
   def recv_noninteractive_reply(self):
       """method that recv output from kernels when you send a request in non interactive mode
       outputs can be pyin, pyerr or stream.
       """
       output_msg = self.session.recv(self.sub_socket)
       return output_msg
       
if __name__ == "__main__" :
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
