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

from IPython.core.iplib import InteractiveShell
import session
import completer
from IPython.core import ultratb
from IPython.utils.traitlets import (
    Int, Str, CBool, CaselessStrEnum, Enum, List, Unicode
)


class InteractiveShellFrontend(InteractiveShell):
   """ this class uses some meny features of Interactive shell,
       but it dont run code really, just let you interactue like ipython prompt
       and send messages to ipython kernel
    
   """
   #explanation:
   #if I inherited from InteractiveShell I have support to Colors in outputs, History, prompt indentation
   #and I can use too many features in the new frontend whithout run code here.
   
   def __init__(self,filename="<ipython_frontent>", session = session, request_socket=None, subscribe_socket=None,reply_socket=None):
       InteractiveShell.__init__(self)
       self.buffer_lines=[]
       
       self.completer=completer.ClientCompleter(self,session,request_socket)
       self.Completer=self.completer
       self.handlers = {}
       for msg_type in ['pyin', 'pyout', 'pyerr', 'stream','prompt']:
           self.handlers[msg_type] = getattr(self, 'handle_%s' % msg_type)
       self.session = session
       self.request_socket = request_socket
       self.sub_socket = subscribe_socket
       self.reply_socket = reply_socket
       self.backgrounded = 0
       self.messages = {}
       sys.excepthook = ultratb.VerboseTB()
       self.formattedtb=ultratb.FormattedTB()
       __builtin__.__dict__['__IPYTHON__active'] = 1
       self.push_line=self._push_line
       self.runsource=self._runsource
       self.runcode=self._runcode
       #when start frontend get kernel id
       self.kernel_pid=None
       self.get_kernel_pid()
       #this is a experimental code to trap KeyboardInterrupt in bucles
       
   def _push_line(self,line):
       """Reimplementation of method push_line in class InteractiveShell
       this method let indent into prompt when you need it
        """
       for subline in line.splitlines():
            self._autoindent_update(subline)
       self.buffer_lines.append(line)
       more = self._runsource('\n'.join(self.buffer_lines), self.filename)
       
       if more == None:
           self.buffer_lines[:]=[]
       return more
   
   def _runsource(self, source, filename='<input>', symbol='single'):
       """Reimplementation of method runsource in class InteractiveShell
          but dont run source really, just check syntax and send code to kernel
            
        """
       source=source.encode(self.stdin_encoding)
       if source[:1] in [' ', '\t']:
           source = 'if 1:\n%s' % source
       try:
           code = self.compile(source,filename,symbol)
           #warining this code is to try enabled prefiltered code
       except (OverflowError, SyntaxError, ValueError, TypeError, MemoryError):
            # Case 1
           self.showsyntaxerror(filename)
           return None

       if code is None:
            # Case 2
           return True
       else:
           self.runcode(self.buffer_lines)
           self.buffer_lines[:]=[]
           return False
        
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
       self.CustomTB(err.etype,err.evalue,''.join(err.traceback))
       
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
               promt_msg = self.reply_socket.recv()    
               raw_output=raw_input(promt_msg)    
               self.reply_socket.send(raw_output)
       except KeyboardInterrupt:
               os.kill(self.kernel_pid,signal.SIGINT)
               #self.write('\nKeyboardInterrupt\n')
       
   def handle_output(self, omsg):
       #print "handle_output:\n",omsg
       handler = self.handlers.get(omsg.msg_type, None)
       if handler is not None:
           handler(omsg)
           
   def handle_prompt(self,omsg):
           pass
       
       
   #def handle_kernel_pid(self,omsg):
       #print("in handel kernel")
       #self.kernel_pid=int(omsg['pid'])
       

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
        if rep.content.status == 'error':
            self.print_pyerr(rep.content)            
        elif rep.content.status == 'aborted':
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

   def _runcode(self, code):
       # We can't pickle code objects, so fetch the actual source
       
       src = '\n'.join(self.buffer_lines)
       # for non-background inputs, if we do have previoiusly backgrounded
       # jobs, check to see if they've produced results
       if not src.endswith(';'):
           while self.backgrounded > 0:
               #print 'checking background'
               rep = self.recv_reply()
               if rep:
                   self.backgrounded -= 1
               time.sleep(0.05)
       # Send code execution message to kernel
       #print "sending message"
       omsg = self.session.send(self.request_socket,
                                 'execute_request', dict(code=src))
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
    import zmq
    ip = '127.0.0.1'
    port_base = 5555
    connection = ('tcp://%s' % ip) + ':%i'
    req_conn = connection % port_base
    sub_conn = connection % (port_base+1)
    rep_conn = connection % (port_base+2)
    
    # Create initial sockets
    c = zmq.Context(1)
    request_socket = c.socket(zmq.XREQ)
    request_socket.connect(req_conn)
    
    sub_socket = c.socket(zmq.SUB)
    sub_socket.connect(sub_conn)
    sub_socket.setsockopt(zmq.SUBSCRIBE, '')
    
    reply_socket = c.socket(zmq.REP)
    reply_socket.connect(rep_conn)
    
    

    # Make session and user-facing client
    sess = session.Session()
    
    frontend=InteractiveShellFrontend('<zmq-console>',sess,request_socket=request_socket,subscribe_socket=sub_socket,reply_socket=reply_socket)
    frontend.interact()
