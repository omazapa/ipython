# -*- coding: utf-8 -*-
# Copyright 2010  Omar Andres Zapata Mesa
# Copyright 2010  Fernando Perez 
# Copyright 2010  Brian Granger

import __builtin__
import zmq
import sys
import time
import os
import subprocess

import traceback
from contextlib import nested

from IPython.utils.session import Session, Message, extract_header
from IPython.utils import session
from IPython.core.completer import IPCompleter
from IPython.core.iplib import InteractiveShell
from IPython.core import ultratb
from IPython.core import hooks
from IPython.core.display_trap import DisplayTrap
from IPython.core.builtin_trap import BuiltinTrap
from IPython.utils.io import IOTerm, Term
from IPython.utils.terminal import set_term_title
from IPython.frontend.process.killableprocess import Popen


class OutStream(object):
    """A file like object that publishes the stream to a 0MQ PUB socket."""

    def __init__(self, session, pub_socket,request_socket, name, max_buffer=200):
        self.session = session
        self.pub_socket = pub_socket
        self.request_socket = request_socket
        self.name = name
        self._buffer = []
        self._buffer_len = 0
        self.max_buffer = max_buffer
        self.parent_header = {}

    def set_parent(self, parent):
        self.parent_header = extract_header(parent)

    def close(self):
        self.pub_socket = None

    def flush(self):
        if self.pub_socket is None:
            raise ValueError(u'I/O operation on closed file')
        else:
            if self._buffer:
                data = ''.join(self._buffer)
                content = {u'name':self.name, u'data':data}
                msg = self.session.msg(u'stream', content=content,
                                       parent=self.parent_header)
                #print>>sys.__stdout__,"MESSAGE = ", Message(msg)
                self.pub_socket.send_json(msg)
                self._buffer_len = 0
                self._buffer = []

    def isattr(self):
        return False

    def next(self):
        raise IOError('Read not supported on a write only stream.')

    def read(self, size=None):
        self.request_socket.send(size)   
        #raise IOError('Read not supported on a write only stream.')
        raw_input_msg = self.request_socket.recv()
        return raw_input_msg

    readline=read

    def write(self, s):
        if self.pub_socket is None:
            raise ValueError('I/O operation on closed file')
        else:
            self._buffer.append(s)
            self._buffer_len += len(s)
            self._maybe_send()

    def _maybe_send(self):
        if '\n' in self._buffer[-1]:
            self._buffer=self._buffer[0:-1]
            self.flush()
        if self._buffer_len > self.max_buffer:
            self.flush()

    def writelines(self, sequence):
        if self.pub_socket is None:
            raise ValueError('I/O operation on closed file')
        else:
            for s in sequence:
                self.write(s)
    def fileno(self):
        if self.name == "stdout":
            return 1
        if self.name == "stderr":
            return 2
                    
                


class DisplayHook(object):

    def __init__(self, session, pub_socket):
        self.session = session
        self.pub_socket = pub_socket
        self.parent_header = {}

    def __call__(self, obj):
        if obj is None:
            return

        __builtin__._ = obj
        msg = self.session.msg(u'pyout', {u'data':repr(obj),u'index':self.index},
                               parent=self.parent_header)
        self.pub_socket.send_json(msg)

    def set_parent(self, parent):
        self.parent_header = extract_header(parent)
    def set_index(self,index):
        self.index=index



class InteractiveShellKernel(InteractiveShell):
    def __init__(self,session, reply_socket, pub_socket,request_socket):
        self.session = session
        self.reply_socket = reply_socket
        self.pub_socket = pub_socket
        self.request_socket = request_socket
        self.user_ns = {}
        self.history = []
        InteractiveShell.__init__(self,user_ns=self.user_ns,user_global_ns=self.user_ns)
        
        #getting outputs
        self.stdout = OutStream(self.session, self.pub_socket,self.request_socket, u'stdout')
        self.stderr = OutStream(self.session, self.pub_socket,self.request_socket, u'stderr')
        #self.stdin  = OutStream(self.session, self.pub_socket,self.request_socket, u'stdin')
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = self.stdout
        sys.stderr = self.stderr
        
        ##overloaded methods
        self.runcode = self._runcode
        self.push_line = self._push_line
        self.system = self._system
        self.interact = self._interact
        __builtin__.raw_input = self._raw_input
        
        self.display_hook = DisplayHook(self.session,self.pub_socket)
        self.outputcache.__class__.display = self.display_hook
        self.display_trap = DisplayTrap(self, self.outputcache)
        #self.InteractiveTB.out_stream=self.stderr
        self.init_readline()
        
        self.kernel_pid=os.getpid()
        
        self.handlers = {}
        for msg_type in ['execute_request', 'complete_request','prompt_request','pid_request']:
            self.handlers[msg_type] = getattr(self, msg_type)
       
    def _system(self, cmd):
        """Reimplementation of system, Make a system call, using IPython."""
        self.pipe=Popen(cmd, shell=True, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        stdout_output=self.pipe.stdout.read()
        stderr_output=self.pipe.stderr.read()
        
        if stdout_output.__len__() != 0 :
            for stdout in stdout_output.split('\n'):
                if stdout.__len__() != 0:
                    print >> self.stdout,stdout
        
        if stderr_output.__len__() != 0 :   
            for stderr in stderr_output.split('\n'):
                if stderr.__len__() != 0:    
                    print >> self.stderr,stderr
        
    
    def _runcode(self,code_obj):
        """This method is a reimplementation of method runcode 
        from InteractiveShell class to InteractiveShellKernel
        Execute a code object.

        When an exception occurs, self.showtraceback() is called to display a
        traceback.

        Return value: a flag indicating whether the code to be run completed
        successfully:

          - 0: successful execution.
          - 1: an error occurred.
        """
        old_excepthook,sys.excepthook = sys.excepthook, self.excepthook
        self.sys_excepthook = old_excepthook
        try:
            try:
                self.hooks.pre_runcode_hook()
                exec code_obj in self.user_global_ns, self.user_ns
            finally:
                # Reset our crash handler in place
                sys.excepthook = old_excepthook
        except SystemExit:
           self.resetbuffer()
           self.showtraceback(exception_only=True)
           warn("To exit: use any of 'exit', 'quit', %Exit or Ctrl-D.", level=1)
        except self.custom_exceptions:
            self.etype,self.value,self.tb = sys.exc_info()
            
    def _runlines(self,lines,clean=True):
        """Run a string of one or more lines of source.

        This method is capable of running a string containing multiple source
        lines, as if they had been entered at the IPython prompt.  Since it
        exposes IPython's processing machinery, the given strings can contain
        magic calls (%magic), special shell access (!cmd), etc.
        """

        if isinstance(lines, (list, tuple)):
            lines = '\n'.join(lines)

        if clean:
            lines = self.cleanup_ipy_script(lines)
        
        # We must start with a clean buffer, in case this is run from an
        # interactive IPython session (via a magic, for example).
        self.resetbuffer()
        lines = lines.splitlines()
        more = 0
        
        with nested(self.builtin_trap, self.display_trap):
            for line in lines:
                # skip blank lines so we don't mess up the prompt counter, but do
                # NOT skip even a blank line if we are in a code block (more is
                # true)
                
                if line or more:
                    # push to raw history, so hist line numbers stay in sync
                    self.input_hist_raw.append("# " + line + "\n")
                    prefiltered = self.prefilter_manager.prefilter_lines(line,more)
                    more = self._push_line(prefiltered)
                    # IPython's runsource returns None if there was an error
                    # compiling the code.  This allows us to stop processing right
                    # away, so the user gets the error message at the right place.
                    if more is None:
                        break
                else:
                    self.input_hist_raw.append("\n")
            # final newline in case the input didn't have it, so that the code
            # actually does get executed
            
            if more:
                self._push_line('\n')
                
    
    def _push_line(self, line):
        """ Reimplementation of Push a line to the interpreter.

        The line should not have a trailing newline; it may have
        internal newlines.  The line is appended to a buffer and the
        interpreter's _runsource() "Reimplemented method too for kernel" method is called with the
        concatenated contents of the buffer as source.  If this
        indicates that the command was executed or invalid, the buffer
        is reset; otherwise, the command is incomplete, and the buffer
        is left as it was after the line was appended.  The return
        value is 1 if more input is required, 0 if the line was dealt
        with in some way (this is the same as runsource()).
        """


        #print 'push line: <%s>' % line  # dbg
        for subline in line.splitlines():
            self._autoindent_update(subline)
        self.buffer.append(line)
        more = self._runsource('\n'.join(self.buffer), self.filename)
        if not more:
            self.resetbuffer()
        return more

    def _runsource(self, source, filename='<input>', symbol='single'):
        source=source.encode(self.stdin_encoding)
        if source[:1] in [' ', '\t']:
            source = 'if 1:\n%s' % source
        code = self.compile(source,filename,symbol)
        
        if code is None:
            # Case 2
            return True

        # Case 3
        # We store the code object so that threaded shells and
        # custom exception handlers can access all this info if needed.
        # The source corresponding to this can be obtained from the
        # buffer attribute as '\n'.join(self.buffer).
        self.code_to_run = code
        # now actually execute the code object
        if self._runcode(code) == 0:
            return False
        else:
            return None
    
    def _raw_input(self,message):
        content = {u'name':'stdin', u'data':message}
        msg = self.session.msg(u'stream', content=content)
            #print>>sys.__stdout__,"MESSAGE = ", Message(msg)
        self.pub_socket.send_json(msg)            
        #print("raw_input called")
        self.request_socket.send(message)
        #print("message was sended")
        raw_input_msg = self.request_socket.recv()
        #print("message was recved")
        return raw_input_msg
    
    def abort_queue(self):
        while True:
            try:
                ident = self.reply_socket.recv(zmq.NOBLOCK)
            except zmq.ZMQError, e:
                if e.errno == zmq.EAGAIN:
                    break
            else:
                assert self.reply_socket.rcvmore(), "Unexpected missing message part."
                msg = self.reply_socket.recv_json()
                print "message here :"+msg
            print>>sys.__stdout__, "Aborting:"
            print>>sys.__stdout__, Message(msg)
            msg_type = msg['msg_type']
            reply_type = msg_type.split('_')[0] + '_reply'
            reply_msg = self.session.msg(reply_type, {'status' : 'aborted'}, msg)
            print>>sys.__stdout__, Message(reply_msg)
            self.reply_socket.send(ident,zmq.SNDMORE)
            self.reply_socket.send_json(reply_msg)
            # We need to wait a bit for requests to come in. This can probably
            # be set shorter for true asynchronous clients.
            time.sleep(0.1)

    def execute_request(self, ident, parent):
        #send messages for current user
        self.display_hook.set_parent(parent)
        try:
            code = parent[u'content'][u'code']
            self.outputcache.prompt_count=self.outputcache.prompt_count+1
            self.display_hook.set_index(self.outputcache.prompt_count)
        except:
            print>>sys.__stderr__, "Got bad msg: "
            print>>sys.__stderr__, Message(parent)
            self.outputcache.prompt_count=self.outputcache.prompt_count-1
            self.display_hook.set_index(self.outputcache.prompt_count)
            return
        
        pyin_msg = self.session.msg(u'pyin',{u'code':code}, parent=parent)
        self.pub_socket.send_json(pyin_msg)
        try:
            #this command run source but it dont raise some exception
            # then a need reimplement some InteractiveShell methods that let me 
            # raise exc
            #self.runlines(code)
            
            #we dont need compile code here,
            # because it is complied in frontend before send it
            #self.user_ns and self.user_global_ns are inherited from InteractiveShell the Mother class
            
            self.hooks.pre_runcode_hook()
            self._runlines(code)
            
        except :
            result = u'error'
            etype, evalue, tb = sys.exc_info()
            tb = traceback.format_exception(etype, evalue, tb)
            exc_content = {
                u'status' : u'error',
                u'traceback' : tb,
                u'etype' : unicode(etype),
                u'evalue' : unicode(evalue)
            }
            exc_msg = self.session.msg(u'pyerr', exc_content, parent)
            self.pub_socket.send_json(exc_msg)
            reply_content = exc_content
        else:
            reply_content = {'status' : 'ok'}
            
        reply_msg = self.session.msg(u'execute_reply', reply_content, parent)
        print>>sys.__stdout__, Message(reply_msg)
        self.reply_socket.send(ident, zmq.SNDMORE)
        self.reply_socket.send_json(reply_msg)
        if reply_msg['content']['status'] == u'error':
            self.abort_queue()
            
        

    def complete_request(self, ident, parent):
        matches = {'matches' : self.complete(parent),
                   'status' : 'ok'}
        completion_msg = self.session.send(self.reply_socket, 'complete_reply',
                                           matches, parent, ident)
        print >> sys.__stdout__, completion_msg
    
    def prompt_request(self,ident,parent):
            prompt=self.hooks.generate_prompt(False)
            prompt_msg = self.session.msg(u'prompt',{u'data':prompt}, parent=parent)
            print(prompt_msg)
            self.reply_socket.send(ident, zmq.SNDMORE)
            self.reply_socket.send_json(prompt_msg)
            #self.session.send(self.reply_socket, 'prompt_reply',)
    
    def pid_request(self,ident,parent):
            pid_msg = {u'pid':self.kernel_pid,
                       'status':'ok'}
            self.session.send(self.reply_socket, 'pid_reply',pid_msg, parent, ident)
            #print("EN pid_request")
            #print(pid_msg)
            #self.reply_socket.send(ident, zmq.SNDMORE)
            #self.reply_socket.send_json(prompt_msg)
            
    
    def complete(self, msg):
        #return self.completer.complete(msg.content.line, msg.content.text)<-- code
        #we dont need KernelCompleter, we can use IPCompleter object inherited
        #from InteractiveShell and suppurt magics etc... Omar.
        return self.Completer.all_completions(msg.content.line)


    def _interact(self):
        ident = self.reply_socket.recv()
        assert self.reply_socket.rcvmore(), "Unexpected missing message part."
        msg = self.reply_socket.recv_json()
        omsg = Message(msg)
        print>>sys.__stdout__, omsg
        handler = self.handlers.get(omsg.msg_type, None)
        if handler is None:
            print >> sys.__stderr__, "UNKNOWN MESSAGE TYPE:", omsg
        else:
            handler(ident, omsg)    
      
            

    def start(self):
        while True:
            self.interact()
            
        
         
if __name__ == "__main__" :
    c = zmq.Context(1)

    ip = '127.0.0.1'
    port_base = 5555
    connection = ('tcp://%s' % ip) + ':%i'
    rep_conn = connection % port_base
    pub_conn = connection % (port_base+1)
    req_conn = connection % (port_base+2)
    
    print >>sys.__stdout__, "Starting the kernel..."
    print >>sys.__stdout__, "On:",rep_conn, pub_conn

    session = Session(username=u'kernel')

    reply_socket = c.socket(zmq.XREP)
    reply_socket.bind(rep_conn)

    pub_socket = c.socket(zmq.PUB)
    pub_socket.bind(pub_conn)
        
    
    request_socket = c.socket(zmq.REQ)
    request_socket.bind(req_conn)
    
    #stdout = OutStream(session, pub_socket, u'stdout')
    #stderr = OutStream(session, pub_socket, u'stderr')
    #sys.stdout = stdout
    #sys.stderr = stderr
    #display_hook = DisplayHook(session, pub_socket)
    #sys.displayhook = display_hook

    kernel = InteractiveShellKernel(session, reply_socket, pub_socket, request_socket)
    
    print >>sys.__stdout__, "Use Ctrl-\\ (NOT Ctrl-C!) to terminate."
    kernel.start()
    #kernel.test()
