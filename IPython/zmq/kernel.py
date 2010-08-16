# -*- coding: utf-8 -*-
"""Ipython's kernel working with python-zmq

Ipython's kernel, is a ipython interface that listen in ports waiting for request.
it use three socket's types XREP, SUB, REP that using standarized menssages let
comunication between several frontends, allowing have a common enviroment for developers.

For more details, see the class docstring below.
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
import zmq
import sys
import time
import os
import subprocess
import traceback
from contextlib import nested

#-----------------------------------------------------------------------------
# Imports from ipython
#-----------------------------------------------------------------------------
from IPython.zmq.session import Session, Message, extract_header
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
    """A file like object that publishes the stream to a 0MQ PUB socket.
    
    Parameters
    ----------
    session : object
        instantiated object from class Session in module session
    
    pub_socket : object
        instantiated object from class Socket in module zmq
    
    name : str
        content the ouptut type like stdout or stderr
    
    max_buffer : int
        bites of buffer before send a message
        
    Example:
    stdout = OutStream(session, pub_socket, u'stdout')
    stderr = OutStream(session, pub_socket, u'stderr')
    """

    def __init__(self, session, pub_socket, name, max_buffer=200):
        self.session = session
        self.pub_socket = pub_socket
        self.name = name
        self._buffer = []
        self._buffer_len = 0
        self.max_buffer = max_buffer
        self.parent_header = {}

    def set_parent(self, parent):
        """ this method put from a session the username and ids to send messages
        
            Parameters
            ----------
            parent : dict
                dictionary that content username, msg_id, session(uuid) 
        """    
        self.parent_header = extract_header(parent)

    def flush(self):
        """ acumulate a buffer indicate by max_buffer and send it using the sub socket
        
        """
        if self.pub_socket is None:
            raise ValueError(u'I/O operation on closed file')
        else:
            if self._buffer:
                data = ''.join(self._buffer)
                content = {u'name':self.name, u'data':data}
                msg = self.session.msg(u'stream', content=content,
                                       parent=self.parent_header)
                self.pub_socket.send_json(msg)
                self._buffer_len = 0
                self._buffer = []

    def isattr(self):
        return False

    def next(self):
        raise IOError('Read not supported on a write only stream.')

    def read(self, size=None):
        raise IOError('Read not supported on a write only stream.')
        
    readline=read

    def write(self, string):
        """ method that overwrite sys.stdout.write or sys.stderr.write
            
            Parameters
            ----------
            string : str
                content a data to print
        """     
        if self.pub_socket is None:
            raise ValueError('I/O operation on closed file')
        else:
            self._buffer.append(string)
            self._buffer_len += len(string)
            self._maybe_send()

    def _maybe_send(self):
        """ acumulate buffer before send it
    
        """  
        if '\n' in self._buffer[-1]:
            self._buffer=self._buffer[0:-1]
            self.flush()
        if self._buffer_len > self.max_buffer:
            self.flush()

    def writelines(self, sequence):
        """ method that get a sequence of string from sys.stdout or sys.stderr
            
            Parameters
            ----------
            sequence : tuple
            content a data to send with subscribe socket
        """       
        if self.pub_socket is None:
            raise ValueError('I/O operation on closed file')
        else:
            for s in sequence:
                self.write(s)
    def fileno(self):
        """ return the number asociated a file
        """
        if self.name == "stdout":
            return 1
        if self.name == "stderr":
            return 2
                    
                


class DisplayHook(object):
    """class to overwrite outputcache.__class__.display in InteractiveShell 
    and using sub socket send pyout messages ( see messages standards )
        
    Parameters
    ----------
    session : object
        instantiated object from class Session in module session
    
    pub_socket : object
        instantiated object from class Socket in module zmq
        
    Example:
    self.display_hook = DisplayHook(self.session,self.pub_socket)
    """
 
    def __init__(self, session, pub_socket):
        self.session = session
        self.pub_socket = pub_socket
        self.parent_header = {}

    def __call__(self, obj):
        """ set this class callable to recieve and object and send it 
        using sub channel like a string
        
        Note:this class send to the index of output in ipython
        
        Parameters
        ----------
        
        obj : object
            python or ipython code that is passed to string a sended     
        """
        if obj is None:
            return

        __builtin__._ = obj
        msg = self.session.msg(u'pyout', {u'data':repr(obj),u'index':self.index},
                               parent=self.parent_header)
        self.pub_socket.send_json(msg)

    def set_parent(self, parent):
        """ this method put from a session the username and ids to send messages
            
            Parameters
            ----------
            parent : dict
                dictionary that content username, msg_id, session(uuid) 
        """        
        self.parent_header = extract_header(parent)
    def set_index(self,index):
        """ let you set index of ipython output in the message
                
            Parameters
            ----------
            index : int
                index of ipython output, taked from outputcache in InteractiveShell class 
        
        """
        self.index = index



class InteractiveShellKernel(InteractiveShell):
    """Kernel of ipython working with python-zmq
        
        NOTE: this class inherit from InteractiveShell to supoort all ipython's features
        
        Parameters:
        ----------
        session : object
        instantiated object from class Session in module session
        
        xreply_socket : object
            instantiated object from class Socket in module zmq type XREP (Reply)
        
        pub_socket : object
            instantiated object from class Socket in module zmq type PUB (publisher)
        
        request_socket : object
            instantiated object from class Socket in module zmq type REQ (request)
            
        Example:
        --------
        c = zmq.Context(1)
        ip = '127.0.0.1'
        port_base = 5555
        connection = ('tcp://%s' % ip) + ':%i'
        rep_conn = connection % port_base
        pub_conn = connection % (port_base+1)
        req_conn = connection % (port_base+2)
        session = Session(username=u'kernel')
 
        reply_socket = c.socket(zmq.XREP)
        reply_socket.bind(rep_conn)
        
        pub_socket = c.socket(zmq.PUB)
        pub_socket.bind(pub_conn)
        
        
        request_socket = c.socket(zmq.REQ)
        request_socket.bind(req_conn)
        
        kernel = InteractiveShellKernel(session, reply_socket, pub_socket, request_socket)
        kernel.start()
        
    """
    def __init__(self,session, xreply_socket, pub_socket,request_socket):
        self.session = session
        self.reply_socket = xreply_socket
        self.pub_socket = pub_socket
        self.request_socket = request_socket
        self.user_ns = {}
        self.history = []
        InteractiveShell.__init__(self,user_ns=self.user_ns,user_global_ns=self.user_ns)
        
        #getting outputs
        self.stdout = OutStream(self.session, self.pub_socket, u'stdout')
        self.stderr = OutStream(self.session, self.pub_socket, u'stderr')
        
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = self.stdout
        sys.stderr = self.stderr
        
        ##overloaded raw_input
        __builtin__.raw_input = self._raw_input
        
        self.display_hook = DisplayHook(self.session,self.pub_socket)
        self.outputcache.__class__.display = self.display_hook
        self.init_readline()
        self.outputcache.promt_count = 1
        self.kernel_pid=os.getpid()
        self.handlers = {}
        for msg_type in ['execute_request', 'complete_request','prompt_request','pid_request']:
            self.handlers[msg_type] = getattr(self, msg_type)
       
    def system(self, cmd):
        """Reimplementation of system in ipython to capture pipe outputs
        
        Parameters
        ----------
        cmd : str
             command to run into operating system
        """
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
    
    def runcode(self,code_obj):
        """This method is a reimplementation of method runcode 
        from InteractiveShell class to InteractiveShellKernel
        Execute a code object.

        Note: When an exception occurs, self.showtraceback() is called to display a
        traceback.

        Parameters:
        -----------
        code_obj : str
            code to execute
        
        Returns
        -------
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
                sys.excepthook = old_excepthook
        except SystemExit:
           self.resetbuffer()
           self.showtraceback(exception_only=True)
           warn("To exit: use any of 'exit', 'quit', %Exit or Ctrl-D.", level=1)
        except self.custom_exceptions:
            self.etype,self.value,self.tb = sys.exc_info()
            
    def runlines(self,lines,clean=True):
        """ split lines in a single line before of execute 
        
        NOTE:This method is capable of running a string containing multiple source
        lines, as if they had been entered at the IPython prompt.  Since it
        exposes IPython's processing machinery, the given strings can contain
        magic calls (%magic), special shell access (!cmd), etc.
        Parameters:
        -----------
        lines : tuple
            contents python or ipython code
        
        clean :  Boolean
            clean a internal buffer 
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
                    more = self.push_line(prefiltered)
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
                self.push_line('\n')
                
    
    def push_line(self, line):
        """ Reimplementation of push_line method from InteractiveShell.

        NOTE:The line should not have a trailing newline; it may have
        internal newlines.  The line is appended to a buffer and the
        interpreter's _runsource() "Reimplemented method too for kernel" method is called with the
        concatenated contents of the buffer as source.  If this
        indicates that the command was executed or invalid, the buffer
        is reset; otherwise, the command is incomplete, and the buffer
        is left as it was after the line was appended.  The return
        value is 1 if more input is required, 0 if the line was dealt
        with in some way (this is the same as runsource()).
        
        Parameters:
        -----------
        line : str
            ipython/python code
        
        Returns:
        --------
        True : if line is part of a block of code
        False : if is a single line of code
        """

        for subline in line.splitlines():
            self._autoindent_update(subline)
        self.buffer.append(line)
        more = self.runsource('\n'.join(self.buffer), self.filename)
        if not more:
            self.resetbuffer()
        return more

    def runsource(self, source, filename='<input>', symbol='single'):
        """ Reimplementation of runsource from InteractiveShell
        Compile and run some source in the interpreter.


        One several things can happen:

        1) The input is incorrect; compile_command() raised an
        exception (SyntaxError or OverflowError). A syntax traceback
        will be printed by calling the showsyntaxerror() method.

        2) The input is incomplete, and more input is required;
        compile_command() returned None. Nothing happens.

        3) The input is complete; compile_command() returned a code
        object. The code is executed by calling self.runcode() (which
        also handles run-time exceptions, except for SystemExit).

        The return value is:

        - True in case 2

        - False in the other cases, unless an exception is raised, where
        None is returned instead. This can be used by external callers to
        know whether to continue feeding input or not.

        The return value can be used to decide whether to use sys.ps1 or
        sys.ps2 to prompt the next line.
        
        """
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
        if self.runcode(code) == 0:
            return False
        else:
            return None
    
    def _raw_input(self,message):
        """ Method to overwrite raw_input in __builtin__.raw_input = self._raw_input
        
           this method use rep socket to send a message to frontend, it let know to frontend 
           that need call raw_input and return string to kernel
        
        Parameters:
        ----------
        message : str
             string with message to show in raw_input
        
        Returns:
        --------
        raw_input_msg : str
            string that frontend send to kernel when call raw_input
           
        
        """
            
            
        content = {u'name':'stdin', u'data':message}
        msg = self.session.msg(u'stream', content=content)
        self.pub_socket.send_json(msg)            
        time.sleep(0.05)
        self.request_socket.send_json(message)
        raw_input_msg = self.request_socket.recv_json()
        return raw_input_msg
    
    def abort_queue(self):
        """ send a message when queue in kernel was aborted
            to let know to kernel that ir can continue with other request
        """
        while True:
            try:
                ident = self.reply_socket.recv(zmq.NOBLOCK)
            except zmq.ZMQError, e:
                if e.errno == zmq.EAGAIN:
                    break
            else:
                assert self.reply_socket.rcvmore(), "Unexpected missing message part."
                msg = self.reply_socket.recv_json()
                #print "message here :"+msg
            print>>sys.__stdout__, "Aborting:"
            #print>>sys.__stdout__, Message(msg)
            msg_type = msg['msg_type']
            reply_type = msg_type.split('_')[0] + '_reply'
            reply_msg = self.session.msg(reply_type, {'status' : 'aborted'}, msg)
            self.reply_socket.send(ident,zmq.SNDMORE)
            self.reply_socket.send_json(reply_msg)
            # We need to wait a bit for requests to come in. This can probably
            # be set shorter for true asynchronous clients.
            time.sleep(0.1)

    def execute_request(self, ident, parent):
        """ Execute requests gotten from frontends and proccess the handlers
            to generated messages with outputs and send it to frontend.
            this method let know to frontend the prompt's index. 
        
        Parameters:
        -----------
        ident : str
             string with uuid of user in frontend.
        
        parent : dict
             dictionary that content all needed information to proccess code
             associated a specific user.
             
        """
        try:
            self.display_hook.set_parent(parent)        
            code = parent[u'content'][u'code']
            self.current_prompt=parent[u'content'][u'prompt']
            self.display_hook.set_index(self.current_prompt)
            
        except:
            print>>sys.__stderr__, "Got bad msg: "
            print>>sys.__stderr__, Message(parent)
            self.outputcache.prompt_count=self.outputcache.prompt_count-1
            self.display_hook.set_index(self.outputcache.prompt_count)
            return
        
        pyin_msg = self.session.msg(u'pyin',{u'code':code}, parent=parent)
        self.pub_socket.send_json(pyin_msg)
        try:
            
            #we dont need compile code here,
            # because it is complied in frontend before send it
            #self.user_ns and self.user_global_ns are inherited from InteractiveShell the Mother class
            
            self.hooks.pre_runcode_hook()
            self.runlines(code)
            
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
        #print>>sys.__stdout__, Message(reply_msg)
        self.reply_socket.send(ident, zmq.SNDMORE)
        self.reply_socket.send_json(reply_msg)
        if reply_msg['content']['status'] == u'error':
            self.abort_queue()

    def complete_request(self, ident, parent):
        """ Execute requests to readline, this let get tab-completion
        reading the namespace from kernel
        
        Parameters:
        -----------
        ident : str
             string with uuid of user in frontend.
        
        parent : dict
             dictionary that content all needed information to proccess code
             associated a specific user.
             
        """    
        matches = {'matches' : self.complete(parent),
                   'status' : 'ok'}
        completion_msg = self.session.send(self.reply_socket, 'complete_reply',
                                           matches, parent, ident)
        #print >> sys.__stdout__, completion_msg
    
    def prompt_request(self,ident,parent):
        """ Execute requests to get the number to frontend's index,
        like a In[index]:; when init the frontend, it call this request 
        to get the current index in kernel.  
        
        Parameters:
        -----------
        ident : str
             string with uuid of user in frontend.
        
        parent : dict
             dictionary that content all needed information to proccess code
             associated a specific user.
             
        """
        self.outputcache.prompt_count = self.outputcache.prompt_count+1
        prompt_msg = {u'prompt':self.outputcache.prompt_count,
                       'status':'ok'}    
        self.session.send(self.reply_socket, 'prompt_reply',prompt_msg, parent, ident)
            
    def pid_request(self,ident,parent):
        """ request to get the kernel`s pid, to enable shortcut Crt+C
        with a signal of interruption, while a bucles are running.  
        
        Parameters:
        -----------
        ident : str
             string with uuid of user in frontend.
        
        parent : dict
             dictionary that content all needed information to proccess code
             associated a specific user.
             
        """
        pid_msg = {u'pid':self.kernel_pid,
                  'status':'ok'}
        self.session.send(self.reply_socket, 'pid_reply',pid_msg, parent, ident)
            
            
    
    def complete(self, msg):
        """ method that call local readline and return the results
            
            Parameters:
            -----------
            msg : dict
                 msg.content.line is string with word to complete
            
            Returns:
            --------
            dict
            matches found 
            
        """
        
        return self.Completer.all_completions(msg.content.line)


    def interact(self):
        """ this method wait a request to be proccessed.
        
        when it get a message, call the differents handlers to proccess information using
        socket sub to send stdout/stderr outputs and reply to send message's status.
            
        """
            
        ident = self.reply_socket.recv()
        assert self.reply_socket.rcvmore(), "Unexpected missing message part."
        msg = self.reply_socket.recv_json()
        omsg = Message(msg)
        #print>>sys.__stdout__, omsg
        handler = self.handlers.get(omsg.msg_type, None)
        if handler is None:
            print >> sys.__stderr__, "UNKNOWN MESSAGE TYPE:", omsg
        else:
            handler(ident, omsg)    
      
    def start(self):
        """Call interact to stay wating request ever
        """
        while True:
            self.interact()
            
def launch_kernel(xrep_port=0, pub_port=0, req_port=0, independent=False):
    """ Launches a localhost kernel, binding to the specified ports.

    Parameters
    ----------
    xrep_port : int, optional
        The port to use for XREP channel.

    pub_port : int, optional
        The port to use for the SUB channel.

    req_port : int, optional
        The port to use for the REQ (raw input) channel.

    independent : bool, optional (default False) 
        If set, the kernel process is guaranteed to survive if this process
        dies. If not set, an effort is made to ensure that the kernel is killed
        when this process dies. Note that in this case it is still good practice
        to kill kernels manually before exiting.

    Returns
    -------
    A tuple of form:
        (kernel_process, xrep_port, pub_port, req_port)
    where kernel_process is a Popen object and the ports are integers.
    """
    import socket
    from subprocess import Popen

    # Find open ports as necessary.
    ports = []
    ports_needed = int(xrep_port <= 0) + int(pub_port <= 0) + int(req_port <= 0)
    for i in xrange(ports_needed):
        sock = socket.socket()
        sock.bind(('', 0))
        ports.append(sock)
    for i, sock in enumerate(ports):
        port = sock.getsockname()[1]
        sock.close()
        ports[i] = port
    if xrep_port <= 0:
        xrep_port = ports.pop(0)
    if pub_port <= 0:
        pub_port = ports.pop(0)
    if req_port <= 0:
        req_port = ports.pop(0)
        
    # Spawn a kernel.
    command = 'from IPython.zmq.kernel import main; main()'
    arguments = [ sys.executable, '-c', command, '--xrep', str(xrep_port), 
                  '--pub', str(pub_port), '--req', str(req_port) ]
    if independent:
        if sys.platform == 'win32':
            proc = Popen(['start', '/b'] + arguments, shell=True)
        else:
            proc = Popen(arguments, preexec_fn=lambda: os.setsid())
    else:
        if sys.platform == 'win32':
            from _subprocess import DuplicateHandle, GetCurrentProcess, \
                DUPLICATE_SAME_ACCESS
            pid = GetCurrentProcess()
            handle = DuplicateHandle(pid, pid, pid, 0, 
                                     True, # Inheritable by new  processes.
                                     DUPLICATE_SAME_ACCESS)
            proc = Popen(arguments + ['--parent', str(int(handle))])
        else:
            proc = Popen(arguments + ['--parent'])

    return proc, xrep_port, pub_port, req_port
    
        
         
def main():
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
    
    kernel = InteractiveShellKernel(session, reply_socket, pub_socket, request_socket)
    
    print >>sys.__stdout__, "Use Ctrl-\\ (NOT Ctrl-C!) to terminate."
    kernel.start()

if __name__ == "__main__" :
    main()   
